# Sources and contributions

This repository is an independent MuJoCo/MJLab port of the third-party
SuperMimic implementation below. It is not an official release by the
SuperMimic paper authors. The method, upstream implementation and simulator
port are credited separately.

## Original method

Qiayuan Liao, Yiyang Shao, Junfeng Long, Kevin Zakka, Roberto Horowitz,
Pieter Abbeel, and Koushil Sreenath. **SuperMimic: Scaling Humanoid Whole-Body
Control with One Differentiable World Model.** arXiv:2610.28480v1,
20 October 2026. [Paper](https://arxiv.org/abs/2610.28480v1).

Credit the paper for the SuperMimic method. This port does not establish the
paper's complete performance, training-time or scaling claims, and does not
reproduce its entire training corpus or every goal interface.

## Upstream third-party implementation

**Chong Zhang, [supermimic_vibed](https://github.com/zita-ch/supermimic_vibed).**
The implementation baseline is pinned to commit
[`a1508d42c9d1699a52e8233ab16d08c488441ab9`](https://github.com/zita-ch/supermimic_vibed/tree/a1508d42c9d1699a52e8233ab16d08c488441ab9).

Original copyright: **Copyright (c) 2026 ETH Zurich, Chong Zhang.** The
upstream implementation is released under the MIT license. Its copyright
and permission notice are preserved in [LICENSE](LICENSE). We thank Chong
Zhang and the upstream contributors for making this implementation available.

This port retains and adapts the upstream differentiable forward kinematics,
rotation utilities, world-model/policy/critic architecture, analytical
rewards, soft termination, reset sampling, and single-GPU learning loop.
The default controller and observation encoding follow that implementation.
The upstream simulator integration targets Isaac Lab 3 / Newton /
MuJoCo-Warp; this repository provides a standalone MuJoCo/MJLab integration.

## This project's contribution

**SuperMimic-MuJoCo contributors** maintain the MuJoCo/MJLab simulator port,
the CPU and CUDA execution backends, two G1 robot configurations, checkpoint
compatibility checks, and standalone training, evaluation and visualization
tools. Changes also address motion-boundary and replay edge cases and
repeated-bin reward updates. These engineering changes build on the upstream
method and implementation; they do not claim authorship of SuperMimic.

The port and its implementation modifications are MIT-licensed. Bundled
robot descriptions and meshes retain their own source-specific notices and
licenses; see [ASSETS.md](ASSETS.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The implementation license
does not relicense assets, datasets, dependencies or result media.

## Citing and acknowledging the work

When reporting research that uses this repository, cite the SuperMimic paper
for the method and identify the pinned third-party implementation as the
code baseline. Also cite this repository and the exact revision used for
experiments when relying on its MuJoCo/MJLab port. Citation metadata for the
port is in [CITATION.cff](CITATION.cff); copyable paper and upstream software
references are in [references.bib](references.bib).

Scientific citations and acknowledgments complement the source copyright
and permission notices; they do not replace them. Preserve applicable notices
when redistributing source or derived distributions.

## Data, checkpoints and storage

Motion datasets and full training checkpoints remain external. The explicitly
published 98k inference policy is an independently trained reproduction
artifact; its provenance and integrity are recorded under
[`checkpoints/g1_29dof/`](checkpoints/g1_29dof/). Curated `results/` snapshots
and `website/` contain portable metrics, reports and media indexes; videos
are hosted separately.

Raw execution outputs belong in the configured experiment directory. Training
artifacts stay on the training server's persistent disk: do not automatically
download, prefetch, mirror, resume-transfer or stream archives, replay or
weights. Only small text status, metrics and necessary metadata may be
retrieved. Integrity and recovery checks run on the server; previously
authorized shutdown follows verification without waiting for downloads and
retains the persistent disk. Publishing the already-local inference policy
does not authorize additional server-artifact downloads.
