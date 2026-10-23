"""Ghost comparison preserves poses and adds no duplicate ground or physics."""
import importlib.util
from pathlib import Path

import mujoco
import numpy as np


spec = importlib.util.spec_from_file_location(
    'render_rollout', Path(__file__).resolve().parents[1] / 'tools/render_rollout.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_reference_visuals_preserve_world_pose_without_ground_or_physics():
    model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
      <geom type="plane" size="5 5 .1"/>
      <body pos="1 2 3"><freejoint/><geom type="box" size=".1 .2 .3"/></body>
    </worldbody></mujoco>''')
    state = mujoco.MjData(model)
    mujoco.mj_forward(model, state)
    original_qpos = state.qpos.copy()
    source, destination = mujoco.MjvScene(model, 10), mujoco.MjvScene(model, 10)
    mujoco.mjv_updateScene(model, state, mujoco.MjvOption(), None,
                          mujoco.MjvCamera(), mujoco.mjtCatBit.mjCAT_ALL, source)
    color = np.array([0, .8, 1, .35], dtype=np.float32)
    assert renderer.append_reference_geoms(destination, source, [1], color) == 1
    assert destination.ngeom == 1
    geom = destination.geoms[0]
    np.testing.assert_array_equal(geom.pos, [1, 2, 3])
    np.testing.assert_array_equal(geom.rgba, color)
    assert geom.objid == 1 and geom.matid == -1 and geom.transparent == 1
    np.testing.assert_array_equal(state.qpos, original_qpos)
    destination.ngeom = destination.maxgeom
    with np.testing.assert_raises_regex(ValueError, 'capacity'):
        renderer.append_reference_geoms(destination, source, [1], color)
