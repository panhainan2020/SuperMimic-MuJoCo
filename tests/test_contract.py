"""Standalone robot selection and checkpoint safety; no external checkout.

The small frozen fixture is the physical metadata of the evaluated 98k policy,
with its absolute installation path sanitized. No weights or data are included.
"""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import unittest

import mujoco
import torch

from supermimic.kinematics import G1Kinematics
from supermimic.robot import ASSET_ROOT, DEFAULT_ROBOT, G1_JOINT_NAMES, ROBOT_MODELS, TRACKED_BODIES
from supermimic.robot_contract import (
    assert_contract_compatible, contract_mismatches, load_contract, make_mjlab_config,
)


class StandaloneContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = {name: load_contract(robot=name) for name in ROBOT_MODELS}
        cls.trained = json.loads((Path(__file__).parent / 'fixtures/trained_g1_contract.json').read_text())

    def test_default_physics_matches_the_frozen_trained_contract(self):
        self.assertEqual(DEFAULT_ROBOT, 'g1_29dof')
        current = load_contract()
        assert_contract_compatible(self.trained, current)
        self.assertEqual(current.xml_sha256, 'ac0a40caa37cf38af8dcee55e4bd2cb77fa19fef796d01c3a6765b4ed669d53f')
        self.assertEqual(contract_mismatches(self.trained, current), [])

    def test_installed_assets_resolve_inside_the_package(self):
        for name, contract in self.contracts.items():
            self.assertTrue(Path(contract.xml_path).is_relative_to(ASSET_ROOT))
            self.assertEqual(Path(contract.xml_path).stem, name)
            make_mjlab_config(contract, 1)

    def test_both_robots_have_sdk_joint_order_and_distinct_physics(self):
        models = []
        for name, contract in self.contracts.items():
            with self.subTest(robot=name):
                model = mujoco.MjModel.from_xml_path(contract.xml_path)
                models.append(model)
                self.assertEqual(contract.joint_names, tuple(G1_JOINT_NAMES))
                for joint in G1_JOINT_NAMES:
                    self.assertEqual(model.joint(joint).type[0], mujoco.mjtJoint.mjJNT_HINGE)
                for body in TRACKED_BODIES:
                    self.assertGreater(model.body(body).id, 0)
                kin = G1Kinematics('cpu', xml_path=contract.xml_path)
                self.assertEqual(len(kin.tracked_idx), 14)
        first, alternate = self.contracts.values()
        self.assertNotEqual(first.xml_sha256, alternate.xml_sha256)
        self.assertNotEqual(float(models[0].body_mass.sum()), float(models[1].body_mass.sum()))
        # Model choice changes the asset while keeping the baseline control law.
        for field in ('kp', 'kd', 'action_scale', 'effort', 'armature', 'physics_settings'):
            self.assertEqual(getattr(first, field), getattr(alternate, field))

    def test_trained_contract_is_portable_but_physics_changes_are_rejected(self):
        current = self.contracts[DEFAULT_ROBOT]
        relocated = replace(current, xml_path='/different/installation/g1_29dof.xml')
        assert_contract_compatible(self.trained, relocated)
        mutations = [
            replace(current, robot='g1_29dof_rev_1_0'),
            replace(current, xml_sha256='0' * 64),
            replace(current, control_dt=0.04),
            replace(current, kp=(current.kp[0] + 1.0, *current.kp[1:])),
            self.contracts['g1_29dof_rev_1_0'],
        ]
        for changed in mutations:
            with self.subTest(contract=changed.robot, mismatch=contract_mismatches(self.trained, changed)):
                with self.assertRaisesRegex(ValueError, 'contract differs'):
                    assert_contract_compatible(self.trained, changed)
        with self.assertRaises(ValueError):
            assert_contract_compatible(None, current)
        with self.assertRaises(ValueError):
            load_contract('unsupported_profile')
        with self.assertRaises(ValueError):
            load_contract(robot='not_a_supported_robot')

        with self.assertRaisesRegex(ValueError, 'unknown_metadata'):
            assert_contract_compatible({**self.trained, 'unknown_metadata': ''}, current)

    def test_contract_metadata_round_trips_without_custom_classes(self):
        for contract in self.contracts.values():
            record = contract.metadata()
            expected_hash = hashlib.sha256(Path(contract.xml_path).read_bytes()).hexdigest()
            self.assertEqual(record['xml_sha256'], expected_hash)
            assert_contract_compatible(json.loads(json.dumps(record)), contract)
            stream = io.BytesIO()
            torch.save(record, stream)
            stream.seek(0)
            self.assertEqual(torch.load(stream, weights_only=True), record)


if __name__ == '__main__':
    unittest.main()
