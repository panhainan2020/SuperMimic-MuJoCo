"""Independent MJLab scenes for upstream and paper G1 controller profiles.

Sources: the paper's 200 Hz physics / 50 Hz control clock; BeyondMimic's open
G1 low-PD controller; MIT supermimic_vibed commit
a1508d42c9d1699a52e8233ab16d08c488441ab9 for implicitfast, pyramidal contacts,
nconmax=128 and njmax=500. The upstream profile disables physical self-collisions
as its source robot.py requests. The optional paper profile preserves the chosen
robot asset's collisions. The upstream README pins IsaacLab commit
46d6cc3d7b115906fad12efd372fbf69f4e3d3ed; its public MJWarpSolverCfg declares
Newton/100 iterations/50 line searches/tolerance 1e-6/impratio 1/CCD 35/no
multiccd. These are configured explicitly from the checkpointed contract.
ls_parallel and ls_tolerance remain separately labelled adapter choices.
No proprietary demo assets or configuration are used.

Packaged robot MJCF/meshes are used; no external task, action manager or
speed-dependent DC motor envelope enters this scene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import mujoco
from mjlab.actuator import BuiltinPositionActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.scene import SceneCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.terrains import TerrainEntityCfg

if TYPE_CHECKING:
    from .robot_contract import RobotContract


@dataclass(frozen=True)
class IndependentSceneConfig:
    scene: SceneCfg
    sim: SimulationCfg
    decimation: int


def make_independent_scene_config(contract: RobotContract, num_envs: int) -> IndependentSceneConfig:
    if contract.profile not in {"paper", "upstream"}:
        raise ValueError("The independent low-PD scene requires profile=upstream or paper")
    if num_envs < 1:
        raise ValueError("num_envs must be positive")
    settings = dict(contract.physics_settings)
    if len(settings) != len(contract.physics_settings):
        raise ValueError("Duplicate physics-setting keys")
    if contract.profile == "upstream":
        if settings.get("pd_actuator") != "builtin_position":
            raise ValueError("The upstream scene requires the checkpointed builtin position PD contract")
        if settings.get("friction_com_sampling") != "startup" or settings.get("calibration_sampling") != "reset":
            raise ValueError("The upstream scene requires startup friction/COM and reset calibration")
        mujoco_cfg = MujocoCfg(
            timestep=contract.sim_dt, integrator=settings["integrator"], cone=settings["cone"],
            solver=settings["solver"], iterations=settings["iterations"], ls_iterations=settings["ls_iterations"],
            tolerance=settings["tolerance"], impratio=settings["impratio"], ccd_iterations=settings["ccd_iterations"],
            ls_tolerance=settings["ls_tolerance"],
            # MuJoCo 3.8 enables multi-CCD by default; disable it explicitly.
            disableflags=() if settings["enable_multiccd"] else ("multiccd",),
        )
        simulation = SimulationCfg(nconmax=settings["nconmax"], njmax=settings["njmax"],
                                   ls_parallel=settings["ls_parallel"], mujoco=mujoco_cfg)
    else:
        # Preserve the previous optional paper experiment's settings.
        simulation = SimulationCfg(nconmax=128, njmax=500,
                                   mujoco=MujocoCfg(timestep=contract.sim_dt, integrator="implicitfast", cone="pyramidal"))

    def robot_spec():
        spec = mujoco.MjSpec.from_file(contract.xml_path)
        # The asset's original torque motors are replaced by MuJoCo-native PD.
        for actuator in list(spec.actuators):
            spec.delete(actuator)
        if not settings.get("self_collision", True):
            # Match enabled_self_collisions=False in the MIT reproduction.
            # Robot collision geoms emit bit 1 but accept no robot bits. The
            # ground's default affinity includes bit 1, so ground contact stays
            # enabled. Keep visual-only geoms non-colliding.
            for geom in spec.geoms:
                if geom.contype or geom.conaffinity:
                    geom.contype, geom.conaffinity = 1, 0
            # Explicit pairs bypass bitmasks; a robot-only asset has no ground
            # pairs, so remove its internal pairs as part of disabling self-contact.
            for pair in list(spec.pairs):
                spec.delete(pair)
        return spec

    actuators = tuple(
        BuiltinPositionActuatorCfg(
            target_names_expr=(name,), stiffness=contract.kp[index], damping=contract.kd[index],
            effort_limit=contract.effort[index], armature=contract.armature[index],
            frictionloss=contract.frictionloss[index],
        )
        for index, name in enumerate(contract.joint_names)
    )
    robot = EntityCfg(
        spec_fn=robot_spec,
        init_state=EntityCfg.InitialStateCfg(
            pos=contract.root_pos, rot=contract.root_quat_wxyz,
            joint_pos=dict(zip(contract.joint_names, contract.default_q)), joint_vel={".*": 0.0},
        ),
        articulation=EntityArticulationInfoCfg(actuators=actuators, soft_joint_pos_limit_factor=0.9),
        sort_actuators=True,
    )
    return IndependentSceneConfig(
        scene=SceneCfg(num_envs=num_envs, env_spacing=0.0,
                       terrain=TerrainEntityCfg(terrain_type="plane", env_spacing=0.0),
                       entities={"robot": robot}),
        sim=simulation,
        decimation=contract.decimation,
    )
