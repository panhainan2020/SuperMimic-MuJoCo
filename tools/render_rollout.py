#!/usr/bin/env python3
"""Render one LOCAL SuperMimic --record NPZ clip to an offscreen MP4.

No network/transfer functionality. Server artifacts remain on persistent storage
unless the user separately authorizes transfer. Input must already exist locally;
outputs remain under the experiment root. A video is not a performance metric.
Uses 50 Hz states, wxyz root quaternion, and named SDK-order joints. Optional
side-by-side shows prediction on the left and reference on the right. Set
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--clip', required=True, help='Exact clip name, not numeric index')
    p.add_argument('--output', type=Path, required=True, help='MP4 under SUPERMIMIC_EXPERIMENT_ROOT')
    p.add_argument('--robot', choices=ROBOT_MODELS, default=DEFAULT_ROBOT)
    p.add_argument('--xml-path', type=Path, help='Optional local MJCF override matching the recording')
    p.add_argument('--profile', choices=('upstream', 'paper'), default='upstream')
    p.add_argument('--side-by-side', action='store_true')
    p.add_argument('--width', type=int, default=640, help='Width of each panel, divisible by 16')
    p.add_argument('--height', type=int, default=480, help='Height, divisible by 16')
    p.add_argument('--max-seconds', type=float, default=None, help='Optional explicitly reported preview limit')
    p.add_argument('--gl', choices=('egl', 'osmesa', 'glfw'), default='egl')
    a = p.parse_args()
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
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.distance, camera.azimuth, camera.elevation = 3.1, 135.0, -18.0
    options = mujoco.MjvOption()
    options.geomgroup[:] = 0
    # Packaged visual meshes use groups 1 or 2; terrain uses group 0.
    options.geomgroup[0] = options.geomgroup[1] = options.geomgroup[2] = 1
    quaternion = np.empty(4, dtype=np.float64)
    def render_state(renderer, position, quat, q, label):
        state.qpos[:] = model.qpos0
        root = indices['root_q']
        state.qpos[root:root + 3] = position
        state.qpos[root + 3:root + 7] = quat
        state.qpos[indices['q']] = q
        mujoco.mj_forward(model, state)
        camera.lookat[:] = [position[0], position[1], max(0.7, position[2])]
        renderer.update_scene(state, camera=camera, scene_option=options)
        pixels = renderer.render()
        from PIL import Image, ImageDraw
        image = Image.fromarray(pixels)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, a.width, 27), fill=(15, 20, 25))
        draw.text((8, 6), label, fill=(255, 255, 255))
        return np.asarray(image)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Reserve output exclusively before passing path to ffmpeg.
    with out.open('xb'):
        pass
    try:
        with mujoco.Renderer(model, height=a.height, width=a.width) as renderer:
            with imageio.get_writer(str(out), format='FFMPEG', fps=50, codec='libx264',
                                    pixelformat='yuv420p', quality=7, macro_block_size=16,
                                    output_params=['-movflags', '+faststart']) as writer:
                for i in range(n):
                    pred = render_state(renderer, positions[i], quats[i], joints[i],
                                        f'Prediction | {a.clip} | {i / 50:.2f}s')
                    if a.side_by_side:
                        f = frames[i]
                        mujoco.mju_mat2Quat(quaternion, np.asarray(ref_rotations[f], dtype=np.float64).reshape(9))
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
        preview_truncated=n < n_alive, width=a.width * (2 if a.side_by_side else 1),
        height=a.height, panels=['prediction', 'reference'] if a.side_by_side else ['prediction'],
        root_quaternion_convention='wxyz', joint_order=list(contract.joint_names),
        storage_policy=STORAGE_POLICY,
        interpretation='Visual playback only; use evaluation JSON for success/failure and returns. A preview or early termination is explicitly recorded here.')
    with metadata_path.open('x') as f:
        json.dump(metadata, f, indent=2)
        f.write('\n')
    print(json.dumps({k: metadata[k] for k in ('output_path', 'size_bytes', 'frames', 'duration_seconds', 'ended_before_reference', 'preview_truncated')}))


if __name__ == '__main__':
    main()
