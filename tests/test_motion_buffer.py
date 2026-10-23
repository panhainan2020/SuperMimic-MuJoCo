"""Regression checks for motion boundaries, serialized motion data and replay histories."""
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import torch

from supermimic.buffer import FIELDS, ReplayBuffer
from supermimic.motion import MotionLib
from supermimic.rotations import so3_exp


class RootOnlyKinematics:
    """A tiny FK fixture keeps data-format tests independent of robot asset files."""

    def forward(self, p, R, v, w, q, qd):
        return p[:, None], R[:, None], v[:, None], w[:, None]


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.kin = RootOnlyKinematics()

    def tearDown(self):
        self.tmp.cleanup()

    def csv(self, name, frames, **kwargs):
        raw = np.zeros((frames, 36), dtype=np.float32)
        raw[:, 2] = 0.8
        raw[:, 6] = 1
        for k, v in kwargs.items():
            raw[:, int(k)] = v
        path = self.root / (name + ".csv")
        np.savetxt(path, raw, delimiter=",")
        return path

    def test_terminal_frame_is_never_a_bin_start(self):
        # 31 frames at 30 Hz -> 51 at 50 Hz: previously created a last-frame-only bin.
        self.csv("a", 31)
        self.csv("b", 32)
        m = MotionLib.from_dir(str(self.root), self.kin, "cpu")
        self.assertEqual(m.clip_len.tolist(), [51, 52])
        self.assertEqual(m.bin_start.tolist(), [0, 51, 101])
        self.assertTrue(bool((m.bin_start < m.bin_end).all()))
        for b, c in enumerate(m.bin_clip.tolist()):
            for f in range(int(m.bin_start[b]), int(m.bin_end[b])):
                self.assertLess(f, int(m.clip_end[c]))
                self.assertEqual(int(m.frame_bin[f]), b)
        future = m.future_frames(torch.tensor([49, 101]), 10)
        self.assertEqual(future[0].tolist(), [50] * 10)
        self.assertEqual(future[1].tolist(), [102] * 10)

    def test_joblib_matches_csv_coordinates_and_order(self):
        # A root yaw and distinct joint values expose xyzw and joint-order mistakes.
        n = 3
        yaw = np.pi / 2
        q_xyzw = np.tile([0, 0, np.sin(yaw / 2), np.cos(yaw / 2)], (n, 1))
        p = np.array([[1, 2, 0.8], [1.1, 2.2, 0.8], [1.2, 2.4, 0.8]])
        joints = np.tile(np.arange(29) / 100, (n, 1))
        raw = np.concatenate([p, q_xyzw, joints], -1)
        csv = self.root / "reference.csv"
        np.savetxt(csv, raw, delimiter=",")
        entry = {"root_trans_offset": p, "root_rot": q_xyzw, "dof": joints, "fps": 50}
        source = self.root / "motions.pkl"
        joblib.dump({"walk": entry}, source)
        before = source.read_bytes()
        a = MotionLib.from_path(source, self.kin, "cpu")
        b = MotionLib([str(csv)], self.kin, "cpu", src_fps=50)
        self.assertEqual(a.names, ["walk"])
        for x, y in zip(a.ref_state(torch.arange(n)), b.ref_state(torch.arange(n))):
            torch.testing.assert_close(x, y)
        torch.testing.assert_close(a.root_p, torch.tensor(p, dtype=torch.float32))
        torch.testing.assert_close(a.q, torch.tensor(joints, dtype=torch.float32))
        self.assertEqual(before, source.read_bytes())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["motions.pkl", "reference.csv"])

    def test_pose_aa_fallback_and_source_fps(self):
        aa = np.zeros((3, 30, 3), dtype=np.float32)
        aa[:, 0, 2] = 0.4
        source = self.root / "rotations.pkl"
        joblib.dump({"one": {"root_trans_offset": np.zeros((3, 3)), "pose_aa": aa,
                             "dof_pos": np.zeros((3, 29)), "fps": 25}}, source)
        m = MotionLib.from_path(source, self.kin, "cpu")
        self.assertEqual(m.clip_len.tolist(), [5])
        expected = so3_exp(torch.tensor([0.0, 0.0, 0.4])).expand(5, 3, 3)
        torch.testing.assert_close(m.root_R, expected)

    def test_invalid_motion_inputs_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "No motion clips"):
            MotionLib.from_path(self.root, self.kin, "cpu")
        one = self.csv("short", 1)
        with self.assertRaisesRegex(ValueError, "T >= 2"):
            MotionLib([str(one)], self.kin, "cpu")
        zero = self.csv("zero", 3, **{"6": 0})
        with self.assertRaisesRegex(ValueError, "zero-norm"):
            MotionLib([str(zero)], self.kin, "cpu")
        bad = self.csv("nan", 3, **{"7": np.nan})
        with self.assertRaisesRegex(ValueError, "NaN"):
            MotionLib([str(bad)], self.kin, "cpu")
        good = self.csv("good", 3)
        with self.assertRaisesRegex(ValueError, "fps"):
            MotionLib([str(good)], self.kin, "cpu", src_fps=0)
        with self.assertRaisesRegex(FileNotFoundError, "does not exist"):
            MotionLib.from_path(self.root / "missing.pkl", self.kin, "cpu")


class ReplayTests(unittest.TestCase):
    def transition(self, n, frame, ep_step=0, done=False):
        out = {}
        for key, (shape, dtype) in FIELDS.items():
            shape = (shape,) if isinstance(shape, int) else shape
            out[key] = torch.zeros((n,) + shape, dtype=dtype)
        out["f"].fill_(frame)
        out["ep_step"].fill_(ep_step)
        out["done"].fill_(done)
        out["s"].fill_(frame)
        return out

    def test_constructor_empty_and_window_guards(self):
        with self.assertRaises(ValueError):
            ReplayBuffer(0, 1, "cpu")
        b = ReplayBuffer(8, 1, "cpu")
        with self.assertRaisesRegex(ValueError, "empty"):
            b.sample_starts(1, 2)
        b.add(self.transition(1, 0))
        with self.assertRaisesRegex(ValueError, "warmup"):
            b.sample_windows(1, 8)
        with self.assertRaises(ValueError):
            b.sample_windows(0, 1)

    def test_add_validates_all_fields_before_mutation(self):
        b = ReplayBuffer(4, 1, "cpu")
        bad = self.transition(1, 3)
        bad["done"] = torch.zeros(2, dtype=torch.bool)
        with self.assertRaises(ValueError):
            b.add(bad)
        self.assertEqual(b.size, 0)
        self.assertEqual(float(b.data["s"].sum()), 0)
        bad = self.transition(1, 0)
        bad["f"] = torch.zeros(1)
        with self.assertRaisesRegex(ValueError, "dtype"):
            b.add(bad)

    def test_terminal_mask_and_ring_chronology(self):
        b = ReplayBuffer(4, 1, "cpu")
        for i in range(6):
            b.add(self.transition(1, i, ep_step=i if i <= 3 else i - 4, done=i == 3))
        w = b.sample_windows(3, 4)
        self.assertEqual(w["s"][0, :, 0].tolist(), [2, 3, 4, 5])
        self.assertEqual(w["mask"][0].tolist(), [1, 1, 0, 0])

    def test_valid_starts_do_not_cross_clip_and_history_boundaries(self):
        b = ReplayBuffer(4, 1, "cpu")
        # Clips span [0, 2], [3, 8]. Only frame 5 has three transitions remaining.
        for f, ep in [(1, 1), (2, 2), (5, 0), (6, 1)]:
            b.add(self.transition(1, f, ep))
        ends = torch.tensor([2, 8])
        ids = torch.tensor([0, 0, 0, 1, 1, 1, 1, 1, 1])
        s, h = b.sample_valid_starts(20, 4, 3, ends, ids)
        self.assertEqual(s["f"].tolist(), [5] * 20)
        self.assertEqual(h["f"][0].tolist(), [5] * 4)
        with self.assertRaisesRegex(ValueError, "no start"):
            b.sample_valid_starts(1, 2, 4, ends, ids)

    def test_history_does_not_wrap_into_newer_data(self):
        b = ReplayBuffer(3, 1, "cpu")
        for f in range(5):
            b.add(self.transition(1, f, ep_step=f))
        ends, ids = torch.tensor([4]), torch.zeros(5, dtype=torch.long)
        s, h = b.sample_valid_starts(1, 5, 2, ends, ids)
        self.assertEqual(s["f"].tolist(), [2])
        self.assertEqual(h["f"][0].tolist(), [2] * 5)


if __name__ == "__main__":
    unittest.main()
