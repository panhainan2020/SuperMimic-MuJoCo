"""Small end-to-end validation, never a benchmark reproduction.

All logs/checkpoints stay in the experiment directory on the executing machine.
No artifacts, archives, replay, data or weights are downloaded or transferred.
For server runs, artifacts remain on server persistent storage; only text status
may be retrieved, and authorized shutdown never waits for a download.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np
from supermimic.runtime import artifact_dir, experiment_root, STORAGE_POLICY
from supermimic.robot import DEFAULT_ROBOT, ROBOT_MODELS
from supermimic.robot_contract import load_contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("mujoco", "mjlab"), default="mujoco")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--profile", choices=("upstream", "paper"), default="upstream")
    parser.add_argument("--robot", choices=ROBOT_MODELS, default=DEFAULT_ROBOT)
    parser.add_argument("--out", default=str(experiment_root() / "validation" / "smoke_native"))
    args = parser.parse_args()
    out = artifact_dir(args.out)
    if (out / "train" / "last.pt").exists():
        raise FileExistsError(f"Choose a fresh --out directory; checkpoint exists under {out}")
    motions = out / "synthetic_motions"
    motions.mkdir(exist_ok=True)
    contract = load_contract(args.profile, robot=args.robot)
    for name, frames in (("stand_long", 61), ("stand_short", 31)):
        raw = np.zeros((frames, 36))
        raw[:, :3] = contract.root_pos
        raw[:, 6] = 1.0
        raw[:, 7:] = contract.default_q
        np.savetxt(motions / f"{name}.csv", raw, delimiter=",")
    common = ["--backend", args.backend, "--device", args.device, "--profile", args.profile, "--robot", args.robot,
              "--motion_dir", str(motions), "--network_size", "tiny"]
    train = [sys.executable, "-m", "supermimic.train", *common, "--num_envs", "2",
             "--buffer_steps", "32", "--warmup_steps", "8", "--horizon", "4",
             "--hist", "2", "--goal_frames", "2", "--wm_window", "2", "--wm_batches", "1",
             "--wm_batch", "8", "--pi_batch", "8", "--wm_only_iters", "0",
             "--critic_epochs", "1", "--critic_minibatches", "1", "--log_every", "1",
             "--ckpt_every", "2", "--log_dir", str(out / "train")]
    commands = [
        ("train", train + ["--iterations", "3"]),
        ("resume", train + ["--iterations", "5", "--resume", str(out / "train" / "last.pt")]),
        ("evaluate", [sys.executable, "-m", "supermimic.evaluate", *common,
                      "--run_dir", str(out / "train"), "--ckpt", str(out / "train" / "last.pt")]),
    ]
    environment = dict(os.environ, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
    summary = {"purpose": "implementation smoke check only; synthetic motions and tiny networks",
               "storage_policy": STORAGE_POLICY, "backend": args.backend, "device": args.device,
               "profile": args.profile, "robot": args.robot, "checks": []}
    for name, command in commands:
        log_path = out / f"{name}.log"
        with log_path.open("w") as log:
            result = subprocess.run(command, cwd=REPO, env=environment, stdout=log, stderr=subprocess.STDOUT)
        summary["checks"].append({"name": name, "returncode": result.returncode, "command": command})
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'} ({log_path})", flush=True)
        if result.returncode:
            print(log_path.read_text()[-5000:], flush=True)
            raise SystemExit(result.returncode)
    print(f"Smoke validation complete: {out / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
