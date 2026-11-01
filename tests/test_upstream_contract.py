"""Small CPU checks for the pinned upstream physics contract; no training/files."""

from dataclasses import asdict, replace
from types import SimpleNamespace
import unittest

import mujoco
import numpy as np
import torch

from supermimic.env import SimCfg, _NativeMujoco, make_sim
from supermimic.robot_contract import load_contract, make_mjlab_config, assert_contract_compatible


class UpstreamContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_contract("upstream")

    def test_default_profile_and_scene_are_upstream(self):
        contract = load_contract(xml_path=self.contract.xml_path)
        sim = make_sim("cpu", SimpleNamespace(xml_path=contract.xml_path))
        make_mjlab_config(contract, 1)
        self.assertEqual(contract.profile, "upstream")
        self.assertEqual(sim.contract.profile, "upstream")
        self.assertEqual(contract.robot, "g1_29dof")

    def test_native_pd_targets_are_unclipped_and_solver_options_match(self):
        contract = self.contract
        self.assertIsNone(contract.action_clip)
        physics = _NativeMujoco(SimCfg("cpu", "mujoco", contract), 1)
        model = physics.models[0]
        ids = physics.idx["actuators"]
        self.assertFalse(np.any(model.actuator_ctrllimited[ids]))
        np.testing.assert_allclose(model.actuator_biasprm[ids, 2], -np.asarray(contract.kd))
        self.assertEqual(model.opt.integrator, mujoco.mjtIntegrator.mjINT_IMPLICITFAST)
        self.assertEqual(model.opt.solver, mujoco.mjtSolver.mjSOL_NEWTON)
        self.assertEqual(model.opt.iterations, 100)
        self.assertEqual(model.opt.ls_iterations, 50)
        self.assertEqual(model.opt.tolerance, 1e-6)
        self.assertEqual(model.opt.impratio, 1.0)
        self.assertEqual(model.opt.ccd_iterations, 35)
        self.assertTrue(model.opt.disableflags & mujoco.mjtDisableBit.mjDSBL_MULTICCD)
        q = torch.tensor(contract.default_q, dtype=torch.float32)[None]
        physics.reset(torch.tensor([0]), (
            torch.tensor([[0.0, 0.0, 1.5]]), torch.eye(3)[None],
            torch.zeros(1, 3), torch.zeros(1, 3), q, torch.zeros_like(q),
        ))
        target = q + 100.0
        physics.step(target)
        np.testing.assert_allclose(physics.data[0].ctrl[ids], target[0].numpy())
        self.assertTrue(all(torch.isfinite(value).all() for value in physics.state()))

    def test_checkpoint_metadata_is_the_factory_settings_source(self):
        settings = dict(self.contract.physics_settings)
        self.assertEqual(settings["friction_com_sampling"], "startup")
        self.assertEqual(settings["calibration_sampling"], "reset")
        self.assertFalse(settings["self_collision"])
        settings["iterations"] = 11
        altered = replace(self.contract, physics_settings=tuple(settings.items()))
        self.assertNotEqual(asdict(self.contract), asdict(altered))
        config = make_mjlab_config(altered, 1)
        self.assertEqual(config.sim.mujoco.iterations, 11)
        self.assertEqual(config.sim.nconmax, settings["nconmax"])
        self.assertEqual(config.sim.njmax, settings["njmax"])
        self.assertEqual(config.sim.ls_parallel, settings["ls_parallel"])

    def test_self_collision_opt_in_changes_compiled_masks_and_checkpoint_identity(self):
        enabled = make_sim("cpu", SimpleNamespace(self_collision=True)).contract
        self.assertTrue(dict(enabled.physics_settings)["self_collision"])
        self.assertEqual(enabled.kp, self.contract.kp)
        with self.assertRaises(ValueError):
            assert_contract_compatible(self.contract.metadata(), enabled)
        for contract, expected in ((self.contract, False), (enabled, True)):
            physics = _NativeMujoco(SimCfg("cpu", "mujoco", contract), 1)
            model = physics.models[0]
            robot = np.array([model.geom(i).name.startswith("robot/") for i in range(model.ngeom)]) & (model.geom_contype != 0)
            self.assertTrue(np.any(robot))
            self.assertEqual(bool(np.any(model.geom_conaffinity[robot] & 1)), expected)
            ground = np.array([model.geom(i).name == "terrain" for i in range(model.ngeom)]) & (model.geom_conaffinity != 0)
            self.assertTrue(np.any(ground))


if __name__ == "__main__":
    unittest.main()
