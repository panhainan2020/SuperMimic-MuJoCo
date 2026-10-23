"""Checkpoint evaluation (paper Appendix F.1) on all motions of the library.

Each motion plays once from its first frame with friction 1.0, no domain randomization, no
observation or action noise. A motion fails if the rollout triggers the training termination.
Normalized return is the undiscounted reward sum divided by its maximum attainable value.

Run as a watcher: ``python supermimic/evaluate.py --run_dir logs/<run> --watch``.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from supermimic.runtime import add_runtime_args, artifact_dir, network_shapes, STORAGE_POLICY

parser = argparse.ArgumentParser()
parser.add_argument("--run_dir", type=str, required=True)
parser.add_argument("--watch", action="store_true")
parser.add_argument("--ckpt", type=str, default=None, help="evaluate one checkpoint")
parser.add_argument("--record", type=str, default=None, help="save trajectories (npz) for rendering")
parser.add_argument("--motion_dir", type=str, required=True, help="existing local motion directory or joblib file")
parser.add_argument("--every", type=int, default=1, help="evaluate every n-th checkpoint")
add_runtime_args(parser)
args = parser.parse_args()
if args.every < 1:
    parser.error("--every must be positive")

import numpy as np
import torch

import supermimic.networks as networks
from supermimic.env import TrackingSim, make_sim, launch_simulation
from supermimic.kinematics import G1Kinematics
from supermimic.mdp import MAX_STEP_REWARD, OBS_DIM, MDP
from supermimic.motion import MotionLib
from supermimic.networks import Policy
from supermimic.robot_contract import assert_contract_compatible, load_contract

torch.backends.cuda.matmul.allow_tf32 = True
dev = args.device
args.run_dir = str(artifact_dir(args.run_dir))
print(STORAGE_POLICY, flush=True)
if args.record:
    artifact_dir(os.path.dirname(os.path.abspath(args.record)))
contract = load_contract(args.profile, robot=args.robot, xml_path=args.xml_path)
kin = G1Kinematics(dev, xml_path=contract.xml_path)
motion = MotionLib.from_dir(args.motion_dir, kin, dev)
mdp = MDP(kin, motion, torch.tensor(contract.default_q, device=dev), observation_mode=args.observation_mode)
OBS_DIM = mdp.obs_dim
C = len(motion.names)


@torch.no_grad()
def evaluate(env: TrackingSim, ck: dict, record: str | None = None) -> dict:
    a_ = ck["args"]
    K, Hh = a_["goal_frames"], a_["hist"]
    for key in ("profile", "observation_mode", "network_size"):
        if a_.get(key) != getattr(args, key):
            raise ValueError(f"Checkpoint {key}={a_.get(key)} differs from evaluation {getattr(args, key)}")
    assert_contract_compatible(ck.get("contract"), contract)
    networks.AMP_DTYPE = torch.bfloat16 if a_.get("amp", "none") == "bf16" else None
    pi = Policy(OBS_DIM, 73 * K, hist=Hh, hidden=network_shapes(args.network_size)[1]).to(dev)
    pi.load_state_dict(ck["pi"])
    pi.eval()
    ids = torch.arange(C, device=dev)
    env.done_eval[:] = False
    env.failed_eval[:] = False
    env.reset(ids, motion.clip_start.clone())
    env.refresh()
    clip_end = motion.clip_end.clone()
    ret = torch.zeros(C, device=dev)
    steps = torch.zeros(C, device=dev)
    hist = None
    traj = {"root_p": [], "root_quat": [], "q": [], "f": [], "alive": []}
    while not bool(env.done_eval.all()):
        S = env.state()
        o = mdp.obs(S, env.a_prev, env.xi, env.f)
        hist = o.unsqueeze(1).repeat(1, Hh, 1) if hist is None else torch.cat((hist[:, 1:], o.unsqueeze(1)), 1)
        a = pi(hist, motion.goal(env.f, K))
        alive = ~env.done_eval.clone()
        if record:
            from supermimic.rotations import mat_to_quat

            traj["root_p"].append(S[0].cpu()), traj["root_quat"].append(mat_to_quat(S[1]).cpu())
            traj["q"].append(S[4].cpu()), traj["f"].append(env.f.cpu().clone()), traj["alive"].append(alive.cpu())
        out = env.step(a)
        ret += torch.where(alive, out["r"], 0.0)
        steps += alive.float()
        # Backend freezes finished clips and clamps frame indices inside each clip.
    norm = ret / ((motion.clip_len - 1).float() * MAX_STEP_REWARD)
    res = {
        "norm_return": norm.mean().item(),
        "norm_return_framew": (ret.sum() / ((motion.clip_len - 1).sum() * MAX_STEP_REWARD)).item(),
        "n_failed": int(env.failed_eval.sum().item()),
        "failed": [motion.names[i] for i in env.failed_eval.nonzero().flatten().tolist()],
        "per_clip": {motion.names[i]: round(norm[i].item(), 4) for i in range(C)},
    }
    if record:
        np.savez_compressed(record, names=np.array(motion.names), **{k: torch.stack(v).numpy() for k, v in traj.items()},
                            ref_root_p=motion.root_p.cpu().numpy(), ref_root_R=motion.root_R.cpu().numpy(), ref_q=motion.q.cpu().numpy(),
                            clip_start=motion.clip_start.cpu().numpy(), clip_len=motion.clip_len.cpu().numpy())  # fmt: skip
    return res


sim_cfg = make_sim(dev, args)
with launch_simulation(sim_cfg, args):
    env = TrackingSim(sim_cfg, C, motion, mdp, eval_mode=True)
    if args.ckpt:
        ck = torch.load(args.ckpt, map_location=dev, weights_only=False)
        res = evaluate(env, ck, args.record)
        json.dump(res, open(os.path.join(args.run_dir, "evaluation.json"), "w"), indent=2)
        print(json.dumps({k: v for k, v in res.items() if k != "per_clip"}, indent=1))
        env.close()
        sys.exit(0)
    out_csv = os.path.join(args.run_dir, "eval.csv")
    done = set()
    if os.path.exists(out_csv):
        done = {int(l.split(",")[0]) for l in open(out_csv).read().strip().splitlines()[1:]}
    else:
        open(out_csv, "w").write("iteration,train_wall_h,saved_at,eval_at,norm_return,norm_return_framew,n_failed,failed\n")
    while True:
        ckpts = sorted(glob.glob(os.path.join(args.run_dir, "ckpt_*.pt")))
        todo = [c for c in ckpts[::args.every] if int(os.path.basename(c)[5:-3]) not in done]
        for c in todo:
            it = int(os.path.basename(c)[5:-3])
            ck = torch.load(c, map_location=dev, weights_only=False)
            t0 = time.time()
            res = evaluate(env, ck)
            line = f"{it},{ck['wall_time'] / 3600:.4f},{ck['saved_at']},{time.strftime('%Y-%m-%d %H:%M:%S')},{res['norm_return']:.4f},{res['norm_return_framew']:.4f},{res['n_failed']},{'|'.join(res['failed'])}\n"
            open(out_csv, "a").write(line)
            json.dump(res, open(c.replace(".pt", "_eval.json"), "w"), indent=1)
            print(f"[eval] it {it} ({ck['wall_time'] / 3600:.2f} h): norm return {res['norm_return']:.4f}, failed {res['n_failed']}/{C} ({time.time() - t0:.0f}s)", flush=True)
            done.add(it)
        if not args.watch:
            break
        time.sleep(60)


    env.close()
