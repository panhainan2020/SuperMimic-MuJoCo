"""Local G1 motion data resampled to 50 Hz, with FK of tracked bodies.

CSV uses ``xyz, quat_xyzw, 29 SDK-order joints``. Compatible joblib motion dictionaries use
``root_trans_offset``, ``root_rot`` (xyzw, or ``pose_aa[:, 0]``), and ``dof`` /
``dof_pos`` in the same joint order. Input files are read in place; no converted
motion archive or other large artifact is written or transferred.
"""

from __future__ import annotations

import glob
import math
import os
from typing import TYPE_CHECKING

import numpy as np
import torch

from .rotations import mat_to_6d, mat_to_quat, quat_slerp, quat_to_mat, so3_exp, so3_log, yaw_mat

if TYPE_CHECKING:
    from .kinematics import G1Kinematics

CONTROL_DT = 0.02
BIN_FRAMES = 50  # 1 s bins of valid transition start frames


def _tensor(value, label: str) -> torch.Tensor:
    try:
        out = torch.as_tensor(value, dtype=torch.float32, device="cpu").detach()
    except (TypeError, ValueError, RuntimeError) as exc:
        raise ValueError(f"{label}: expected a numeric array") from exc
    if not bool(torch.isfinite(out).all()):
        raise ValueError(f"{label}: motion data contains NaN or infinity")
    return out


def _resample(name, p, quat, joints, fps):
    if not math.isfinite(float(fps)) or float(fps) <= 0:
        raise ValueError(f"{name}: source fps must be positive and finite")
    p, quat, joints = (_tensor(x, f"{name}: {k}") for x, k in
                       ((p, "root position"), (quat, "root quaternion"), (joints, "joints")))
    if p.ndim != 2 or p.shape[1] != 3 or p.shape[0] < 2:
        raise ValueError(f"{name}: root position must have shape (T >= 2, 3), got {tuple(p.shape)}")
    T = p.shape[0]
    if quat.shape != (T, 4) or joints.shape != (T, 29):
        raise ValueError(f"{name}: expected quaternion ({T}, 4) and joints ({T}, 29); "
                         f"got {tuple(quat.shape)}, {tuple(joints.shape)}")
    norms = torch.linalg.vector_norm(quat, dim=-1, keepdim=True)
    if bool((norms < 1e-6).any()):
        raise ValueError(f"{name}: zero-norm root quaternion")
    # Preserve the fixed third-party resampling expressions. The interpolator
    # handles quaternion interpolation; do not add a separate input renormalization.
    duration = (T - 1) / float(fps)
    n = int(math.floor(duration / CONTROL_DT)) + 1
    if n < 2:
        raise ValueError(f"{name}: clip is shorter than one {CONTROL_DT:g}s control transition")
    t = torch.arange(n, dtype=torch.float32) * CONTROL_DT * float(fps)
    i0 = t.floor().long().clamp(max=T - 2)
    a = (t - i0.float()).clamp(0, 1)
    p = p[i0] * (1 - a[:, None]) + p[i0 + 1] * a[:, None]
    joints = joints[i0] * (1 - a[:, None]) + joints[i0 + 1] * a[:, None]
    quat = quat_slerp(quat[i0], quat[i0 + 1], a)
    return p, quat, joints


class MotionLib:
    def __init__(self, files: list[str], kin: G1Kinematics, device: str, src_fps: float = 30.0):
        clips = []
        for path in files:
            raw = np.loadtxt(path, delimiter=",", ndmin=2)
            if raw.ndim != 2 or raw.shape[1] != 36:
                raise ValueError(f"{path}: CSV must have 36 columns (xyz, xyzw, 29 joints)")
            name = os.path.splitext(os.path.basename(path))[0]
            quat = raw[:, [6, 3, 4, 5]]  # xyzw -> wxyz
            clips.append((name, *_resample(name, raw[:, :3], quat, raw[:, 7:36], src_fps)))
        self._initialize(clips, kin, device)

    def _initialize(self, clips, kin: G1Kinematics, device: str):
        if not clips:
            raise ValueError("No motion clips found; provide a local CSV directory or compatible joblib .pkl file")
        self.device = device
        self.names = [c[0] for c in clips]
        if len(set(self.names)) != len(self.names):
            raise ValueError("Motion clip names must be unique")
        lens = [c[1].shape[0] for c in clips]
        self.clip_len = torch.tensor(lens, dtype=torch.long, device=device)
        self.clip_start = torch.cumsum(self.clip_len, 0) - self.clip_len
        self.clip_end = self.clip_start + self.clip_len - 1  # inclusive last reference frame
        self.num_frames = sum(lens)
        self.clip_id = torch.repeat_interleave(torch.arange(len(lens), device=device), self.clip_len)

        root_p, root_R, root_v, root_w, jq, jqd = [], [], [], [], [], []
        for _, p, quat, j in clips:
            R = quat_to_mat(quat)
            v, qd = _gradient(p, CONTROL_DT), _gradient(j, CONTROL_DT)
            w = torch.zeros_like(p)
            w[1:-1] = so3_log(R[2:] @ R[:-2].transpose(-1, -2)) / (2 * CONTROL_DT)
            w[0] = so3_log(R[1] @ R[0].T) / CONTROL_DT
            w[-1] = so3_log(R[-1] @ R[-2].T) / CONTROL_DT
            root_p.append(p), root_R.append(R), root_v.append(v), root_w.append(w)
            jq.append(j), jqd.append(qd)
        cat = lambda xs: torch.cat(xs).to(device)
        self.root_p, self.root_R = cat(root_p), cat(root_R)
        self.root_v, self.root_w = cat(root_v), cat(root_w)
        self.q, self.qd = cat(jq), cat(jqd)
        with torch.no_grad():
            body_parts = [[], [], [], []]
            for s in range(0, self.num_frames, 65536):
                e = min(s + 65536, self.num_frames)
                outputs = kin.forward(self.root_p[s:e], self.root_R[s:e], self.root_v[s:e],
                                      self.root_w[s:e], self.q[s:e], self.qd[s:e])
                for parts, out in zip(body_parts, outputs):
                    parts.append(out)
            self.body_p, self.body_R, self.body_v, self.body_w = (torch.cat(parts) for parts in body_parts)
        Rt = self.root_R.transpose(-1, -2)
        self.root_v_local = (Rt @ self.root_v.unsqueeze(-1)).squeeze(-1)
        self.root_w_local = (Rt @ self.root_w.unsqueeze(-1)).squeeze(-1)
        self.root_gz = self.root_R[:, 2, 2]

        # A clip with 51 reference frames has 50 transitions, hence ONE bin.
        # The final reference frame remains available to goals/FK but is never a reset start.
        bin_clip, bin_start, bin_end = [], [], []
        offset = 0
        self.frame_bin = torch.empty(self.num_frames, dtype=torch.long, device=device)
        for c, length in enumerate(lens):
            for start in range(offset, offset + length - 1, BIN_FRAMES):
                end = min(start + BIN_FRAMES, offset + length - 1)
                b = len(bin_start)
                bin_clip.append(c), bin_start.append(start), bin_end.append(end)
                self.frame_bin[start:end] = b
            self.frame_bin[offset + length - 1] = len(bin_start) - 1
            offset += length
        self.bin_clip = torch.tensor(bin_clip, dtype=torch.long, device=device)
        self.bin_start = torch.tensor(bin_start, dtype=torch.long, device=device)
        self.bin_end = torch.tensor(bin_end, dtype=torch.long, device=device)  # exclusive
        self.num_bins = len(bin_start)

    @classmethod
    def from_path(cls, path: str, kin: G1Kinematics, device: str,
                  src_fps: float = 30.0, max_motions: int | None = None) -> MotionLib:
        """Read existing local data; ``max_motions`` limits loading for small smoke checks.

        Joblib/pickle input must be trusted local data, since deserialization can execute code.
        Root positions and joint angles retain their source convention; this loader does not
        apply optional floor-height correction or heading augmentation.
        """
        path = os.fspath(path)
        if max_motions is not None and (not isinstance(max_motions, int) or max_motions < 1):
            raise ValueError("max_motions must be a positive integer")
        if os.path.isdir(path):
            files = sorted(glob.glob(os.path.join(path, "*.csv")))
            return cls(files[:max_motions], kin, device, src_fps)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Motion source does not exist: {path}")
        if path.lower().endswith(".csv"):
            return cls([path], kin, device, src_fps)
        if not path.lower().endswith((".pkl", ".pickle", ".joblib")):
            raise ValueError(f"Unsupported motion source: {path}")
        import joblib
        data = joblib.load(path)
        if not isinstance(data, dict) or not data:
            raise ValueError(f"{path}: expected a nonempty dictionary of motion clips")
        if not all(isinstance(name, str) for name in data):
            raise ValueError(f"{path}: each clip must have a string name")
        clips = []
        # Match the fixed third-party CSV directory's filename ordering so
        # frame/clip IDs do not depend on pickle insertion order.
        for name in sorted(data)[:max_motions]:
            c = data[name]
            if not isinstance(name, str) or not isinstance(c, dict):
                raise ValueError(f"{path}: each clip must have a string name and dictionary value")
            try:
                p = c["root_trans_offset"]
                j = c.get("dof_pos", c.get("dof"))
                if j is None:
                    raise ValueError(f"{name}: missing SDK-order dof_pos or dof array")
                if "root_rot" in c:
                    xyzw = _tensor(c["root_rot"], f"{name}: root_rot")
                    if xyzw.ndim != 2 or xyzw.shape[1] != 4:
                        raise ValueError(f"{name}: root_rot must be (T, 4) in xyzw order")
                    quat = xyzw[:, [3, 0, 1, 2]]
                else:
                    aa = _tensor(c["pose_aa"], f"{name}: pose_aa")
                    if aa.ndim != 3 or aa.shape[1] < 1 or aa.shape[2] != 3:
                        raise ValueError(f"{name}: pose_aa must have shape (T, joints, 3)")
                    quat = mat_to_quat(so3_exp(aa[:, 0]))
                clips.append((name, *_resample(name, p, quat, j, c["fps"])))
            except KeyError as exc:
                raise ValueError(f"{name}: missing motion field {exc.args[0]}") from exc
        obj = cls.__new__(cls)
        obj._initialize(clips, kin, device)
        return obj

    @classmethod
    def from_dir(cls, path: str, kin: G1Kinematics, device: str,
                 src_fps: float = 30.0, max_motions: int | None = None) -> MotionLib:
        """Compatibility entry point; accepts a CSV directory or supported local motion file."""
        return cls.from_path(path, kin, device, src_fps, max_motions)

    def future_frames(self, f: torch.Tensor, K: int) -> torch.Tensor:
        """Frames f+1..f+K clamped to the clip's last frame, shape (B, K)."""
        if not isinstance(K, int) or K < 1:
            raise ValueError("K must be a positive integer")
        end = self.clip_end[self.clip_id[f]]
        fut = f.unsqueeze(-1) + torch.arange(1, K + 1, device=f.device)
        return torch.minimum(fut, end.unsqueeze(-1))

    def goal(self, f: torch.Tensor, K: int) -> torch.Tensor:
        fut = self.future_frames(f, K)
        Ht = yaw_mat(self.root_R[f]).transpose(-1, -2).unsqueeze(1)
        dp = (Ht @ (self.root_p[fut] - self.root_p[f].unsqueeze(1)).unsqueeze(-1)).squeeze(-1)
        rot = mat_to_6d(Ht @ self.root_R[fut])
        feats = torch.cat((dp, rot, self.root_v_local[fut], self.root_w_local[fut],
                           self.q[fut], self.qd[fut] * 0.1), -1)
        return feats.reshape(f.shape[0], -1)

    def ref_state(self, f: torch.Tensor):
        return self.root_p[f], self.root_R[f], self.root_v[f], self.root_w[f], self.q[f], self.qd[f]


def _gradient(x: torch.Tensor, dt: float) -> torch.Tensor:
    g = torch.zeros_like(x)
    g[1:-1] = (x[2:] - x[:-2]) / (2 * dt)
    g[0] = (x[1] - x[0]) / dt
    g[-1] = (x[-1] - x[-2]) / dt
    return g
