"""Shared CLI and artifact placement; never transfers training outputs."""
from pathlib import Path
import os
from .robot import DEFAULT_ROBOT, ROBOT_MODELS

STORAGE_POLICY = (
    "Artifacts stay on the training server's persistent disk. No automatic download, "
    "prefetch, archive/replay/weight transfer, mirroring or resume-transfer. "
    "Integrity/recovery checks run on the server; retrieve only small text metrics and metadata. "
    "Previously authorized shutdown follows training/storage/test completion without waiting for downloads."
)


def experiment_root():
    return Path(os.environ.get(
        "SUPERMIMIC_EXPERIMENT_ROOT", str(Path.cwd() / "outputs"))).expanduser().resolve()


def artifact_dir(path):
    root = experiment_root()
    path = Path(path).expanduser().resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Artifacts must be under {root}; got {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def add_runtime_args(parser):
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--backend", choices=("mujoco", "mjlab"), default="mujoco")
    parser.add_argument("--robot", choices=ROBOT_MODELS, default=DEFAULT_ROBOT,
                        help="packaged robot; g1_29dof matches existing trained checkpoints")
    parser.add_argument("--profile", choices=("upstream", "paper"), default="upstream",
                        help="upstream preserves the third-party baseline; paper is a historical ablation")
    parser.add_argument("--xml_path", default=None)
    parser.add_argument("--observation_mode", choices=("paper93", "legacy99"), default="legacy99",
                        help="legacy99 is the third-party 99D observation; paper93 is an incomplete experimental ablation")
    parser.add_argument("--network_size", choices=("paper", "tiny"), default="paper",
                        help="tiny is for implementation smoke checks only")


def network_shapes(size):
    return ((64, 64), (64, 32), (32, 16)) if size == "tiny" else (
        (2048, 2048, 2048), (2048, 1024, 512, 256), (256, 128))
