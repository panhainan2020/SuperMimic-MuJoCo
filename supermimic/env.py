"""SuperMimic tracking on native MuJoCo and MJLab physics.

``mujoco`` uses native CPU MuJoCo for small, inspectable validation runs;
``mjlab`` uses MJLab's MuJoCo-Warp GPU simulator for batched training. Both
compile the same scene and use the same joint-name mapping. The upstream/paper
profiles use native position PD.
The task, reset sampler and analytic MDP remain independent of either backend.
No data, weights, replay or other training artifacts are downloaded or uploaded.
"""

from __future__ import annotations

import copy
from contextlib import nullcontext
from dataclasses import dataclass

import numpy as np
import torch

from .mdp import MAX_STEP_REWARD, MDP, flatten_state
from .motion import CONTROL_DT, MotionLib
from .rotations import mat_to_quat, quat_to_mat, so3_exp
from .robot import DEFAULT_ROBOT
from .robot_contract import RobotContract, load_contract, make_mjlab_config


@dataclass(frozen=True)
class SimCfg:
    device: str
    backend: str
    contract: RobotContract
    seed: int = 0


def make_sim(device: str, args) -> SimCfg:
    """Resolve the local shared physics contract without launching Isaac Lab."""
    backend = getattr(args, "backend", "mujoco")
    if backend not in {"mujoco", "mjlab"}:
        raise ValueError(f"Unknown simulation backend: {backend}")
    if backend == "mjlab" and torch.device(device).type != "cuda":
        raise ValueError("The mjlab backend requires a CUDA device; use mujoco for CPU validation")
    contract = load_contract(getattr(args, "profile", "upstream"),
                             robot=getattr(args, "robot", DEFAULT_ROBOT),
                             xml_path=getattr(args, "xml_path", None))
    if abs(contract.control_dt - CONTROL_DT) > 1e-9:
        raise ValueError("Motion, reward and dynamics use a 50 Hz control clock")
    return SimCfg(str(device), backend, contract, int(getattr(args, "seed", 0)))


def launch_simulation(sim_cfg: SimCfg, args=None):
    """Compatibility context: MuJoCo does not need an external application."""
    return nullcontext(sim_cfg)


def _model_indices(model, names):
    """Map named G1 joints into the compiled scene; never assume XML order."""
    import mujoco

    joints = np.asarray([model.joint(f"robot/{n}").id for n in names])
    if any(model.jnt_type[j] != mujoco.mjtJoint.mjJNT_HINGE for j in joints):
        raise ValueError("The shared robot contract requires 29 scalar hinge joints")
    free = np.flatnonzero(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)
    if len(free) != 1:
        raise ValueError("Expected exactly one free root joint in the shared scene")
    actuators = []
    for j in joints:
        ids = np.flatnonzero((model.actuator_trnid[:, 0] == j) &
                            (model.actuator_trntype == mujoco.mjtTrn.mjTRN_JOINT))
        if len(ids) != 1:
            raise ValueError(f"Expected one actuator for joint {model.joint(int(j)).name}")
        actuators.append(int(ids[0]))
    robot_bodies = np.asarray([i for i in range(model.nbody) if model.body(i).name.startswith("robot/")])
    robot_geoms = np.flatnonzero(np.isin(model.geom_bodyid, robot_bodies))
    return dict(joints=joints, q=model.jnt_qposadr[joints], v=model.jnt_dofadr[joints],
                actuators=np.asarray(actuators), root_q=int(model.jnt_qposadr[free[0]]),
                root_v=int(model.jnt_dofadr[free[0]]), torso=model.body("robot/torso_link").id,
                robot_geoms=robot_geoms,
                ground_geoms=np.flatnonzero(~np.isin(model.geom_bodyid, robot_bodies)))


class _NativeMujoco:
    """Independent native models allow physical per-environment randomization."""

    def __init__(self, cfg: SimCfg, n: int):
        import mujoco
        from mjlab.scene import Scene

        self.device, self.contract = cfg.device, cfg.contract
        scene_cfg = make_mjlab_config(cfg.contract, n, seed=cfg.seed)
        self.scene = Scene(scene_cfg.scene, device="cpu")
        model = self.scene.compile()
        scene_cfg.sim.mujoco.apply(model)
        self.idx = _model_indices(model, cfg.contract.joint_names)
        self.models = [model] + [copy.copy(model) for _ in range(n - 1)]
        self.data = [mujoco.MjData(m) for m in self.models]
        self.default_com = model.body_ipos[self.idx["torso"]].copy()
        self.sim = self
        self.robot = self.scene["robot"]

    def randomize(self, xi: torch.Tensor, eval_mode: bool, env_ids=None):
        import mujoco

        contexts = xi.detach().cpu().numpy()
        ids = range(len(self.data)) if env_ids is None else env_ids.detach().cpu().tolist()
        for index in ids:
            model, data, context = self.models[index], self.data[index], contexts[index]
            model.geom_friction[self.idx["ground_geoms"], 0] = 1.0 if eval_mode else 0.3
            model.geom_friction[self.idx["robot_geoms"], 0] = context[0]
            model.body_ipos[self.idx["torso"]] = self.default_com + context[30:33]
            mujoco.mj_setConst(model, data)

    def state(self):
        iq, iv = self.idx["root_q"], self.idx["root_v"]
        qpos = torch.as_tensor(np.stack([d.qpos.copy() for d in self.data]), dtype=torch.float32, device=self.device)
        qvel = torch.as_tensor(np.stack([d.qvel.copy() for d in self.data]), dtype=torch.float32, device=self.device)
        R = quat_to_mat(qpos[:, iq + 3:iq + 7])
        # MuJoCo free-joint linear velocity is world, angular velocity is body.
        w = (R @ qvel[:, iv + 3:iv + 6, None]).squeeze(-1)
        return qpos[:, iq:iq + 3], R, qvel[:, iv:iv + 3], w, qpos[:, self.idx["q"]], qvel[:, self.idx["v"]]

    def reset(self, env_ids, S):
        import mujoco

        p, R, v, w, q, qd = S
        quat = mat_to_quat(R)
        wb = (R.transpose(-1, -2) @ w.unsqueeze(-1)).squeeze(-1)
        arrays = [x.detach().cpu().numpy() for x in (p, quat, v, wb, q, qd)]
        iq, iv = self.idx["root_q"], self.idx["root_v"]
        for row, env_id in enumerate(env_ids.detach().cpu().tolist()):
            model, data = self.models[env_id], self.data[env_id]
            mujoco.mj_resetData(model, data)
            pp, rr, vv, ww, qq, dd = (x[row] for x in arrays)
            data.qpos[iq:iq + 3], data.qpos[iq + 3:iq + 7] = pp, rr
            data.qvel[iv:iv + 3], data.qvel[iv + 3:iv + 6] = vv, ww
            data.qpos[self.idx["q"]], data.qvel[self.idx["v"]] = qq, dd
            data.ctrl[self.idx["actuators"]] = qq
            mujoco.mj_forward(model, data)

    def step(self, target, active=None):
        import mujoco

        targets = target.detach().cpu().numpy()
        ids = range(len(self.data)) if active is None else active.nonzero().flatten().cpu().tolist()
        for i in ids:
            model, data = self.models[i], self.data[i]
            # Native MuJoCo position actuators integrate PD damping implicitly.
            # ctrl is an angle target, never a Python-computed torque.
            data.ctrl[self.idx["actuators"]] = targets[i]
            for _ in range(self.contract.decimation):
                mujoco.mj_step(model, data)
            mujoco.mj_forward(model, data)

    def forward(self):
        import mujoco

        for model, data in zip(self.models, self.data):
            mujoco.mj_forward(model, data)

    def close(self):
        pass


class _MjlabMujoco:
    """MJLab scene and actuator API, without its task/reward/reset managers."""

    def __init__(self, cfg: SimCfg, n: int):
        from mjlab.scene import Scene
        from mjlab.sim import Simulation

        self.device, self.contract = cfg.device, cfg.contract
        scene_cfg = make_mjlab_config(cfg.contract, n, seed=cfg.seed)
        self.scene = Scene(scene_cfg.scene, device=cfg.device)
        self.sim = Simulation(n, scene_cfg.sim, spec=self.scene.spec, device=cfg.device)
        self.scene.initialize(mj_model=self.sim.mj_model, model=self.sim.model, data=self.sim.data)
        self.robot = self.scene["robot"]
        self.idx = _model_indices(self.sim.mj_model, cfg.contract.joint_names)
        # Local articulation order can differ from SDK / policy order.
        self.joint_ids = torch.tensor([self.robot.joint_names.index(n) for n in cfg.contract.joint_names],
                                      device=cfg.device, dtype=torch.long)
        self.q_ids = torch.tensor(self.idx["q"], device=cfg.device)
        self.v_ids = torch.tensor(self.idx["v"], device=cfg.device)
        self.default_com = torch.tensor(self.sim.mj_model.body_ipos[self.idx["torso"]].copy(),
                                         dtype=torch.float32, device=cfg.device)
        # Expand derived constants too: otherwise COM DR silently mixes worlds.
        from mjlab.envs.mdp.dr.body import body_com_offset
        fields = tuple(dict.fromkeys(("geom_friction", *body_com_offset.model_fields)))
        self.sim.expand_model_fields(fields)

    def randomize(self, xi, eval_mode, env_ids=None):
        from mjlab.managers.event_manager import RecomputeLevel

        ids = torch.arange(xi.shape[0], device=self.device) if env_ids is None else env_ids
        ground = torch.as_tensor(self.idx["ground_geoms"], device=self.device)
        robot = torch.as_tensor(self.idx["robot_geoms"], device=self.device)
        self.sim.model.geom_friction[ids[:, None], ground, 0] = 1.0 if eval_mode else 0.3
        self.sim.model.geom_friction[ids[:, None], robot, 0] = xi[ids, :1]
        self.sim.model.body_ipos[ids, self.idx["torso"]] = self.default_com + xi[ids, 30:33]
        self.sim.recompute_constants(RecomputeLevel.set_const)

    def state(self):
        # Reading qpos/qvel avoids stale derived data after MuJoCo integration.
        qpos, qvel = self.sim.data.qpos, self.sim.data.qvel
        iq, iv = self.idx["root_q"], self.idx["root_v"]
        R = quat_to_mat(qpos[:, iq + 3:iq + 7].clone())
        w = (R @ qvel[:, iv + 3:iv + 6, None]).squeeze(-1)
        return (qpos[:, iq:iq + 3].clone(), R, qvel[:, iv:iv + 3].clone(), w,
                qpos[:, self.q_ids].clone(), qvel[:, self.v_ids].clone())

    def reset(self, env_ids, S):
        p, R, v, w, q, qd = S
        self.sim.reset(env_ids)
        self.scene.reset(env_ids)
        self.robot.write_root_link_pose_to_sim(torch.cat((p, mat_to_quat(R)), -1), env_ids=env_ids)
        self.robot.write_root_link_velocity_to_sim(torch.cat((v, w), -1), env_ids=env_ids)
        # Entity setters use direct tensor indexing. A column env index gives
        # the intended Cartesian product with the ordered joint-id vector.
        self.robot.write_joint_state_to_sim(q, qd, joint_ids=self.joint_ids, env_ids=env_ids)
        self.robot.set_joint_position_target(q, joint_ids=self.joint_ids, env_ids=env_ids[:, None])
        if self.contract.profile in {"paper", "upstream"}:
            self.scene.write_data_to_sim()
        self.sim.forward()
        self.scene.update(0.0)

    def step(self, target, active=None):
        self.robot.set_joint_position_target(target, joint_ids=self.joint_ids)
        inactive = None if active is None else (~active).nonzero().flatten()
        saved = None
        if inactive is not None and len(inactive):
            saved = [getattr(self.sim.data, name)[inactive].clone() for name in ("qpos", "qvel", "qacc_warmstart")]
        for _ in range(self.contract.decimation):
            self.scene.write_data_to_sim()
            self.sim.step()
            self.scene.update(self.contract.sim_dt)
        if saved is not None:
            for name, value in zip(("qpos", "qvel", "qacc_warmstart"), saved):
                getattr(self.sim.data, name)[inactive] = value
        self.sim.forward()

    def forward(self):
        self.sim.forward()
        self.scene.update(0.0)

    def close(self):
        # No viewer/application is created by this backend.
        pass


class TrackingSim:
    """Batched G1 tracking, preserving the upstream transition dictionary."""

    def __init__(self, sim_cfg: SimCfg, num_envs: int, motion: MotionLib, mdp: MDP, gamma: float = 0.99,
                 eval_mode: bool = False, max_episode_steps: int = 500, reset_noise: bool = True):
        if num_envs < 1:
            raise ValueError("num_envs must be positive")
        if not 0.0 < gamma < 1.0:
            raise ValueError("The return sampler requires 0 < gamma < 1")
        self.device, self.contract = sim_cfg.device, sim_cfg.contract
        settings = dict(self.contract.physics_settings)
        self.context_sampling = settings.get("friction_com_sampling", "episode" if self.contract.profile == "paper" else "startup")
        if self.context_sampling not in {"startup", "episode"} or settings.get("calibration_sampling", "reset") != "reset":
            raise ValueError("Unsupported physical-context sampling contract")
        self.N, self.motion, self.mdp, self.gamma = num_envs, motion, mdp, gamma
        self.eval_mode = eval_mode
        self.max_episode_steps = max_episode_steps if not eval_mode else 10**9
        self.reset_noise = reset_noise and not eval_mode
        self._physics = (_NativeMujoco if sim_cfg.backend == "mujoco" else _MjlabMujoco)(sim_cfg, num_envs)
        self.sim, self.scene, self.robot = self._physics.sim, self._physics.scene, self._physics.robot
        dev = self.device
        self.default_q = torch.tensor(self.contract.default_q, dtype=torch.float32, device=dev)
        self.alpha = torch.tensor(self.contract.action_scale, dtype=torch.float32, device=dev)
        if not torch.allclose(mdp.default_q, self.default_q):
            raise ValueError("MDP default_q does not match the selected controller profile")
        self.torso_id = self._physics.idx["torso"]
        # xi = floor/robot sliding friction, joint calibration offsets, torso COM.
        self.xi = torch.zeros(num_envs, 33, device=dev)
        if eval_mode:
            self.xi[:, 0] = 1.0
        elif self.context_sampling == "startup":
            self.xi[:, 0].uniform_(0.3, 1.2)
            self.xi[:, 30].uniform_(-0.025, 0.025)
            self.xi[:, 31:33].uniform_(-0.05, 0.05)
        if eval_mode or self.context_sampling == "startup":
            self._physics.randomize(self.xi, eval_mode)
        self.f = torch.zeros(num_envs, dtype=torch.long, device=dev)
        self.ep_step = torch.zeros_like(self.f)
        self.a_prev = torch.zeros(num_envs, 29, device=dev)
        self.start_bin = torch.zeros_like(self.f)
        self.ep_disc_ret = torch.zeros(num_envs, device=dev)
        self.ep_ret = torch.zeros(num_envs, device=dev)
        self.G_max = MAX_STEP_REWARD / (1 - gamma)
        self.bin_G = torch.zeros(motion.num_bins, device=dev)
        self.bin_w_avg = torch.full((motion.num_bins,), 1.0 / motion.num_bins, device=dev)
        self.done_eval = torch.zeros(num_envs, dtype=torch.bool, device=dev)
        self.failed_eval = torch.zeros_like(self.done_eval)
        self.reset(torch.arange(num_envs, device=dev))

    def state(self):
        return self._physics.state()

    def sample_frames(self, n: int) -> tuple[torch.Tensor, torch.Tensor]:
        m = self.motion
        soft = torch.softmax(-25.0 * self.bin_G / self.G_max, 0)
        self.bin_w_avg.mul_(0.999).add_(0.001 * soft)
        probs = 0.5 / m.num_bins + 0.4 * soft + 0.1 * self.bin_w_avg / self.bin_w_avg.sum()
        # Defensive masking also supports older libraries with final-frame bins.
        valid = m.bin_start < m.clip_end[m.bin_clip]
        probs = probs * valid
        if not bool(valid.any()):
            raise ValueError("Reference clips must contain at least one transition")
        bins = torch.multinomial(probs, n, replacement=True)
        start = m.bin_start[bins]
        end = torch.minimum(start + 50, m.clip_end[m.bin_clip[bins]])
        f = start + (torch.rand(n, device=self.device) * (end - start).float()).long()
        return f, bins

    def reset(self, env_ids: torch.Tensor, frames: torch.Tensor | None = None):
        env_ids = torch.as_tensor(env_ids, dtype=torch.long, device=self.device)
        if len(env_ids) == 0:
            return
        n, dev = len(env_ids), self.device
        if frames is None:
            frames, bins = self.sample_frames(n)
        else:
            frames = torch.as_tensor(frames, dtype=torch.long, device=dev)
            if frames.shape != (n,) or bool(((frames < 0) | (frames >= self.motion.num_frames)).any()):
                raise ValueError("One valid reference frame is required per reset environment")
            bins = self.motion.frame_bin[frames]
        p, R, v, w, q, qd = (x.clone() for x in self.motion.ref_state(frames))
        if self.reset_noise:
            p += torch.empty(n, 3, device=dev).uniform_(-1, 1) * torch.tensor([0.05, 0.05, 0.01], device=dev)
            rv = torch.empty(n, 3, device=dev).uniform_(-1, 1) * torch.tensor([0.1, 0.1, 0.2], device=dev)
            R = so3_exp(rv) @ R
            v += torch.empty(n, 3, device=dev).uniform_(-1, 1) * torch.tensor([0.5, 0.5, 0.2], device=dev)
            w += torch.empty(n, 3, device=dev).uniform_(-1, 1) * torch.tensor([0.52, 0.52, 0.78], device=dev)
            q += torch.empty_like(q).uniform_(-0.1, 0.1)
        q = torch.clamp(q, self.mdp.kin.q_lo, self.mdp.kin.q_hi)
        if not self.eval_mode and self.context_sampling == "episode":
            # Paper Sec. 3.2 defines xi as per-episode context. Resample only
            # worlds beginning an episode, never inject interval pushes.
            self.xi[env_ids, 0] = torch.empty(n, device=dev).uniform_(0.3, 1.2)
            self.xi[env_ids, 30] = torch.empty(n, device=dev).uniform_(-0.025, 0.025)
            self.xi[env_ids, 31:33] = torch.empty(n, 2, device=dev).uniform_(-0.05, 0.05)
            self.xi[env_ids, 1:30] = torch.empty(n, 29, device=dev).uniform_(-0.01, 0.01)
            self._physics.randomize(self.xi, eval_mode=False, env_ids=env_ids)
        self._physics.reset(env_ids, (p, R, v, w, q, qd))
        self.f[env_ids], self.start_bin[env_ids] = frames, bins
        self.ep_step[env_ids] = 0
        self.a_prev[env_ids] = 0.0
        self.ep_disc_ret[env_ids], self.ep_ret[env_ids] = 0.0, 0.0
        self.done_eval[env_ids], self.failed_eval[env_ids] = False, False
        if not self.eval_mode and self.context_sampling == "startup":
            self.xi[env_ids, 1:30] = torch.empty(n, 29, device=dev).uniform_(-0.01, 0.01)

    def refresh(self):
        """Refresh derived MuJoCo body states after external state writes."""
        self._physics.forward()

    def step(self, a: torch.Tensor) -> dict:
        if a.shape != (self.N, 29):
            raise ValueError(f"Expected action shape {(self.N, 29)}, got {tuple(a.shape)}")
        a = a.detach().to(self.device)
        if self.contract.action_clip is not None:
            a = a.clamp(-self.contract.action_clip, self.contract.action_clip)
        S, f, xi = self.state(), self.f.clone(), self.xi.clone()
        a_prev, ep_step = self.a_prev.clone(), self.ep_step.clone()
        active = ~self.done_eval if self.eval_mode else None
        target = self.default_q + xi[:, 1:30] + self.alpha * a
        self._physics.step(target, active)
        S1 = self.state()
        clip_end = self.motion.clip_end[self.motion.clip_id[f]]
        # Clamp *before* reward/termination lookup, also for completed eval envs.
        f1 = torch.minimum(f + 1, clip_end)
        if self.eval_mode:
            f1 = torch.where(active, f1, f)
        r, terms = self.mdp.reward(S1, f1, a, a_prev, terms=True)
        term = self.mdp.termination(S1, f1)
        timeout = (f1 >= clip_end) | (ep_step + 1 >= self.max_episode_steps)
        if self.eval_mode:
            r = torch.where(active, r, 0.0)
            term = term & active
            done = term | timeout | ~active
        else:
            done = term | timeout
        out = {"s": flatten_state(S), "a": a.clone(), "a_prev": a_prev, "f": f,
               "s1": flatten_state(S1), "r": r, "term": term, "done": done,
               "ep_step": ep_step, "xi": xi, "terms": terms}
        self.ep_disc_ret += (self.gamma ** ep_step.float()) * r
        self.ep_ret += r
        self.f = f1
        if self.eval_mode:
            self.ep_step = ep_step + active.long()
            self.a_prev = torch.where(active[:, None], a, a_prev)
            self.failed_eval |= term
            self.done_eval |= done
            return out
        self.ep_step, self.a_prev = ep_step + 1, a.clone()
        ids = done.nonzero(as_tuple=False).squeeze(-1)
        if len(ids):
            T = self.ep_step[ids].float()
            boot = torch.where(term[ids], 0.0, (self.gamma**T) * (self.ep_ret[ids] / T) / (1 - self.gamma))
            G, b = self.ep_disc_ret[ids] + boot, self.start_bin[ids]
            # Repeated bins occur in parallel resets: aggregate before one EMA.
            sums, counts = torch.zeros_like(self.bin_G), torch.zeros_like(self.bin_G)
            sums.scatter_add_(0, b, G)
            counts.scatter_add_(0, b, torch.ones_like(G))
            used = counts > 0
            self.bin_G[used] = 0.8 * self.bin_G[used] + 0.2 * sums[used] / counts[used]
            out["ep_len"], out["ep_ret_norm"] = T, self.ep_ret[ids] / (T * MAX_STEP_REWARD)
            self.reset(ids)
        return out

    def close(self):
        self._physics.close()
