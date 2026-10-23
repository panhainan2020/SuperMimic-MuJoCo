"""Standalone robot/controller contracts for both packaged G1 variants.

The default upstream profile preserves the pinned third-party controller.
The optional paper profile is a historical ablation, not the reproduction baseline.
No external robot repository, configuration framework, data or weights are loaded.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .robot import DEFAULT_ROBOT, G1_JOINT_NAMES, _kd, _kp, default_joint_pos_list, motor_of, robot_xml_path

UPSTREAM_PHYSICS_SETTINGS = (
    ("upstream_commit", "a1508d42c9d1699a52e8233ab16d08c488441ab9"),
    ("isaaclab_commit", "46d6cc3d7b115906fad12efd372fbf69f4e3d3ed"),
    ("pd_actuator", "builtin_position"),
    ("integrator", "implicitfast"), ("cone", "pyramidal"),
    ("solver", "newton"), ("iterations", 100), ("ls_iterations", 50),
    ("tolerance", 1e-6), ("impratio", 1.0), ("ccd_iterations", 35),
    ("enable_multiccd", False), ("nconmax", 128), ("njmax", 500),
    ("self_collision", False), ("friction_com_sampling", "startup"),
    ("calibration_sampling", "reset"),
    # IsaacLab declares ls_parallel=False but removes it before constructing
    # Newton's solver. We explicitly choose that declared value in MJLab.
    ("ls_parallel", False), ("ls_parallel_source", "adapter: declared IsaacLab value, not forwarded to Newton"),
    ("ls_tolerance", 0.01), ("ls_tolerance_source", "adapter: MJLab 1.4 default, absent from pinned IsaacLab config"),
)


@dataclass(frozen=True)
class RobotContract:
    profile: str
    joint_names: tuple[str, ...]
    default_q: tuple[float, ...]
    kp: tuple[float, ...]
    kd: tuple[float, ...]
    effort: tuple[float, ...]
    velocity: tuple[float, ...]
    armature: tuple[float, ...]
    frictionloss: tuple[float, ...]
    action_scale: tuple[float, ...]
    xml_path: str
    xml_sha256: str
    sim_dt: float
    control_dt: float
    action_clip: float | None = None
    root_pos: tuple[float, ...] = (0.0, 0.0, 0.8)
    root_quat_wxyz: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0)
    physics_settings: tuple[tuple[str, str | int | float | bool], ...] = ()
    robot: str = DEFAULT_ROBOT

    @property
    def decimation(self) -> int:
        ratio = self.control_dt / self.sim_dt
        if abs(ratio - round(ratio)) > 1e-7:
            raise ValueError("control_dt must be an integer multiple of sim_dt")
        return round(ratio)

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


def load_contract(profile: str = "upstream", *, robot: str = DEFAULT_ROBOT,
                  xml_path: str | Path | None = None) -> RobotContract:
    """Load a local robot with the unchanged third-party PD controller.

    Asset selection is independent of control profile. Both G1 variants have the
    same SDK joint order, but different XML identities: their checkpoints are
    deliberately not interchangeable. An explicit XML override is checkpointed.
    """
    if profile not in {"paper", "upstream"}:
        raise ValueError(f"Unknown controller profile: {profile}; choose upstream or paper")
    xml = robot_xml_path(robot, xml_path)
    if not xml.is_file():
        raise FileNotFoundError(f"G1 MJCF missing at {xml}; reinstall package assets or set --xml_path")
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(xml))
    names = tuple(G1_JOINT_NAMES)
    hinges = tuple(model.joint(i).name for i in range(model.njnt)
                   if model.jnt_type[i] == mujoco.mjtJoint.mjJNT_HINGE)
    if set(hinges) != set(names) or len(hinges) != len(names) or model.njnt != len(names) + 1:
        raise ValueError("The robot must have exactly the 29 named G1 scalar hinge joints")
    if sum(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE) != 1:
        raise ValueError("The robot must have exactly one floating root")
    motors = [motor_of(name) for name in names]
    kp = tuple(_kp(motor[2]) for motor in motors)
    contract = RobotContract(
        profile=profile, robot=robot, joint_names=names, default_q=tuple(default_joint_pos_list()),
        kp=kp, kd=tuple(_kd(motor[2]) for motor in motors),
        effort=tuple(motor[0] for motor in motors), velocity=tuple(motor[1] for motor in motors),
        armature=tuple(motor[2] for motor in motors), frictionloss=(0.0,) * len(names),
        action_scale=tuple(0.25 * motor[0] / gain for motor, gain in zip(motors, kp)),
        xml_path=str(xml), xml_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
        # Evaluation/imagined actions stay unbounded in the pinned upstream code.
        sim_dt=0.005, control_dt=0.02, action_clip=None if profile == "upstream" else 20.0,
        root_pos=(0.0, 0.0, 0.76), root_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        physics_settings=UPSTREAM_PHYSICS_SETTINGS if profile == "upstream" else (),
    )
    contract.decimation
    return contract


def contract_mismatches(saved: Mapping[str, Any] | None, current: RobotContract) -> list[str]:
    """Compare physical identity across installations.

    Absolute XML locations are portable; XML contents, model name, gains, timing
    and solver settings are not. Checkpoints without an explicit robot selection
    use the default G1 model. Unknown or missing physical fields cause rejection.
    """
    if not isinstance(saved, Mapping):
        return ["missing contract"]
    expected, actual = dict(saved), current.metadata()
    expected.setdefault("robot", DEFAULT_ROBOT)
    expected.pop("xml_path", None)
    actual.pop("xml_path", None)
    # JSON canonicalization handles tuple/list differences in JSON round trips.
    return [key for key in sorted(expected.keys() | actual.keys())
            if key not in expected or key not in actual
            or json.dumps(expected[key], sort_keys=True) != json.dumps(actual[key], sort_keys=True)]


def assert_contract_compatible(saved: Mapping[str, Any] | None, current: RobotContract) -> None:
    mismatches = contract_mismatches(saved, current)
    if mismatches:
        raise ValueError("Checkpoint robot contract differs from the selected environment: "
                         + ", ".join(mismatches))


def make_mjlab_config(contract: RobotContract, num_envs: int, seed: int = 0):
    """Construct the independent MuJoCo/MJLab scene; the caller owns task logic."""
    from .paper_scene import make_independent_scene_config

    return make_independent_scene_config(contract, num_envs)
