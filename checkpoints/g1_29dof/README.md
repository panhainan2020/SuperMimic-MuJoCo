# Tested G1 policy — 98,000 iterations

`policy_098000.pt` is the inference policy used by the published LAFAN1 and
100STYLE evaluations. It contains 26 policy state tensors (including running
normalization buffers), the architecture settings and the robot contract.
It is approximately **34.8 MiB**, tracked directly by Git; Git LFS is not needed
for this artifact. Ordinary authenticated cloning of this private repository
includes the file.

| Setting | Value |
| --- | --- |
| Training iteration | 98,000 |
| Robot | `g1_29dof` (default, 5010 wrist assets) |
| Controller | `upstream` |
| Observation | `legacy99` (the third-party 99D observation) |
| Network | `paper` |
| History / goal frames | 10 / 10 |
| Training motions | 40 complete clips of the third-party G1 LAFAN release |
| OOD evaluation | 3,573 segments / 100 styles; no finetuning |

This is an independently trained reproduction artifact, not official author
weights. It is not a trained policy for `g1_29dof_rev_1_0`.

## Integrity and use

From the repository root, after following the
[environment setup guide](../../docs/installation.md):

```bash
python tools/verify_checkpoint.py
```

The command checks file SHA256/size, tensor digest, architecture and physical
contract, then performs a finite-output CPU forward pass without motion data.
It is a load check, not a new tracking-quality evaluation. For actual evaluation
and video commands see the [main README](../../README.md#evaluation-and-videos)
and [evaluation guide](../../docs/evaluation.md).

[`manifest.json`](manifest.json) records the published file hash, original
inference-file hash, evaluated local-file hash and original training-checkpoint
hash. Every policy tensor was compared with both existing inference files and
is bitwise identical. Only deployment metadata was made portable: machine
paths were cleared/replaced, the default robot was named explicitly and empty
legacy integration fields were removed. Consequently the serialized file SHA
changes, while the learned policy and normalization values do not.

The default robot XML is rebuilt directly from pinned MJLab and Unitree
sources. Its compiled model is identical to the trained asset; the XML text
and its hash differ. The checkpoint's XML-hash metadata was updated after
[compiled-model equivalence checks](../../results/robot_asset_equivalence.json),
with every policy tensor unchanged. The published XML is still checked by
its exact SHA256. Reports and reference results are under
[`results/098000/`](../../results/098000/).

## Scope and storage

This file includes **only the policy**. It has no world model, critic, optimizer
state or replay buffer, so it **cannot resume the full training loop** with
`--resume`. Full resumable checkpoints remain on server persistent storage.

The user explicitly authorized this one already-local policy to be committed
to the private repository. This does not authorize retrieving or publishing
other server weights, datasets, replay, archives or videos. Other large
training artifacts stay on persistent disk; only small text status/metrics
are retrieved, integrity checks run on the server, and previously authorized
shutdown does not wait for downloads.
