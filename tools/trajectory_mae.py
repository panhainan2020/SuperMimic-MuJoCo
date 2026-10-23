#!/usr/bin/env python3
"""CPU-only whole-record MAE from existing local evaluation NPZ files.

No inference, network access or artifact transfer is performed. Raw output must
stay under SUPERMIMIC_EXPERIMENT_ROOT. Server weights, replay, trajectories and
videos remain on persistent storage; this command never downloads them.

The historical pre-step convention includes reset and excludes the terminal
executed state. Failed clips contribute only their observed prefix, never zeros
for unexecuted frames. Root XYZ coordinate MAE and mean Euclidean error are
different quantities and are reported separately.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from supermimic.runtime import STORAGE_POLICY, artifact_dir

DT = 0.02
METRICS = ("jointMaeRad", "jointMaeDeg", "rootXyzMaeM", "rootXMaeM",
           "rootYMaeM", "rootZMaeM", "rootL2MeanM")
CONVENTIONS = {
    "phase": "pre_step_alive",
    "sampling": "All recorded alive=True samples at 50 Hz; reset included; terminal executed state excluded. No video subsampling.",
    "referenceIndex": "Recorded state at t is compared with the reference at recorded global f[t], without a frame shift.",
    "jointMae": "mean over observed time and 29 bounded SDK-order joints of abs(q - reference_q), without angle wrapping",
    "rootXyzMae": "mean over observed time and world X/Y/Z coordinates of abs(root_position - reference_root_position), in metres",
    "rootL2Mean": "mean over observed time of the Euclidean world root position error, in metres; this is not coordinate MAE",
    "alignment": "No XY, yaw or other alignment is applied to the root-position errors.",
    "clipEqual": "Compute each clip's mean over its observed samples, then weight clips equally.",
    "frameWeighted": "Pool all observed samples; longer observed trajectories receive proportionally more weight.",
    "failedClips": "Only the observed prefix is measurable; never pad unexecuted states or invent full-reference-trajectory MAE. Report failure and duration coverage separately.",
    "completedOnly": "Includes only clips with no authoritative failure and all expected transitions executed.",
    "coverage": "Executed transitions / (reference frames - 1); 100% transition coverage does not mean the terminal state was recorded.",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def analyze_record(record, evaluation: dict, dataset_id: str) -> list[dict]:
    """Validate the saved sampling contract, then compute one row per clip."""
    keys = ("names", "alive", "f", "clip_start", "clip_len", "q", "root_p", "ref_q", "ref_root_p")
    a = {key: record[key] for key in keys}
    names, alive = a["names"], a["alive"]
    if names.ndim != 1 or names.dtype.kind not in "US" or not len(names):
        raise ValueError("names must be a nonempty string vector")
    if len(set(map(str, names))) != len(names):
        raise ValueError("Duplicate clip names")
    if alive.dtype != np.bool_ or alive.ndim != 2 or alive.shape[1] != len(names) or not alive.shape[0]:
        raise ValueError("alive must have nonempty Boolean shape (T, C)")
    t, c = alive.shape
    for key in ("f", "clip_start", "clip_len"):
        if not np.issubdtype(a[key].dtype, np.integer):
            raise ValueError(f"{key} must be integer")
    if a["clip_len"].shape != (c,) or a["clip_start"].shape != (c,) or np.any(a["clip_len"] < 2):
        raise ValueError("Invalid clip lengths/starts")
    if not np.array_equal(a["clip_start"], np.cumsum(a["clip_len"]) - a["clip_len"]):
        raise ValueError("Reference clips must be contiguous and begin at zero")
    f = int(a["clip_len"].sum())
    for key, shape in {"q": (t, c, 29), "root_p": (t, c, 3), "f": (t, c),
                       "ref_q": (f, 29), "ref_root_p": (f, 3)}.items():
        if a[key].shape != shape or not np.isfinite(a[key]).all():
            raise ValueError(f"Invalid shape or nonfinite values: {key}")
    failed = evaluation["failed"]
    if (set(evaluation["per_clip"]) != set(map(str, names))
            or len(failed) != len(set(failed)) or len(failed) != evaluation["n_failed"]
            or not set(failed).issubset(evaluation["per_clip"])):
        raise ValueError("Authoritative evaluation labels do not match the record")
    rows = []
    for i, name in enumerate(names):
        active = np.flatnonzero(alive[:, i])
        n, expected = len(active), int(a["clip_len"][i]) - 1
        if n < 1 or n > expected or not np.array_equal(active, np.arange(n)):
            raise ValueError(f"{name}: alive must be a nonempty contiguous prefix")
        frames = a["f"][active, i]
        if not np.array_equal(frames, int(a["clip_start"][i]) + active):
            raise ValueError(f"{name}: pre-step reference frame mismatch")
        dq = a["q"][active, i].astype(np.float64) - a["ref_q"][frames].astype(np.float64)
        dp = a["root_p"][active, i].astype(np.float64) - a["ref_root_p"][frames].astype(np.float64)
        joint_mae = float(np.abs(dq).mean())
        axes = np.abs(dp).mean(axis=0)
        row = {
            "key": f"{dataset_id}:{name}", "datasetId": dataset_id, "name": str(name),
            "failed": str(name) in failed, "completed": str(name) not in failed and n == expected,
            "observedSamples": n, "expectedTransitions": expected, "coverageFraction": n / expected,
            "executedDurationSeconds": n * DT, "referenceDurationSeconds": expected * DT,
            "lastRecordedTimeSeconds": (n - 1) * DT,
            "jointMaeRad": joint_mae, "jointMaeDeg": float(np.degrees(joint_mae)),
            "rootXyzMaeM": float(axes.mean()), "rootXMaeM": float(axes[0]),
            "rootYMaeM": float(axes[1]), "rootZMaeM": float(axes[2]),
            "rootL2MeanM": float(np.linalg.norm(dp, axis=-1).mean()),
        }
        rows.append(row)
    return rows


def aggregate(rows: list[dict]) -> dict:
    observed = sum(row["observedSamples"] for row in rows)
    expected = sum(row["expectedTransitions"] for row in rows)
    result = {
        "nClips": len(rows), "nFailed": sum(row["failed"] for row in rows),
        "nCompleted": sum(row["completed"] for row in rows),
        "observedSamples": observed, "expectedTransitions": expected,
        "coverageFraction": observed / expected if expected else None,
        "executedDurationSeconds": observed * DT, "referenceDurationSeconds": expected * DT,
        "clipEqual": None, "frameWeighted": None,
    }
    if rows:
        result["clipEqual"] = {key: float(np.mean([row[key] for row in rows])) for key in METRICS}
        result["frameWeighted"] = {
            key: float(sum(row[key] * row["observedSamples"] for row in rows) / observed)
            for key in METRICS
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", required=True, metavar="ID=PATH",
                        help="Existing rollout.npz or directory recursively containing rollout.npz; repeat for datasets")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = artifact_dir(args.output_dir)
    filenames = ("trajectory_mae.json", "trajectory_mae.public.json", "trajectory_mae.per_clip.json", "trajectory_mae.per_clip.csv")
    if any((output / name).exists() for name in filenames):
        raise FileExistsError("Refusing to overwrite an existing MAE report")
    all_rows, sources, datasets = [], [], set()
    max_difference = 0.0
    compared_clips = 0
    for dataset in args.dataset:
        dataset_id, separator, location = dataset.partition("=")
        if not separator or not dataset_id or dataset_id in datasets:
            parser.error("Each --dataset requires a unique ID=PATH")
        datasets.add(dataset_id)
        path = Path(location).expanduser().resolve()
        paths = sorted(path.rglob("rollout.npz")) if path.is_dir() else [path]
        if not paths:
            raise ValueError(f"No local records for {dataset_id}")
        for index, path in enumerate(paths):
            evaluation_path = path.with_name("evaluation.json")
            evaluation = json.loads(evaluation_path.read_text())
            with np.load(path, allow_pickle=False) as record:
                rows = analyze_record(record, evaluation, dataset_id)
            tracking_path = path.with_name("tracking_metrics.json")
            source = {"datasetId": dataset_id, "recordId": f"{dataset_id}/{index:03d}",
                      "recordSha256": sha256(path), "evaluationSha256": sha256(evaluation_path),
                      "sourcePaths": {"record": str(path), "evaluation": str(evaluation_path)}}
            if tracking_path.exists():
                historical = {row["name"]: row for row in json.loads(tracking_path.read_text())["per_clip"]}
                for row in rows:
                    old = historical[row["name"]]
                    if old["valid_pre_step_samples"] != row["observedSamples"]:
                        raise ValueError("Historical tracking sample count mismatch")
                    difference = abs(old["joint_mae_rad"] - row["jointMaeRad"])
                    if difference > 1e-10:
                        raise ValueError(f"Historical joint MAE mismatch: {row['key']}")
                    max_difference = max(max_difference, difference)
                    compared_clips += 1
                source["historicalTrackingSha256"] = sha256(tracking_path)
                source["sourcePaths"]["historicalTracking"] = str(tracking_path)
            sources.append(source)
            all_rows.extend(rows)
    all_rows.sort(key=lambda row: row["key"])
    if len({row["key"] for row in all_rows}) != len(all_rows):
        raise ValueError("Duplicate dataset/name key across records")
    summary = {}
    for dataset_id in sorted(datasets):
        rows = [row for row in all_rows if row["datasetId"] == dataset_id]
        summary[dataset_id] = {
            "allObserved": aggregate(rows),
            "completedOnly": aggregate([row for row in rows if row["completed"]]),
            "failedOnly": aggregate([row for row in rows if row["failed"]]),
            "failedClips": [row for row in rows if row["failed"]],
        }
    public = {
        "schemaVersion": 1, "controlDtSeconds": DT, "conventions": CONVENTIONS,
        "summary": summary,
        "historicalJointMaeCheck": {"comparedClips": compared_clips, "maxAbsoluteDifferenceRad": max_difference,
                                    "note": "Same samples and formula; differences are float64 reduction rounding only."},
        "sources": [{key: value for key, value in source.items() if key != "sourcePaths"} for source in sources],
        "implementationSha256": sha256(Path(__file__)),
        "storagePolicy": STORAGE_POLICY,
    }
    raw = {**public, "sources": sources, "perClip": all_rows}
    # Per-clip public JSON omits values directly derivable from sample counts.
    compact_rows = [{key: value for key, value in row.items() if key not in (
        "coverageFraction", "executedDurationSeconds", "referenceDurationSeconds", "lastRecordedTimeSeconds")}
        for row in all_rows]
    payloads = {"trajectory_mae.json": json.dumps(raw, indent=2, ensure_ascii=False, allow_nan=False),
                "trajectory_mae.public.json": json.dumps(public, indent=2, ensure_ascii=False, allow_nan=False),
                "trajectory_mae.per_clip.json": json.dumps(compact_rows, ensure_ascii=False, separators=(",", ":"), allow_nan=False)}
    for name, content in payloads.items():
        if name != "trajectory_mae.json" and len(content.encode("utf-8")) >= 2 * 1024 * 1024:
            raise ValueError(f"Public metadata exceeds 2 MiB: {name}")
    for name, content in payloads.items():
        (output / name).write_text(content + "\n")
    with (output / "trajectory_mae.per_clip.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    print(json.dumps({"output": str(output), "summary": summary,
                      "historicalJointMaeCheck": public["historicalJointMaeCheck"]}, indent=2))


if __name__ == "__main__":
    main()
