"""Physical backend regressions using local assets and tiny synthetic clips.

Native checks run with normal unittest discovery. Opt into the two-environment
CUDA checks with SUPERMIMIC_TEST_CUDA=1; no training, downloads, weights, replay,
archive transfers or network access are performed. Synthetic CSV fixtures live
in a TemporaryDirectory and are removed. Durable reports belong under the
configured SUPERMIMIC_EXPERIMENT_ROOT, never in this source repository.
"""

from dataclasses import replace
from functools import lru_cache
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from supermimic.env import SimCfg, TrackingSim, _NativeMujoco
from supermimic.kinematics import G1Kinematics
from supermimic.mdp import MDP, RewardCfg, flatten_state
from supermimic.motion import MotionLib
from supermimic.rotations import so3_exp
from supermimic.robot_contract import load_contract


@lru_cache(maxsize=2)
def _contract(robot="g1_29dof"):
    return load_contract(robot=robot)


def _array(x):
    # MJLab wraps tensors in a Warp interop proxy, forwarding Tensor methods.
    return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)


def _reset_state(contract, device):
    q = torch.tensor(contract.default_q, device=device).repeat(2, 1)
    q += 0.01 * torch.sin(torch.arange(58, device=device).reshape(2, 29))
    qd = 0.2 * torch.cos(torch.arange(58, device=device).reshape(2, 29))
    return (
        torch.tensor([[0.2, -0.4, 0.8], [-0.5, 0.8, 1.2]], device=device),
        so3_exp(torch.tensor([[0.1, 0.2, 0.3], [-0.3, 0.1, -0.2]], device=device)),
        torch.tensor([[0.1, -0.2, 0.05], [0.3, 0.1, -0.2]], device=device),
        torch.tensor([[0.1, 0.2, 0.3], [-0.3, 0.2, -0.1]], device=device),
        q, qd,
    )


class _BackendChecks:
    robot = "g1_29dof"

    @classmethod
    def setUpClass(cls):
        cls.cfg = SimCfg(cls.device, cls.backend, _contract(cls.robot), seed=17)
        cls.tmp = tempfile.TemporaryDirectory(prefix="supermimic_backend_test_")
        cls.addClassCleanup(cls.tmp.cleanup)
        # 50 Hz sources remove resampling ambiguity from boundary assertions.
        files = []
        for name, length in (("short", 5), ("long", 40)):
            raw = np.zeros((length, 36), dtype=np.float32)
            raw[:, 2], raw[:, 6] = 0.8, 1.0
            raw[:, 7:] = cls.cfg.contract.default_q
            path = Path(cls.tmp.name) / f"{name}.csv"
            np.savetxt(path, raw, delimiter=",")
            files.append(str(path))
        kin = G1Kinematics(cls.device, xml_path=cls.cfg.contract.xml_path)
        cls.motion = MotionLib(files, kin, cls.device, src_fps=50)
        # This test isolates clip completion from task failure thresholds.
        mdp = MDP(kin, cls.motion, torch.tensor(cls.cfg.contract.default_q, device=cls.device),
                  cfg=RewardCfg(term_height=10.0, term_tilt=10.0))
        cls.env = TrackingSim(cls.cfg, 2, cls.motion, mdp, eval_mode=True)
        cls.addClassCleanup(cls.env.close)
        cls.physics = cls.env._physics

    def setUp(self):
        self.env.xi.zero_()
        self.env.xi[:, 0] = 1.0
        self.physics.randomize(self.env.xi, eval_mode=True)
        self.ids = torch.arange(2, device=self.device)

    def test_reset_preserves_world_velocities_and_joint_order(self):
        wanted = _reset_state(self.cfg.contract, self.device)
        self.physics.reset(self.ids, wanted)
        for actual, expected in zip(self.physics.state(), wanted):
            torch.testing.assert_close(actual, expected, atol=2e-7, rtol=2e-6)
        # Inspect MuJoCo's generalized velocity as an independent convention check.
        iv = self.physics.idx["root_v"]
        raw = (np.stack([d.qvel.copy() for d in self.physics.data]) if self.backend == "mujoco"
               else _array(self.physics.sim.data.qvel))
        expected_local_omega = (wanted[1].transpose(-1, -2) @ wanted[3].unsqueeze(-1)).squeeze(-1)
        np.testing.assert_allclose(raw[:, iv:iv + 3], _array(wanted[2]), atol=1e-7)
        np.testing.assert_allclose(raw[:, iv + 3:iv + 6], _array(expected_local_omega), atol=1e-7)
        # A partial reset must not overwrite the other environment's coordinates.
        before = flatten_state(self.physics.state())[0].clone()
        replacement = tuple(x[0:1] for x in wanted)
        self.physics.reset(self.ids[1:2], replacement)
        torch.testing.assert_close(flatten_state(self.physics.state())[0], before, atol=0, rtol=0)
        for actual, expected in zip(self.physics.state(), replacement):
            torch.testing.assert_close(actual[1:2], expected, atol=2e-7, rtol=2e-6)

    def test_xi_friction_and_com_modify_independent_models(self):
        xi = torch.zeros(2, 33, device=self.device)
        xi[:, 0] = torch.tensor([0.4, 1.1], device=self.device)
        xi[:, 30:33] = torch.tensor([[0.01, -0.02, 0.03], [-0.02, 0.04, -0.01]], device=self.device)
        self.physics.randomize(xi, eval_mode=False)
        idx = self.physics.idx
        if self.backend == "mujoco":
            friction = np.stack([m.geom_friction.copy() for m in self.physics.models])
            com = np.stack([m.body_ipos[idx["torso"]].copy() for m in self.physics.models])
        else:
            friction = _array(self.physics.sim.model.geom_friction)
            com = _array(self.physics.sim.model.body_ipos[:, idx["torso"]])
        expected_mu = np.broadcast_to(_array(xi[:, :1]), (2, len(idx["robot_geoms"])))
        np.testing.assert_allclose(friction[:, idx["robot_geoms"], 0], expected_mu, atol=1e-7)
        np.testing.assert_allclose(friction[:, idx["ground_geoms"], 0], 0.3, atol=1e-7)
        expected_com = _array(self.physics.default_com) + _array(xi[:, 30:33])
        np.testing.assert_allclose(com, expected_com, atol=1e-7)
        # Reapplication is relative to the nominal COM, not a cumulative drift.
        self.physics.randomize(xi, eval_mode=False)
        repeated = (np.stack([m.body_ipos[idx["torso"]].copy() for m in self.physics.models])
                    if self.backend == "mujoco" else _array(self.physics.sim.model.body_ipos[:, idx["torso"]]))
        np.testing.assert_array_equal(repeated, com)

    def test_joint_calibration_offsets_reach_the_actuators(self):
        # Same initial state, same action, different calibration -> different motion.
        frame = self.motion.clip_start[1].expand(2)
        self.env.reset(self.ids, frame)
        self.env.xi[1, 1] = 0.01
        out = self.env.step(torch.zeros(2, 29, device=self.device))
        self.assertAlmostEqual(float(out["xi"][1, 1]), 0.01, places=7)
        self.assertGreater(float((out["s1"][1, 13:42] - out["s1"][0, 13:42]).abs().max()), 1e-5)
        self.assertTrue(bool(torch.isfinite(out["s1"]).all()))

    def test_completed_clip_freezes_while_longer_clip_advances(self):
        starts = torch.stack((self.motion.clip_end[0] - 1, self.motion.clip_start[1]))
        self.env.reset(self.ids, starts)
        zero = torch.zeros(2, 29, device=self.device)
        out = self.env.step(zero)
        self.assertTrue(bool(out["done"][0]))
        self.assertFalse(bool(out["term"][0]))
        frozen = flatten_state(self.env.state())[0].clone()
        frozen_frame, frozen_step = int(self.env.f[0]), int(self.env.ep_step[0])
        for _ in range(20):
            out = self.env.step(zero)
            torch.testing.assert_close(flatten_state(self.env.state())[0], frozen, atol=0, rtol=0)
            self.assertEqual(int(self.env.f[0]), frozen_frame)
            self.assertEqual(int(self.env.ep_step[0]), frozen_step)
            self.assertEqual(float(out["r"][0]), 0.0)
            self.assertTrue(bool(out["done"][0]))
            self.assertFalse(bool(out["term"][0]))
            self.assertEqual(self.motion.clip_id[self.env.f].tolist(), [0, 1])
            self.assertTrue(bool(torch.isfinite(out["s1"]).all()))
        self.assertEqual(int(self.env.f[1]), int(starts[1]) + 21)
        self.assertFalse(bool(self.env.done_eval[1]))
        # Caller may reset an evaluated environment for a new batch.
        self.env.reset(self.ids[:1], self.motion.clip_start[:1])
        self.assertFalse(bool(self.env.done_eval[0]))
        self.assertEqual(int(self.env.ep_step[0]), 0)


class NativeBackendTests(_BackendChecks, unittest.TestCase):
    backend, device = "mujoco", "cpu"


class RevisionNativeBackendTests(NativeBackendTests):
    robot = "g1_29dof_rev_1_0"


@unittest.skipUnless(os.environ.get("SUPERMIMIC_TEST_CUDA") == "1", "Set SUPERMIMIC_TEST_CUDA=1 for GPU checks")
class CudaBackendTests(_BackendChecks, unittest.TestCase):
    backend, device = "mjlab", "cuda:0"

    @classmethod
    def setUpClass(cls):
        if not torch.cuda.is_available():
            raise unittest.SkipTest("CUDA is unavailable")
        super().setUpClass()

    def test_ten_control_steps_agree_with_native_mujoco(self):
        native = _NativeMujoco(replace(self.cfg, backend="mujoco", device="cpu"), 2)
        self.addCleanup(native.close)
        q = torch.tensor(self.cfg.contract.default_q).repeat(2, 1)
        state = (
            torch.tensor([[0.0, 0.0, 0.8], [0.0, 0.0, 1.2]]),
            so3_exp(torch.tensor([[0.0, 0.0, 0.3], [0.1, 0.2, -0.3]])),
            torch.tensor([[0.1, -0.2, 0.05], [0.3, 0.1, -0.2]]),
            torch.tensor([[0.1, 0.2, 0.3], [-0.3, 0.2, -0.1]]),
            q, torch.zeros_like(q),
        )
        xi = torch.zeros(2, 33)
        xi[:, 0] = torch.tensor([0.4, 1.1])
        xi[1, 30:33] = torch.tensor([0.02, -0.02, 0.03])
        native.randomize(xi, eval_mode=False)
        self.physics.randomize(xi.to(self.device), eval_mode=False)
        native.reset(torch.arange(2), state)
        self.physics.reset(self.ids, tuple(x.to(self.device) for x in state))
        for step in range(10):
            target = q + 0.005 * torch.sin(torch.arange(29) + step)
            native.step(target)
            self.physics.step(target.to(self.device))
            for key, expected, actual in zip(("p", "R", "v", "w", "q", "qd"), native.state(), self.physics.state()):
                with self.subTest(control_step=step + 1, state_component=key):
                    # CPU is float64, GPU float32; contact solvers need a tolerance.
                    atol = 1e-3 if key in {"v", "w", "qd"} else 5e-5
                    torch.testing.assert_close(actual.cpu(), expected, atol=atol, rtol=0)


class RevisionCudaBackendTests(CudaBackendTests):
    """Exercise the alternate robot, including native/GPU agreement."""

    robot = "g1_29dof_rev_1_0"


if __name__ == "__main__":
    unittest.main()
