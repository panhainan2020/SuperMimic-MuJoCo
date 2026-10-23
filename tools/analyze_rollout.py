#!/usr/bin/env python3
"""CPU-only pose diagnostics for an existing local SuperMimic evaluation NPZ.

No network or transfer functionality. Inputs must already exist locally. Outputs
stay under SUPERMIMIC_EXPERIMENT_ROOT on the executing machine; server weights,
replay, archives, trajectories and videos stay on its persistent storage.

These are descriptive pre-step pose errors, not additional paper acceptance
criteria. Official normalized return and failure labels come from evaluation.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from supermimic.robot import DEFAULT_ROBOT, ROBOT_MODELS
from supermimic.runtime import artifact_dir, STORAGE_POLICY


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def summarize(errors: dict[str, np.ndarray]) -> dict[str, float]:
    values = {name: float(x.mean()) for name, x in errors.items()
              if not name.endswith('_squared')}
    values['root_position_rmse_m'] = float(np.sqrt(errors['root_position_squared'].mean()))
    values['joint_rmse_rad'] = float(np.sqrt(errors['joint_squared'].mean()))
    values['joint_mae_deg'] = float(np.degrees(values['joint_mae_rad']))
    values['joint_rmse_deg'] = float(np.degrees(values['joint_rmse_rad']))
    return values


def validate_record(record) -> dict[str, np.ndarray]:
    required = ('names', 'root_p', 'root_quat', 'q', 'f', 'alive',
                'ref_root_p', 'ref_root_R', 'ref_q', 'clip_start', 'clip_len')
    if any(k not in record for k in required):
        raise ValueError(f'Record must contain {required}')
    a = {k: record[k] for k in required}
    if a['names'].ndim != 1 or a['names'].dtype.kind not in 'US':
        raise ValueError('names must be a one-dimensional string array')
    c = len(a['names'])
    if c < 1 or len(set(map(str, a['names']))) != c:
        raise ValueError('Clip names must be nonempty and unique')
    if a['alive'].dtype != np.bool_ or a['alive'].ndim != 2 or a['alive'].shape[1] != c:
        raise ValueError('alive must have Boolean shape (T, C)')
    t = a['alive'].shape[0]
    if t < 1:
        raise ValueError('Empty rollout')
    for k in ('f', 'clip_start', 'clip_len'):
        if not np.issubdtype(a[k].dtype, np.integer):
            raise ValueError(f'{k} must be integer')
    if a['clip_start'].shape != (c,) or a['clip_len'].shape != (c,) or np.any(a['clip_len'] < 2):
        raise ValueError('Invalid clip lengths/starts')
    if not np.array_equal(a['clip_start'], np.cumsum(a['clip_len']) - a['clip_len']):
        raise ValueError('Reference clips must be contiguous, starting at frame zero')
    frames = int(a['clip_len'].sum())
    expected = {'root_p': (t, c, 3), 'root_quat': (t, c, 4), 'q': (t, c, 29),
                'f': (t, c), 'ref_root_p': (frames, 3),
                'ref_root_R': (frames, 3, 3), 'ref_q': (frames, 29)}
    for k, shape in expected.items():
        if a[k].shape != shape or not np.isfinite(a[k]).all():
            raise ValueError(f'Invalid shape or nonfinite data in {k}; expected {shape}')
    if not np.allclose(np.linalg.norm(a['root_quat'], axis=-1), 1, atol=1e-3):
        raise ValueError('Root quaternions must be normalized wxyz')
    rr = a['ref_root_R']
    if (not np.allclose(rr @ np.swapaxes(rr, -1, -2), np.eye(3), atol=1e-3)
            or not np.allclose(np.linalg.det(rr), 1, atol=1e-3)):
        raise ValueError('Reference rotations must be proper orthogonal matrices')
    for i in range(c):
        active = np.flatnonzero(a['alive'][:, i])
        if len(active) < 1 or not np.array_equal(active, np.arange(len(active))):
            raise ValueError(f'{a["names"][i]}: alive must form a nonempty prefix')
        if len(active) > a['clip_len'][i] - 1:
            raise ValueError('Cannot have more active transitions than reference transitions')
        if not np.array_equal(a['f'][active, i], a['clip_start'][i] + active):
            raise ValueError(f'{a["names"][i]}: active frames must increment by one from clip_start')
    return a


def analyze(a, kin, torch, quat_to_mat, yaw_mat, chunk: int) -> tuple[dict, list]:
    gathered: dict[str, list[np.ndarray]] = {}
    per_clip = []
    for i, name in enumerate(a['names']):
        active = np.flatnonzero(a['alive'][:, i])
        f = a['f'][active, i]
        p = a['root_p'][active, i].astype(np.float64)
        rp = a['ref_root_p'][f].astype(np.float64)
        q = a['q'][active, i].astype(np.float64)
        rq = a['ref_q'][f].astype(np.float64)
        R = quat_to_mat(torch.as_tensor(a['root_quat'][active, i], dtype=torch.float64)).numpy()
        rR = a['ref_root_R'][f].astype(np.float64)
        d = p - rp
        relative = np.swapaxes(rR, -1, -2) @ R
        sin = 0.5 * np.linalg.norm(np.stack((relative[:, 2, 1] - relative[:, 1, 2],
                                           relative[:, 0, 2] - relative[:, 2, 0],
                                           relative[:, 1, 0] - relative[:, 0, 1]), axis=-1), axis=-1)
        cos = np.clip((np.trace(relative, axis1=-2, axis2=-1) - 1) / 2, -1, 1)
        errors = {
            'root_position_mean_m': np.linalg.norm(d, axis=-1),
            'root_position_squared': (d * d).sum(axis=-1),
            'root_xy_mean_m': np.linalg.norm(d[:, :2], axis=-1),
            'root_height_mae_m': np.abs(d[:, 2]),
            'root_orientation_mean_deg': np.degrees(np.arctan2(sin, cos)),
            'joint_mae_rad': np.abs(q - rq).mean(axis=-1),
            'joint_squared': np.square(q - rq).mean(axis=-1),
        }
        body_world, body_anchored = [], []
        with torch.no_grad():
            for begin in range(0, len(active), chunk):
                end = begin + chunk
                tp, tr, tq, rtp, rtr, rtq = [torch.as_tensor(x[begin:end], dtype=torch.float32)
                                            for x in (p, R, q, rp, rR, rq)]
                zv = torch.zeros_like(tp)
                bp = kin.forward(tp, tr, zv, zv, tq, torch.zeros_like(tq))[0]
                rbp = kin.forward(rtp, rtr, zv, zv, rtq, torch.zeros_like(rtq))[0]
                # Identical XY + yaw reference anchoring to MDP.reward, not Procrustes.
                dr = yaw_mat(tr @ rtr.transpose(-1, -2))
                anchor = torch.cat((tp[:, :2], rtp[:, 2:3]), -1)
                aligned = anchor[:, None] + (dr[:, None] @ (rbp - rtp[:, None])[..., None]).squeeze(-1)
                body_world.append(torch.linalg.vector_norm(bp - rbp, dim=-1).mean(-1).numpy())
                body_anchored.append(torch.linalg.vector_norm(bp - aligned, dim=-1).mean(-1).numpy())
        errors['tracked_body_world_mpjpe_m'] = np.concatenate(body_world)
        errors['tracked_body_xy_yaw_anchored_mpjpe_m'] = np.concatenate(body_anchored)
        total = int(a['clip_len'][i]) - 1
        per_clip.append({'name': str(name), 'valid_pre_step_samples': len(active),
                         'expected_transitions': total, 'sample_coverage_fraction': len(active) / total,
                         'recorded_sample_time_range_s': [0.0, (len(active) - 1) * 0.02],
                         **summarize(errors)})
        for key, value in errors.items():
            gathered.setdefault(key, []).append(value)
    frame_weighted = summarize({key: np.concatenate(value) for key, value in gathered.items()})
    clip_weighted = {key: float(np.mean([row[key] for row in per_clip])) for key in frame_weighted}
    return {'frame_weighted': frame_weighted, 'clip_equal_weighted': clip_weighted}, per_clip


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--evaluation', type=Path, help='Authoritative evaluation.json from the same invocation')
    parser.add_argument('--output', type=Path, required=True, help='JSON under SUPERMIMIC_EXPERIMENT_ROOT')
    parser.add_argument('--robot', choices=ROBOT_MODELS, default=DEFAULT_ROBOT)
    parser.add_argument('--xml-path', type=Path, help='Same verified local MJCF used for this evaluation')
    parser.add_argument('--chunk', type=int, default=4096)
    args = parser.parse_args()
    if args.chunk < 1:
        parser.error('--chunk must be positive')
    args.output = args.output.expanduser().resolve()
    args.record = args.record.expanduser().resolve()
    if args.output.suffix.lower() != '.json':
        parser.error('--output must have a .json extension')
    artifact_dir(args.output.parent)
    if args.output.exists():
        parser.error('Refusing to overwrite an existing analysis')
    import torch
    from supermimic.kinematics import G1Kinematics
    from supermimic.robot import TRACKED_BODIES, G1_JOINT_NAMES, robot_xml_path
    from supermimic.rotations import quat_to_mat, yaw_mat
    torch.set_num_threads(4)
    xml = robot_xml_path(args.robot, args.xml_path)
    kin = G1Kinematics('cpu', xml_path=str(xml))
    with np.load(args.record, allow_pickle=False) as record:
        arrays = validate_record(record)
    aggregate, per_clip = analyze(arrays, kin, torch, quat_to_mat, yaw_mat, args.chunk)
    result = {
        'record': str(args.record.resolve()), 'record_sha256': sha256(args.record),
        'robot': args.robot, 'xml_path': str(xml), 'xml_sha256': sha256(xml), 'control_dt_s': 0.02,
        'n_clips': len(per_clip), 'valid_pre_step_samples': sum(x['valid_pre_step_samples'] for x in per_clip),
        'joint_names': G1_JOINT_NAMES, 'tracked_bodies': TRACKED_BODIES,
        'metric_scope': 'Descriptive pose diagnostics on pre-step states with alive=True; all errors lower is better.',
        'conventions': [
            'Compare recorded S_t with reference indexed by recorded global f_t; do not shift reference by one.',
            'Only alive=True samples are included. Frozen padding after completion/termination is excluded.',
            'Reset frame is included. The final post-step state that completes or terminates each clip is not recorded.',
            'Pose errors are conditional on survival, so failures require separate evaluation.json reporting.',
            'Joint error is direct SDK-order angle difference, without angle wrapping (29 bounded hinge joints).',
            'Root orientation is SO(3) geodesic angle; quaternion order is wxyz.',
            'MPJPE averages Euclidean link-origin errors over the 14 tracked bodies, not all joints or visual vertices.',
            'Anchored MPJPE uses exactly reward XY+yaw reanchoring; world MPJPE retains global drift.',
            'Frame-weighted averages pool valid samples. Equal-clip averages weight every clip equally, including clip RMSE.',
            'NPZ omits actions and simulator velocities; these metrics do not reconstruct normalized return.',
        ],
        'storage_policy': STORAGE_POLICY,
        **aggregate, 'per_clip': per_clip,
    }
    if args.evaluation:
        evaluation = json.loads(args.evaluation.read_text())
        if set(evaluation['per_clip']) != set(map(str, arrays['names'])):
            raise ValueError('Evaluation JSON and rollout have different clip sets')
        if evaluation['n_failed'] != len(evaluation['failed']) or not set(evaluation['failed']).issubset(evaluation['per_clip']):
            raise ValueError('Inconsistent authoritative failure labels')
        result['official_evaluation'] = evaluation
        result['evaluation_json_sha256'] = sha256(args.evaluation)
        for row in per_clip:
            row['normalized_return'] = evaluation['per_clip'][row['name']]
            row['failed'] = row['name'] in evaluation['failed']
    with args.output.open('x') as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'output': str(args.output), 'n_clips': result['n_clips'], **aggregate}, indent=2))


if __name__ == '__main__':
    main()
