"""Protect whole-record temporal support, weighting, and the MAE/L2 distinction."""
import numpy as np
import unittest

from tools.trajectory_mae import aggregate, analyze_record


def fixture():
    record = {
        "names": np.array(["complete", "failed"]),
        "alive": np.array([[True, True], [True, False]]),
        "f": np.array([[0, 3], [1, 4]]), "clip_start": np.array([0, 3]),
        "clip_len": np.array([3, 3]), "q": np.zeros((2, 2, 29)),
        "root_p": np.zeros((2, 2, 3)), "ref_q": np.zeros((6, 29)),
        "ref_root_p": np.zeros((6, 3)),
    }
    record["q"][:, 0] = [[1.] * 29, [-3.] * 29]
    record["q"][:, 1] = [[6.] * 29, [1000.] * 29]
    record["root_p"][:, 0] = [[3., 4., 0.], [-3., -4., 0.]]
    record["root_p"][:, 1] = [[0., 0., 9.], [1000., 1000., 1000.]]
    labels = {"failed": ["failed"], "n_failed": 1, "per_clip": {"complete": .9, "failed": .1}}
    return record, labels


class TrajectoryMaeTest(unittest.TestCase):
    def test_absolute_coordinate_mae_is_not_l2_or_signed_mean(self):
        record, labels = fixture()
        first, _ = analyze_record(record, labels, "test")
        self.assertEqual(first["jointMaeRad"], 2)
        self.assertAlmostEqual(first["rootXyzMaeM"], 7 / 3)
        self.assertEqual(first["rootL2MeanM"], 5)
        self.assertEqual(first["rootXMaeM"], 3)
        self.assertEqual(first["lastRecordedTimeSeconds"], .02)

    def test_failed_prefix_excludes_padding_without_imputing_missing_frames(self):
        record, labels = fixture()
        _, failed = analyze_record(record, labels, "test")
        self.assertEqual(failed["jointMaeRad"], 6)
        self.assertEqual(failed["rootXyzMaeM"], 3)
        self.assertEqual(failed["coverageFraction"], .5)
        self.assertTrue(failed["failed"] and not failed["completed"])
        self.assertEqual(failed["executedDurationSeconds"], .02)
        self.assertEqual(failed["referenceDurationSeconds"], .04)

    def test_frame_pooling_differs_from_equal_clip_and_completed_subset(self):
        record, labels = fixture()
        rows = analyze_record(record, labels, "test")
        total = aggregate(rows)
        self.assertEqual(total["clipEqual"]["jointMaeRad"], 4)
        self.assertAlmostEqual(total["frameWeighted"]["jointMaeRad"], 10 / 3)
        self.assertEqual(total["coverageFraction"], .75)
        complete = aggregate([row for row in rows if row["completed"]])
        self.assertTrue(complete["nClips"] == 1 and complete["nFailed"] == 0)
        self.assertEqual(complete["frameWeighted"]["jointMaeRad"], 2)
        self.assertIsNone(aggregate([])["frameWeighted"])

    def test_reject_shifted_reference_or_discontinuous_survival(self):
        record, labels = fixture()
        record["f"][0, 0] = 1
        with self.assertRaisesRegex(ValueError, "reference frame mismatch"):
            analyze_record(record, labels, "test")
        record, labels = fixture()
        record["alive"][:, 1] = [False, True]
        with self.assertRaisesRegex(ValueError, "contiguous prefix"):
            analyze_record(record, labels, "test")
