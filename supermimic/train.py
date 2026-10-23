"""SuperMimic training (Algorithm A.1): collect -> fit world model -> BPTT policy + critic update."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from supermimic.runtime import add_runtime_args, artifact_dir, experiment_root, network_shapes, STORAGE_POLICY

parser = argparse.ArgumentParser()
parser.add_argument("--num_envs", type=int, default=16)
parser.add_argument("--iterations", type=int, default=320_000)
parser.add_argument("--buffer_steps", type=int, default=1000)
parser.add_argument("--utd", type=float, default=0.4, help="updates per vectorized simulator step")
parser.add_argument("--horizon", type=int, default=32)
parser.add_argument("--goal_frames", type=int, default=10)
parser.add_argument("--hist", type=int, default=10)
parser.add_argument("--wm_window", type=int, default=8)
parser.add_argument("--wm_batches", type=int, default=10)
parser.add_argument("--wm_batch", type=int, default=2048)
parser.add_argument("--pi_batch", type=int, default=4096)
parser.add_argument("--lr", type=float, default=2e-4)
parser.add_argument("--gamma", type=float, default=0.99)
parser.add_argument("--lam", type=float, default=0.95)
parser.add_argument("--action_noise", type=float, default=0.1)
parser.add_argument("--critic_epochs", type=int, default=5)
parser.add_argument("--critic_minibatches", type=int, default=4)
parser.add_argument("--no_critic", action="store_true")
parser.add_argument("--warmup_steps", type=int, default=64, help="sim steps before any update")
parser.add_argument("--wm_only_iters", type=int, default=500, help="world-model-only iterations at the start")
parser.add_argument("--lr_decay_iters", type=int, default=250_000)
parser.add_argument("--ckpt_every", type=int, default=2000)
parser.add_argument("--last_every", type=int, default=None,
                    help="save resumable last.pt every N iterations; defaults to --ckpt_every")
parser.add_argument("--log_every", type=int, default=50)
parser.add_argument("--motion_dir", type=str, required=True, help="existing local motion directory or joblib file")
parser.add_argument("--log_dir", type=str, default=str(experiment_root() / "runs" / "run"))
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--resume", type=str, default=None)
parser.add_argument("--amp", type=str, default="none", choices=["none", "bf16"], help="autocast dtype for MLP matmuls")
parser.add_argument("--compile", action="store_true", help="compile model update kernels")
parser.add_argument("--no_checkpoint", action="store_true", help="validate updates without writing model artifacts")
add_runtime_args(parser)
args = parser.parse_args()
args.last_every = args.ckpt_every if args.last_every is None else args.last_every

stop_signal = None


def request_stop(signum, _frame):
    # Signal handlers only request a stop. Finish the active optimizer updates
    # before saving, so a checkpoint never contains a partly updated iteration.
    global stop_signal
    if stop_signal is None:
        stop_signal = signum


signal.signal(signal.SIGTERM, request_stop)
signal.signal(signal.SIGINT, request_stop)

import torch
import torch.nn as nn

from supermimic.buffer import ReplayBuffer
from supermimic.env import TrackingSim, make_sim, launch_simulation
from supermimic.kinematics import G1Kinematics
from supermimic.mdp import CRITIC_EXTRA, INV_DIM, MDP, OBS_DIM, invariant_features, normalize_xi, unflatten_state
from supermimic.motion import MotionLib
import supermimic.networks as networks
from supermimic.networks import Critic, Policy, WorldModel
from supermimic.robot_contract import assert_contract_compatible, load_contract

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.manual_seed(args.seed)
networks.AMP_DTYPE = torch.bfloat16 if args.amp == "bf16" else None
dev = args.device
if args.backend == "mjlab" and not dev.startswith("cuda"):
    raise ValueError("MJLab backend requires a CUDA device; use --backend mujoco --device cpu for CPU checks")
if args.utd <= 0 or min(args.wm_batches, args.wm_batch, args.pi_batch, args.horizon, args.hist, args.goal_frames, args.wm_window, args.log_every, args.ckpt_every, args.last_every, args.critic_epochs, args.critic_minibatches) <= 0:
    raise ValueError("Batch sizes, horizons, intervals and UTD must be positive")
if args.buffer_steps < max(args.wm_window, args.hist):
    raise ValueError("buffer_steps must cover wm_window and observation history")
if args.horizon * args.pi_batch < args.critic_minibatches:
    raise ValueError("More critic minibatches than rollout samples")
args.log_dir = str(artifact_dir(args.log_dir))
print(STORAGE_POLICY, flush=True)
os.makedirs(args.log_dir, exist_ok=True)
if not args.resume and any(os.path.exists(os.path.join(args.log_dir, n)) for n in ("last.pt", "train_log.csv")):
    raise FileExistsError("Run directory already contains training outputs; use --resume or a fresh --log_dir")

contract = load_contract(args.profile, robot=args.robot, xml_path=args.xml_path)
kin = G1Kinematics(dev, xml_path=contract.xml_path)
motion = MotionLib.from_dir(args.motion_dir, kin, dev)
mdp = MDP(kin, motion, torch.tensor(contract.default_q, device=dev), observation_mode=args.observation_mode)
OBS_DIM = mdp.obs_dim
if int(motion.clip_len.max()) <= args.horizon:
    raise ValueError("At least one motion must contain horizon+1 frames")
from dataclasses import asdict
K, Hh, HZ = args.goal_frames, args.hist, args.horizon
GOAL_DIM = 73 * K
CRITIC_IN = INV_DIM + CRITIC_EXTRA + GOAL_DIM

wm_hidden, pi_hidden, v_hidden = network_shapes(args.network_size)
wm = WorldModel(hidden=wm_hidden).to(dev)
pi = Policy(OBS_DIM, GOAL_DIM, hist=Hh, hidden=pi_hidden).to(dev)
critic = Critic(CRITIC_IN, hidden=v_hidden).to(dev)
opt_wm = torch.optim.Adam(wm.parameters(), lr=args.lr)
opt_pi = torch.optim.Adam(pi.parameters(), lr=args.lr, betas=(0.9, 0.95))
opt_v = torch.optim.Adam(critic.parameters(), lr=args.lr)
start_it, wall_offset, sim_steps = 0, 0.0, 0
if args.resume:
    ck = torch.load(args.resume, map_location=dev, weights_only=False)
    if not all(k in ck for k in ("critic", "opt_wm", "opt_pi", "opt_v")):
        raise ValueError("Resume requires last.pt with critic and optimizer states; ckpt_*.pt is evaluation-only")
    for key in ("profile", "observation_mode", "network_size", "goal_frames", "hist", "backend",
                "gamma", "lam", "horizon", "wm_window", "no_critic", "utd", "action_noise",
                "wm_only_iters", "critic_epochs", "critic_minibatches", "lr", "lr_decay_iters"):
        if ck["args"].get(key) != getattr(args, key):
            raise ValueError(f"Resume mismatch for {key}: checkpoint={ck['args'].get(key)}, run={getattr(args, key)}")
    assert_contract_compatible(ck.get("contract"), contract)
    if os.path.realpath(ck["args"]["motion_dir"]) != os.path.realpath(args.motion_dir):
        raise ValueError("Resume motion source differs from checkpoint")
    wm.load_state_dict(ck["wm"]), pi.load_state_dict(ck["pi"]), critic.load_state_dict(ck["critic"])
    opt_wm.load_state_dict(ck["opt_wm"]), opt_pi.load_state_dict(ck["opt_pi"]), opt_v.load_state_dict(ck["opt_v"])
    start_it, wall_offset, sim_steps = ck["iteration"], ck["wall_time"], ck["sim_steps"]

args_name = f"args_resume_{start_it:06d}.json" if args.resume else "args.json"
with open(os.path.join(args.log_dir, args_name), "w") as output:
    json.dump(vars(args), output, indent=2)
if not args.resume:
    with open(os.path.join(args.log_dir, "robot_contract.json"), "w") as output:
        json.dump(asdict(contract), output, indent=2)


# per-component floors on the error normalization (pos, rot, lin vel, ang vel, q, qd increments)
ERR_FLOOR = torch.cat((torch.full((3,), 3e-3), torch.full((3,), 5e-3), torch.full((3,), 2e-2), torch.full((3,), 5e-2),
                       torch.full((29,), 3e-3), torch.full((29,), 5e-2))).to(dev)  # fmt: skip


def _wm_rollout(s, a, xi):
    S = unflatten_state(s[:, 0])
    preds = []
    for j in range(args.wm_window):
        S = wm.step(S, a[:, j], normalize_xi(xi[:, j]))
        preds.append(S)
    return tuple(torch.stack([P[i] for P in preds], 1) for i in range(6))  # (B, k, ...)


def _wm_err(S_hat, s1, mask):
    std = torch.maximum(wm.out_norm.std(), ERR_FLOOR)
    e = (wm.state_error(S_hat, unflatten_state(s1)) / std) ** 2  # (B, k, D)
    e = e.mean(-1)
    return (e * mask).sum() / s1.shape[0], e[:, -1]


def _imag_step(S, o_hist, a_prev, f, xi, xi_n, g):
    a = pi(o_hist, g)
    if contract.action_clip is not None:
        a = a.clamp(-contract.action_clip, contract.action_clip)
    S1 = wm.step(S, a, xi_n)
    f1 = f + 1
    o1 = mdp.add_noise(mdp.obs(S1, a, xi, f1))
    o_hist = torch.cat((o_hist[:, 1:], o1.unsqueeze(1)), 1)
    return S1, a, o_hist, f1, motion.goal(f1, K)


def _reward_term(S, f, a, a_prev):
    return mdp.reward(S, f, a, a_prev), mdp.soft_termination(S, f)


def _critic_input(S, f, xi_n, g):
    return torch.cat((mdp.critic_features(S, f, xi_n), g), -1)


compile_fn = torch.compile if args.compile else (lambda fn: fn)
wm_rollout = compile_fn(_wm_rollout)
wm_err = compile_fn(_wm_err)
imag_step = compile_fn(_imag_step)
reward_term = compile_fn(_reward_term)
critic_input_c = compile_fn(_critic_input)


def lr_at(it: int) -> float:
    if it >= args.lr_decay_iters:
        return args.lr * 0.03
    return args.lr * (0.03 + 0.97 * 0.5 * (1 + math.cos(math.pi * it / args.lr_decay_iters)))


def set_requires_grad(m: nn.Module, flag: bool):
    for p in m.parameters():
        p.requires_grad_(flag)


# ------------------------------------------------------------------------------------------------
def wm_update():
    w = buffer.sample_windows(args.wm_batch, args.wm_window)
    S_hat = wm_rollout(w["s"], w["a"], w["xi"])
    loss, e_last = wm_err(S_hat, w["s1"], w["mask"])
    opt_wm.zero_grad(set_to_none=True)
    loss.backward()
    nn.utils.clip_grad_norm_(wm.parameters(), 1.0)
    opt_wm.step()
    m = w["mask"][:, -1]
    return loss.detach() / args.wm_window, (e_last.detach() * m).sum() / m.sum().clamp(min=1)


def sample_valid_starts(B: int):
    return buffer.sample_valid_starts(B, Hh, HZ, motion.clip_end, motion.clip_id)


PROFILE = dev.startswith("cuda") and bool(int(os.environ.get("SM_PROFILE", "0")))


def policy_update():
    if PROFILE:
        torch.cuda.synchronize(); tq0 = time.time()
    s, h = sample_valid_starts(args.pi_batch)
    S = unflatten_state(s["s"])
    xi, f, a_prev = s["xi"], s["f"], s["a_prev"]
    xi_n = normalize_xi(xi)
    with torch.no_grad():
        o_hist = mdp.obs(unflatten_state(h["s"]), h["a_prev"], h["xi"], h["f"])
    o_hist = mdp.add_noise(o_hist)
    set_requires_grad(wm, False)
    set_requires_grad(critic, False)
    B = args.pi_batch
    g0 = motion.goal(f, K)
    g = g0
    S0 = S
    Ss, As, Aps, Fs, Gs = [], [], [], [], []
    for t in range(HZ):
        Aps.append(a_prev)
        S, a_prev, o_hist, f, g = imag_step(S, o_hist, a_prev, f, xi, xi_n, g)
        Ss.append(S), As.append(a_prev), Fs.append(f), Gs.append(g)
    flat = lambda xs: torch.stack(xs).flatten(0, 1)  # noqa: E731  (H*B, ...)
    S_all = tuple(flat([St[i] for St in Ss]) for i in range(6))
    f_all = flat(Fs)
    r, d = reward_term(S_all, f_all, flat(As), flat(Aps))
    r, d = r.view(HZ, B), d.view(HZ, B)
    alive = torch.cumprod(1 - d, 0)  # c_{t+1}
    c_t = torch.cat((torch.ones(1, B, device=dev), alive[:-1]), 0)
    disc = args.gamma ** torch.arange(HZ, device=dev, dtype=torch.float32).unsqueeze(-1)
    J = (disc * c_t * r).sum(0)
    c = alive[-1]
    r_sum = (c_t * r).detach().sum(0)
    rews, dones = r.detach(), d.detach()
    if not args.no_critic:
        J = J + (args.gamma**HZ) * c * critic(_critic_input(S, f, xi_n, g))
    loss = -J.mean()
    if PROFILE:
        torch.cuda.synchronize(); tq1 = time.time()
    opt_pi.zero_grad(set_to_none=True)
    loss.backward()
    if PROFILE:
        torch.cuda.synchronize(); tq2 = time.time()
    gn = nn.utils.clip_grad_norm_(pi.parameters(), 1.0)
    nn.utils.clip_grad_value_(pi.parameters(), 0.1)
    if torch.isfinite(gn):
        opt_pi.step()
    set_requires_grad(wm, True)
    set_requires_grad(critic, True)
    # ---------------- critic: GAE(lambda) targets over the imagined transitions ----------------
    v_loss = torch.zeros(())
    if not args.no_critic:
        with torch.no_grad():
            S_c = tuple(torch.cat((S0[i].unsqueeze(0), torch.stack([St[i].detach() for St in Ss])), 0).flatten(0, 1) for i in range(6))
            f_c = torch.cat((s["f"].unsqueeze(0), torch.stack(Fs)), 0).flatten()
            g_c = torch.cat((g0.unsqueeze(0), torch.stack(Gs)), 0).flatten(0, 1)
            xi_c = xi_n.unsqueeze(0).expand(HZ + 1, -1, -1).flatten(0, 1)
            X = critic_input_c(S_c, f_c, xi_c, g_c).view(HZ + 1, B, -1)
        critic.norm.update(X)
        with torch.no_grad():
            V = critic(X)
            R = V[-1]
            targets = []
            for t in range(HZ - 1, -1, -1):
                R = rews[t] + args.gamma * (1 - dones[t]) * ((1 - args.lam) * V[t + 1] + args.lam * R)
                targets.append(R)
            targets = torch.stack(targets[::-1])  # (H, B)
        Xf, Yf = X[:-1].reshape(-1, X.shape[-1]), targets.reshape(-1)
        n = Xf.shape[0]
        for _ in range(args.critic_epochs):
            perm = torch.randperm(n, device=dev)
            for idx in torch.tensor_split(perm, args.critic_minibatches):
                v_loss = ((critic(Xf[idx]) - Yf[idx]) ** 2).mean()
                opt_v.zero_grad(set_to_none=True)
                v_loss.backward()
                nn.utils.clip_grad_norm_(critic.parameters(), 1.0)
                opt_v.step()
    if PROFILE:
        torch.cuda.synchronize()
        print(f"[prof] imagine fwd {1e3*(tq1-tq0):.0f} ms | bwd {1e3*(tq2-tq1):.0f} ms | critic {1e3*(time.time()-tq2):.0f} ms", flush=True)
    return loss.detach(), v_loss.detach(), (r_sum / HZ / 0.1).mean(), gn.detach(), c.mean().detach()


# ------------------------------------------------------------------------------------------------
sim_cfg = make_sim(dev, args)
with launch_simulation(sim_cfg, args):
    env = TrackingSim(sim_cfg, args.num_envs, motion, mdp, gamma=args.gamma)
    buffer = ReplayBuffer(args.buffer_steps, args.num_envs, dev)
    obs_hist = torch.zeros(args.num_envs, Hh, OBS_DIM, device=dev)

    @torch.no_grad()
    def collect(n_steps: int, stats: dict):
        global obs_hist, sim_steps
        for _ in range(n_steps):
            S = env.state()
            o = mdp.add_noise(mdp.obs(S, env.a_prev, env.xi, env.f))
            fresh = env.ep_step == 0
            obs_hist = torch.where(fresh[:, None, None], o.unsqueeze(1).expand_as(obs_hist), torch.cat((obs_hist[:, 1:], o.unsqueeze(1)), 1))
            g = motion.goal(env.f, K)
            pi.obs_norm.update(o)
            pi.goal_norm.update(g)
            a = pi(obs_hist, g)
            a = torch.clamp(a + args.action_noise * torch.randn_like(a), -20, 20)
            out = env.step(a)
            buffer.add(out)
            S0, S1 = unflatten_state(out["s"]), unflatten_state(out["s1"])
            wm.in_norm.update(wm.inputs(S0, out["a"], normalize_xi(out["xi"])))
            wm.out_norm.update(wm.targets(S0, S1))
            sim_steps += args.num_envs
            stats["r"].append(out["r"].mean() / 0.1)
            if "ep_len" in out:
                stats["ep_len"].append(out["ep_len"].mean())
                stats["ep_ret"].append(out["ep_ret_norm"].mean())
                stats["term"].append(out["term"].float().sum())
                stats["done"].append(out["done"].float().sum())

    stats = {"r": [], "ep_len": [], "ep_ret": [], "term": [], "done": []}
    # Replay is deliberately not archived with checkpoints. Refill after resume too.
    collect(max(args.warmup_steps, args.wm_window, args.hist), stats)
    log_f = open(os.path.join(args.log_dir, "train_log.csv"), "a")
    if start_it == 0:
        log_f.write("iteration,wall_h,sim_steps,wm_loss,wm_err8,pi_loss,v_loss,imag_rew,pi_gradnorm,imag_survival,sim_rew,ep_len,ep_ret_norm,term_frac,it_per_s,lr\n")
    t_start = time.time() - wall_offset
    t_log = time.time()

    def save_checkpoints(iteration, *, save_last, save_snapshot):
        ck = {"wm": wm.state_dict(), "pi": pi.state_dict(), "critic": critic.state_dict(), "opt_wm": opt_wm.state_dict(),
              "opt_pi": opt_pi.state_dict(), "opt_v": opt_v.state_dict(), "iteration": iteration,
              "wall_time": time.time() - t_start, "sim_steps": sim_steps, "args": vars(args),
              "contract": asdict(contract), "storage_policy": STORAGE_POLICY,
              "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}  # fmt: skip

        def atomic_save(payload, path):
            with open(path + ".tmp", "wb") as output:
                torch.save(payload, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(path + ".tmp", path)

        if save_last:
            atomic_save(ck, os.path.join(args.log_dir, "last.pt"))
        if save_snapshot:
            small = {k: ck[k] for k in ("pi", "wm", "iteration", "wall_time", "sim_steps", "args", "saved_at", "contract", "storage_policy")}
            atomic_save(small, os.path.join(args.log_dir, f"ckpt_{iteration:06d}.pt"))

    step_acc = 0.0
    agg = {"wm": [], "wm8": [], "pi": [], "v": [], "ir": [], "gn": [], "surv": []}
    completed_it = start_it
    for it in range(start_it, args.iterations):
        if stop_signal is not None:
            break
        lr = lr_at(it)
        for o in (opt_wm, opt_pi, opt_v):
            for gparam in o.param_groups:
                gparam["lr"] = lr
        step_acc += 1.0 / args.utd
        n = int(step_acc)
        step_acc -= n
        prof = PROFILE and it % 20 == 0 and it > args.wm_only_iters + 5
        if prof:
            torch.cuda.synchronize(); tp0 = time.time()
        collect(n, stats)
        if prof:
            torch.cuda.synchronize(); tp1 = time.time()
        for _ in range(args.wm_batches):
            l, e8 = wm_update()
        if prof:
            torch.cuda.synchronize(); tp2 = time.time()
        agg["wm"].append(l), agg["wm8"].append(e8)
        if it >= args.wm_only_iters:
            pl, vl, ir, gn, surv = policy_update()
            if prof:
                torch.cuda.synchronize(); tp3 = time.time()
                print(f"[prof] collect {1e3*(tp1-tp0):.0f} ms ({n} steps) | wm {1e3*(tp2-tp1):.0f} ms | policy+critic {1e3*(tp3-tp2):.0f} ms", flush=True)
            agg["pi"].append(pl), agg["v"].append(vl), agg["ir"].append(ir), agg["gn"].append(gn), agg["surv"].append(surv)
        if (it + 1) % args.log_every == 0:
            mean = lambda x: float(sum(float(v) for v in x) / max(len(x), 1))  # noqa: E731
            ips = args.log_every / (time.time() - t_log)
            t_log = time.time()
            wall_h = (time.time() - t_start) / 3600
            term_frac = float(sum(float(v) for v in stats["term"]) / max(sum(float(v) for v in stats["done"]), 1))
            row = [it + 1, wall_h, sim_steps, mean(agg["wm"]), mean(agg["wm8"]), mean(agg["pi"]), mean(agg["v"]), mean(agg["ir"]),
                   mean(agg["gn"]), mean(agg["surv"]), mean(stats["r"]), mean(stats["ep_len"]), mean(stats["ep_ret"]), term_frac, ips, lr]  # fmt: skip
            log_f.write(",".join(f"{x:.6g}" if isinstance(x, float) else str(x) for x in row) + "\n")
            log_f.flush()
            print(f"it {it + 1} | {wall_h:.3f} h | wm {row[3]:.4f} e8 {row[4]:.4f} | pi {row[5]:.3f} v {row[6]:.4f} imag_r {row[7]:.3f} surv {row[9]:.3f} "
                  f"| sim_r {row[10]:.3f} ep_len {row[11]:.1f} ep_ret {row[12]:.3f} term {term_frac:.2f} | {ips:.2f} it/s", flush=True)  # fmt: skip
            stats = {k: [] for k in stats}
            agg = {k: [] for k in agg}
        completed_it = it + 1
        final_iteration = completed_it == args.iterations
        save_last = completed_it % args.last_every == 0 or final_iteration
        save_snapshot = completed_it % args.ckpt_every == 0 or final_iteration
        if not args.no_checkpoint and (save_last or save_snapshot):
            save_checkpoints(completed_it, save_last=save_last, save_snapshot=save_snapshot)

    if stop_signal is not None:
        if not args.no_checkpoint:
            save_checkpoints(completed_it, save_last=True, save_snapshot=False)
        checkpoint_status = "checkpoint disabled (--no_checkpoint)" if args.no_checkpoint else "last.pt saved atomically on server storage"
        print(f"[stop] {signal.Signals(stop_signal).name}: stopped after iteration {completed_it}; {checkpoint_status}", flush=True)

    log_f.close()
    env.close()
