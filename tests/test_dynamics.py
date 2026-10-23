"""Independent MuJoCo FK/velocity checks and differentiable learning checks."""
import tempfile
import unittest
from pathlib import Path

import mujoco
import numpy as np
import torch

from supermimic.kinematics import G1Kinematics
from supermimic.mdp import MDP, flatten_state, normalize_xi, unflatten_state
from supermimic.motion import MotionLib
from supermimic.networks import Policy, WorldModel
from supermimic.robot import G1_JOINT_NAMES, TRACKED_BODIES, default_joint_pos_list, robot_xml_path
from supermimic.rotations import quat_to_mat


class DynamicsTest(unittest.TestCase):
    def test_fk_against_mujoco_with_rotated_moving_root(self):
        self._check_fk('g1_29dof')

    def test_revision_fk_against_mujoco_with_rotated_moving_root(self):
        self._check_fk('g1_29dof_rev_1_0')

    def _check_fk(self, robot):
        rng = np.random.default_rng(4)
        xml = str(robot_xml_path(robot))
        model = mujoco.MjModel.from_xml_path(xml)
        data = mujoco.MjData(model)
        kin = G1Kinematics("cpu", xml_path=xml)
        jids = [model.joint(n).id for n in G1_JOINT_NAMES]
        qa, va = model.jnt_qposadr[jids], model.jnt_dofadr[jids]
        bodies = [model.body(n).id for n in TRACKED_BODIES]
        for _ in range(4):
            data.qpos[:3] = [0.2, -0.4, 1.1]
            quat = rng.normal(size=4)
            data.qpos[3:7] = quat / np.linalg.norm(quat)
            data.qpos[qa] = rng.uniform(-0.2, 0.2, 29)
            data.qvel[:] = rng.normal(scale=0.3, size=model.nv)
            mujoco.mj_forward(model, data)
            t = lambda x: torch.tensor(np.asarray(x).copy(), dtype=torch.float64).unsqueeze(0)
            R = quat_to_mat(t(data.qpos[3:7]))
            S = (t(data.qpos[:3]), R, t(data.qvel[:3]),
                 (R @ t(data.qvel[3:6]).unsqueeze(-1)).squeeze(-1), t(data.qpos[qa]), t(data.qvel[va]))
            kin.axes, kin.off_p, kin.off_R = kin.axes.double(), kin.off_p.double(), kin.off_R.double()
            p, rot, vel, omega = kin.forward(*S)
            p0 = data.xpos[bodies].copy()
            r0 = data.xmat[bodies].reshape(-1, 3, 3).copy()
            np.testing.assert_allclose(p[0].numpy(), p0, atol=2e-7)
            np.testing.assert_allclose(rot[0].numpy(), r0, atol=2e-7)
            dt = 1e-6
            mujoco.mj_integratePos(model, data.qpos, data.qvel, dt)
            mujoco.mj_forward(model, data)
            np.testing.assert_allclose(vel[0].numpy(), (data.xpos[bodies] - p0) / dt, atol=3e-6)
            dr = (data.xmat[bodies].reshape(-1, 3, 3) - r0) / dt
            skew = dr @ r0.transpose(0, 2, 1)
            expected = np.stack((skew[:, 2, 1], skew[:, 0, 2], skew[:, 1, 0]), -1)
            np.testing.assert_allclose(omega[0].numpy(), expected, atol=3e-6)

    def test_policy_gradient_through_frozen_world_model(self):
        torch.manual_seed(3)
        with tempfile.TemporaryDirectory() as tmp:
            raw = np.zeros((61, 36))
            raw[:, 2], raw[:, 6] = 0.8, 1.0
            raw[:, 7:] = default_joint_pos_list()
            np.savetxt(Path(tmp) / "stand.csv", raw, delimiter=",")
            kin = G1Kinematics("cpu")
            motion = MotionLib.from_dir(tmp, kin, "cpu")
            mdp = MDP(kin, motion, torch.tensor(default_joint_pos_list()), observation_mode="paper93")
            legacy = MDP(kin, motion, mdp.default_q, observation_mode="legacy99")
            f = torch.tensor([0, 1])
            S = motion.ref_state(f)
            xi = torch.zeros(2, 33)
            xi[:, 0] = 1
            previous = torch.zeros(2, 29)
            obs = mdp.obs(S, previous, xi, f)
            self.assertEqual(obs.shape[-1], 93)
            self.assertEqual(legacy.obs(S, previous, xi, f).shape[-1], 99)
            reconstructed = unflatten_state(flatten_state(S))
            for actual, wanted in zip(reconstructed, S):
                torch.testing.assert_close(actual, wanted)
            wm = WorldModel(hidden=(32, 32))
            # A nonzero learned dynamics Jacobian, as after the first WM update.
            torch.nn.init.normal_(wm.net[-1].weight, std=1e-3)
            for p in wm.parameters():
                p.requires_grad_(False)
            pi = Policy(93, 73 * 2, hist=2, hidden=(32, 16))
            history = obs[:, None].repeat(1, 2, 1)
            objective = 0
            for _ in range(3):
                action = pi(history, motion.goal(f, 2))
                S = wm.step(S, action, normalize_xi(xi))
                f = f + 1
                objective = objective + mdp.reward(S, f, action, previous).mean()
                history = torch.cat((history[:, 1:], mdp.obs(S, action, xi, f)[:, None]), 1)
                previous = action
            (-objective).backward()
            grads = [p.grad for p in pi.parameters() if p.grad is not None]
            self.assertTrue(all(torch.isfinite(g).all() for g in grads))
            self.assertGreater(sum(g.abs().sum().item() for g in grads), 0)
            self.assertTrue(all(p.grad is None for p in wm.parameters()))


if __name__ == "__main__":
    unittest.main()
