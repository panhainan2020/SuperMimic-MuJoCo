#!/usr/bin/env python3
"""Render one LOCAL SuperMimic --record NPZ clip to an offscreen MP4.

No network/transfer functionality. Server artifacts remain on persistent storage
unless the user separately authorizes transfer. Input must already exist locally;
outputs remain under the experiment root. A video is not a performance metric.
Uses 50 Hz states, wxyz root quaternion, and named SDK-order joints. By default,
the reference is a translucent cyan ghost over the solid policy robot in the
same world frame. Single-policy and legacy side-by-side modes remain available. Set
SUPERMIMIC_EXPERIMENT_ROOT to your local/server persistent output directory.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from supermimic.robot import DEFAULT_ROBOT, ROBOT_MODELS
from supermimic.runtime import artifact_dir, STORAGE_POLICY


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def append_reference_geoms(destination, reference_scene, robot_geoms, rgba):
    """Add only robot visuals, preserving world poses; never modify physics.

    Both scenes must use the same compiled model, so mesh data IDs remain valid.
    A new untextured material makes the reference visibly distinct. Ground and
    other scene geometry are excluded, and no trajectory alignment is applied.
    """
    import mujoco
    robot_geoms = set(robot_geoms)
    sources = [reference_scene.geoms[i] for i in range(reference_scene.ngeom)
               if reference_scene.geoms[i].objtype == mujoco.mjtObj.mjOBJ_GEOM
               and reference_scene.geoms[i].objid in robot_geoms]
    if destination.ngeom + len(sources) > destination.maxgeom:
        raise ValueError('Render scene has insufficient capacity for reference visuals')
    for src in sources:
        dst = destination.geoms[destination.ngeom]
        mujoco.mjv_initGeom(dst, src.type, src.size, src.pos, src.mat.reshape(9), rgba)
        dst.dataid = src.dataid
        dst.modelrbound = src.modelrbound
        dst.objtype, dst.objid = src.objtype, src.objid
        dst.category = mujoco.mjtCatBit.mjCAT_DYNAMIC
        dst.matid, dst.texcoord, dst.segid = -1, 0, -1
        dst.specular, dst.shininess, dst.reflectance = 0.1, 0.1, 0.0
        dst.emission, dst.transparent = 0.2, 1
        destination.ngeom += 1
    return len(sources)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--clip', required=True, help='Exact clip name, not numeric index')
    p.add_argument('--output', type=Path, required=True, help='MP4 under SUPERMIMIC_EXPERIMENT_ROOT')
    p.add_argument('--robot', choices=ROBOT_MODELS, default=DEFAULT_ROBOT)
    p.add_argument('--xml-path', type=Path, help='Optional local MJCF override matching the recording')
    p.add_argument('--profile', choices=('upstream', 'paper'), default='upstream')
    p.add_argument('--comparison', choices=('ghost', 'policy', 'side-by-side'), default='ghost',
                   help='Default: solid policy with translucent reference in shared world coordinates')
    p.add_argument('--side-by-side', action='store_true', help='Compatibility alias for --comparison side-by-side')
    p.add_argument('--reference-alpha', type=float, default=0.35, help='Reference opacity in ghost mode, between 0 and 1')
    p.add_argument('--width', type=int, default=640, help='Width of each panel, divisible by 16')
    p.add_argument('--height', type=int, default=480, help='Height, divisible by 16')
    p.add_argument('--max-seconds', type=float, default=None, help='Optional explicitly reported preview limit')
    p.add_argument('--gl', choices=('egl', 'osmesa', 'glfw'), default='egl')
    a = p.parse_args()
    if a.side_by_side:
        a.comparison = 'side-by-side'
    out, record = a.output.expanduser().resolve(), a.record.expanduser().resolve()
    metadata_path = out.with_suffix('.video.json')
    if out.suffix.lower() != '.mp4':
        raise ValueError('Output must have an .mp4 extension')
    artifact_dir(out.parent)
    if out.exists() or metadata_path.exists():
        raise FileExistsError('Choose fresh output paths')
    if min(a.width, a.height) < 64 or a.width % 16 or a.height % 16:
        raise ValueError('Width/height must be at least 64 and divisible by 16')
    if a.max_seconds is not None and a.max_seconds <= 0:
        raise ValueError('max-seconds must be positive')
    if not 0 < a.reference_alpha < 1:
        raise ValueError('reference-alpha must be strictly between 0 and 1')
    if not record.is_file():
        raise FileNotFoundError('Recording must already exist locally; no transfer attempted')
    os.environ['MUJOCO_GL'] = a.gl
    import imageio.v2 as imageio
    import mujoco
    import numpy as np
    from mjlab.scene import Scene
    from supermimic.env import _model_indices
    from supermimic.robot_contract import load_contract, make_mjlab_config
    with np.load(record, allow_pickle=False) as archive:
        required = ('names', 'root_p', 'root_quat', 'q', 'f', 'alive',
                    'ref_root_p', 'ref_root_R', 'ref_q', 'clip_start', 'clip_len')
        if any(k not in archive for k in required):
            raise ValueError('Not a complete SuperMimic --record NPZ')
        names = [str(x) for x in archive['names'].tolist()]
        if names.count(a.clip) != 1:
            raise ValueError('Requested clip must occur exactly once in names')
        c = names.index(a.clip)
        positions = archive['root_p'][:, c].copy()
        quats = archive['root_quat'][:, c].copy()
        joints = archive['q'][:, c].copy()
        frames = archive['f'][:, c].astype(np.int64)
        alive = archive['alive'][:, c].astype(bool)
        ref_positions = archive['ref_root_p'].copy()
        ref_rotations = archive['ref_root_R'].copy()
        ref_joints = archive['ref_q'].copy()
        start, clip_len = int(archive['clip_start'][c]), int(archive['clip_len'][c])
    if not (positions.shape == (len(alive), 3) and quats.shape == (len(alive), 4)
            and joints.shape == (len(alive), 29) and frames.shape == alive.shape):
        raise ValueError('Invalid recording state shapes')
    if any(not np.isfinite(x).all() for x in (positions, quats, joints, ref_positions, ref_rotations, ref_joints)):
        raise ValueError('Nonfinite recording values')
    first_dead = np.flatnonzero(~alive)
    n_alive = int(first_dead[0]) if len(first_dead) else len(alive)
    if alive[n_alive:].any():
        raise ValueError('Invalid alive mask: a terminated clip became alive again')
    if n_alive < 1:
        raise ValueError('No alive frames in this recording')
    if np.any(frames[:n_alive] < start) or np.any(frames[:n_alive] >= start + clip_len - 1):
        raise ValueError('Frame indices outside clip transition range')
    if not np.array_equal(frames[:n_alive], start + np.arange(n_alive)):
        raise ValueError('Expected one contiguous 50 Hz rollout from the clip first frame')
    if np.any(np.abs(np.linalg.norm(quats[:n_alive], axis=1) - 1.0) > 1e-3):
        raise ValueError('Root quaternions are not normalized wxyz')
    n = n_alive if a.max_seconds is None else min(n_alive, max(1, int(a.max_seconds * 50)))
    contract = load_contract(a.profile, robot=a.robot, xml_path=a.xml_path)
    cfg = make_mjlab_config(contract, 1)
    scene = Scene(cfg.scene, device='cpu')
    model = scene.compile()
    cfg.sim.mujoco.apply(model)
    model.vis.global_.offwidth = max(model.vis.global_.offwidth, a.width)
    model.vis.global_.offheight = max(model.vis.global_.offheight, a.height)
    indices = _model_indices(model, contract.joint_names)
    # Hide collision-only geometry in this rendering model. The two XMLs use
    # different original geom groups; terrain and visual meshes remain visible.
    for geom in indices['robot_geoms']:
        if model.geom_contype[geom] or model.geom_conaffinity[geom]:
            model.geom_group[geom] = 3
    state = mujoco.MjData(model)
    reference_state = mujoco.MjData(model)
    reference_scene = mujoco.MjvScene(model, maxgeom=max(1000, 2 * model.ngeom))
    reference_rgba = np.array([0.0, 0.8, 1.0, a.reference_alpha], dtype=np.float32)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.distance, camera.azimuth, camera.elevation = 3.1, 135.0, -18.0
    options = mujoco.MjvOption()
    options.geomgroup[:] = 0
    # Packaged visual meshes use groups 1 or 2; terrain uses group 0.
    options.geomgroup[0] = options.geomgroup[1] = options.geomgroup[2] = 1
    quaternion = np.empty(4, dtype=np.float64)
    def set_state(data, position, quat, q):
        data.qpos[:] = model.qpos0
        root = indices['root_q']
        data.qpos[root:root + 3] = position
        data.qpos[root + 3:root + 7] = quat
        data.qpos[indices['q']] = q
        mujoco.mj_forward(model, data)

    def caption(pixels, label, ghost=False):
        from PIL import Image, ImageDraw
        image = Image.fromarray(pixels)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, a.width, 49 if ghost else 27), fill=(15, 20, 25))
        draw.text((8, 6), label, fill=(255, 255, 255))
        if ghost:
            draw.text((8, 27), 'Solid: policy  |  Cyan ghost: reference  |  Shared world frame', fill=(90, 225, 255))
        return np.asarray(image)

    def render_state(renderer, position, quat, q, label):
        set_state(state, position, quat, q)
        camera.lookat[:] = [position[0], position[1], max(0.7, position[2])]
        camera.distance = 3.1
        renderer.update_scene(state, camera=camera, scene_option=options)
        return caption(renderer.render(), label)

    def render_ghost(renderer, i, f, ref_quat):
        set_state(state, positions[i], quats[i], joints[i])
        set_state(reference_state, ref_positions[f], ref_quat, ref_joints[f])
        # Camera changes only: retain both actual world poses, including drift.
        midpoint = 0.5 * (positions[i] + ref_positions[f])
        camera.lookat[:] = [midpoint[0], midpoint[1], max(0.7, midpoint[2])]
        camera.distance = max(3.1, 2.4 + 1.15 * np.linalg.norm(positions[i] - ref_positions[f]))
        renderer.update_scene(state, camera=camera, scene_option=options)
        mujoco.mjv_updateScene(model, reference_state, options, None, camera,
                              mujoco.mjtCatBit.mjCAT_ALL, reference_scene)
        append_reference_geoms(renderer.scene, reference_scene, indices['robot_geoms'], reference_rgba)
        return caption(renderer.render(), f'{a.clip} | {i / 50:.2f}s', ghost=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Reserve output exclusively before passing path to ffmpeg.
    with out.open('xb'):
        pass
    try:
        with mujoco.Renderer(model, height=a.height, width=a.width,
                             max_geom=max(1000, 2 * model.ngeom)) as renderer:
            with imageio.get_writer(str(out), format='FFMPEG', fps=50, codec='libx264',
                                    pixelformat='yuv420p', quality=7, macro_block_size=16,
                                    output_params=['-movflags', '+faststart']) as writer:
                for i in range(n):
                    if a.comparison != 'policy':
                        f = frames[i]
                        mujoco.mju_mat2Quat(quaternion, np.asarray(ref_rotations[f], dtype=np.float64).reshape(9))
                    if a.comparison == 'ghost':
                        pred = render_ghost(renderer, i, f, quaternion)
                    else:
                        pred = render_state(renderer, positions[i], quats[i], joints[i],
                                            f'Prediction | {a.clip} | {i / 50:.2f}s')
                    if a.comparison == 'side-by-side':
                        ref = render_state(renderer, ref_positions[f], quaternion, ref_joints[f],
                                           f'Reference | {a.clip} | {i / 50:.2f}s')
                        pred = np.concatenate((pred, ref), axis=1)
                    writer.append_data(pred)
    except BaseException:
        # Preserve partial bytes for diagnosis; never report them as successful video.
        raise
    metadata = dict(
        created_at_utc=datetime.now(timezone.utc).isoformat(), input_path=str(record),
        input_sha256=sha256(record), clip=a.clip, profile=a.profile, robot=a.robot,
        xml_path=contract.xml_path, xml_sha256=contract.xml_sha256,
        output_path=str(out), size_bytes=out.stat().st_size, sha256=sha256(out),
        fps=50, frames=n, duration_seconds=n / 50, alive_frames=n_alive,
        full_reference_transition_frames=clip_len - 1,
        ended_before_reference=n_alive < clip_len - 1,
        preview_truncated=n < n_alive, width=a.width * (2 if a.comparison == 'side-by-side' else 1),
        height=a.height, comparison=a.comparison,
        panels=['policy+reference'] if a.comparison == 'ghost' else
               ['prediction', 'reference'] if a.comparison == 'side-by-side' else ['prediction'],
        reference_rgba=reference_rgba.tolist() if a.comparison == 'ghost' else None,
        coordinate_alignment='none; recorded world positions and orientations are preserved',
        camera_tracking='shared root midpoint, distance expands with separation' if a.comparison == 'ghost' else 'each panel follows its robot',
        root_quaternion_convention='wxyz', joint_order=list(contract.joint_names),
        storage_policy=STORAGE_POLICY,
        interpretation='Visual playback only; use evaluation JSON for success/failure and returns. A preview or early termination is explicitly recorded here.')
    with metadata_path.open('x') as f:
        json.dump(metadata, f, indent=2)
        f.write('\n')
    print(json.dumps({k: metadata[k] for k in ('output_path', 'size_bytes', 'frames', 'duration_seconds', 'ended_before_reference', 'preview_truncated')}))


if __name__ == '__main__':
    main()
