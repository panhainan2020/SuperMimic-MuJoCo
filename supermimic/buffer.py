"""Fixed-size replay of simulator transitions, laid out as (time, environment).

Replay lives on the training machine; this module performs no artifact transfers.
"""

from __future__ import annotations

import torch

from .mdp import STATE_DIM, XI_DIM

FIELDS = {
    "s": (STATE_DIM, torch.float32),
    "s1": (STATE_DIM, torch.float32),
    "a": (29, torch.float32),
    "a_prev": (29, torch.float32),
    "xi": (XI_DIM, torch.float32),
    "r": ((), torch.float32),
    "f": ((), torch.long),
    "ep_step": ((), torch.int32),
    "done": ((), torch.bool),
}


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


class ReplayBuffer:
    def __init__(self, T: int, N: int, device: str):
        _positive_int(T, "Replay capacity T")
        _positive_int(N, "Environment count N")
        self.T, self.N, self.device = T, N, device
        self.data = {}
        for k, (shape, dt) in FIELDS.items():
            shp = (T, N) + ((shape,) if isinstance(shape, int) else shape)
            self.data[k] = torch.zeros(shp, dtype=dt, device=device)
        self.ptr, self.size = 0, 0

    @torch.no_grad()
    def add(self, tr: dict):
        """Validate a complete vectorized transition before mutating the ring.

        Floating fields must be floating tensors, indices integer tensors, and done boolean.
        Integer widths may differ (the simulator commonly uses int64 episode counters).
        """
        for k, (_, dtype) in FIELDS.items():
            if k not in tr:
                raise ValueError(f"Transition is missing field {k!r}")
            v, target = tr[k], self.data[k][self.ptr]
            if not isinstance(v, torch.Tensor) or v.shape != target.shape:
                raise ValueError(f"Transition {k!r} must be a tensor of shape {tuple(target.shape)}")
            if v.device != target.device:
                raise ValueError(f"Transition {k!r} is on {v.device}, expected {target.device}")
            valid_dtype = (v.is_floating_point() if dtype.is_floating_point else
                           v.dtype == torch.bool if dtype == torch.bool else
                           v.dtype in (torch.int8, torch.int16, torch.int32, torch.int64, torch.uint8))
            if not valid_dtype:
                raise ValueError(f"Transition {k!r} has incompatible dtype {v.dtype}")
        for k in FIELDS:
            self.data[k][self.ptr].copy_(tr[k])
        self.ptr = (self.ptr + 1) % self.T
        self.size = min(self.size + 1, self.T)

    def _row(self, age: torch.Tensor) -> torch.Tensor:
        """Map chronological index (0 = oldest retained step) to storage row."""
        return (self.ptr - self.size + age) % self.T

    def _check_sampling(self, B, length, name):
        _positive_int(B, "Batch size B")
        _positive_int(length, name)
        if self.size == 0:
            raise ValueError("Cannot sample an empty replay buffer; collect transitions first")

    def sample_windows(self, B: int, k: int):
        """k-step windows plus a mask excluding transitions after an episode boundary."""
        self._check_sampling(B, k, "Window length k")
        if self.size < k:
            raise ValueError(f"Replay has {self.size} steps, but a {k}-step window is required; "
                             "collect warmup transitions, including after checkpoint resume")
        t0 = torch.randint(0, self.size - k + 1, (B,), device=self.device)
        env = torch.randint(0, self.N, (B,), device=self.device)
        ages = t0.unsqueeze(-1) + torch.arange(k, device=self.device)
        rows = self._row(ages)
        e = env.unsqueeze(-1).expand_as(rows)
        out = {key: self.data[key][rows, e] for key in ("s", "s1", "a", "xi", "done")}
        d = out["done"].float()
        out["mask"] = torch.cumprod(torch.cat((torch.ones(B, 1, device=self.device), 1 - d[:, :-1]), -1), -1)
        return out

    def _starts_at(self, age: torch.Tensor, env: torch.Tensor, hist: int):
        row = self._row(age)
        ep_step = self.data["ep_step"][row, env].long()
        if bool((ep_step < 0).any()):
            raise ValueError("Replay episode counters must be nonnegative")
        back = torch.arange(hist - 1, -1, -1, device=self.device)
        back = torch.minimum(back.unsqueeze(0), ep_step.unsqueeze(-1))
        back = torch.minimum(back, age.unsqueeze(-1))
        hrows = self._row(age.unsqueeze(-1) - back)
        henv = env.unsqueeze(-1).expand_as(hrows)
        keys = ("s", "a_prev", "xi", "f")
        start = {k: self.data[k][row, env] for k in keys}
        history = {k: self.data[k][hrows, henv] for k in keys}
        return start, history

    def sample_starts(self, B: int, hist: int):
        """Replay start states and histories, padded within their episode and retained data."""
        self._check_sampling(B, hist, "History length hist")
        age = torch.randint(0, self.size, (B,), device=self.device)
        env = torch.randint(0, self.N, (B,), device=self.device)
        return self._starts_at(age, env, hist)

    def sample_valid_starts(self, B: int, hist: int, horizon: int,
                            clip_end: torch.Tensor, clip_id: torch.Tensor):
        """Uniform eligible starts with replacement, without an unbounded rejection loop.

        Enumerates the finite replay candidates once, retaining only starts whose reference
        clip has ``horizon`` transitions remaining. A missing eligible state raises an explicit
        error, so the caller can collect more data or choose a shorter imagination horizon.
        """
        self._check_sampling(B, hist, "History length hist")
        _positive_int(horizon, "Imagination horizon")
        dev = self.data["f"].device
        for value, name in ((clip_end, "clip_end"), (clip_id, "clip_id")):
            if not isinstance(value, torch.Tensor) or value.ndim != 1 or value.numel() == 0:
                raise ValueError(f"{name} must be a nonempty one-dimensional tensor")
            if value.device != dev or value.dtype != torch.long:
                raise ValueError(f"{name} must be torch.long on {dev}")
        if bool(((clip_id < 0) | (clip_id >= clip_end.numel())).any()):
            raise ValueError("clip_id contains an invalid clip index")
        if bool(((clip_end < 0) | (clip_end >= clip_id.numel())).any()):
            raise ValueError("clip_end contains an invalid frame index")
        rows = self._row(torch.arange(self.size, device=self.device))
        frames = self.data["f"][rows]
        if bool(((frames < 0) | (frames >= clip_id.numel())).any()):
            raise ValueError("Replay contains a reference frame outside the motion library")
        valid = frames + horizon <= clip_end[clip_id[frames]]
        candidates = valid.flatten().nonzero(as_tuple=False).flatten()
        if candidates.numel() == 0:
            raise ValueError(f"Replay has no start with {horizon} reference transitions remaining; "
                             "collect additional eligible data or reduce the imagination horizon")
        chosen = candidates[torch.randint(candidates.numel(), (B,), device=self.device)]
        return self._starts_at(chosen // self.N, chosen % self.N, hist)
