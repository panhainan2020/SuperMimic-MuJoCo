# Evaluation results

[简体中文](README.md) | **English** · **[Live results](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)**

This directory contains metrics, evaluation conditions and provenance for the fixed **98,000-iteration** policy. Raw trajectories, full training checkpoints, motion data and videos stay outside Git.

| File | Contents |
| --- | --- |
| [REPORT.md](098000/REPORT.md) | Findings and limitations |
| [summary.json](098000/summary.json) | Full-precision metrics and evaluation conditions |
| [training_coverage.json](098000/training_coverage.json) | Coverage of the 40-clip G1 LAFAN release versus the original 77 sequences |
| [lafan_per_clip.csv](098000/lafan_per_clip.csv) | Per-clip results for 40 LAFAN motions |
| [100style_per_clip.csv](098000/100style_per_clip.csv) | Per-clip results for 3,573 100STYLE segments |
| [100style_per_style.csv](098000/100style_per_style.csv) | Summaries for 100 styles |
| [trajectory_mae.public.json](098000/trajectory_mae.public.json) | Whole-record MAE, coverage, aggregation rules and source hashes |
| [trajectory_mae.per_clip.csv](098000/trajectory_mae.per_clip.csv) | MAE for all 3,613 trajectories |
| [media_manifest.json](098000/media_manifest.json) | Video selection, presentation scope, sizes and hashes |
| [provenance.json](098000/provenance.json) | SHA-256 of the original metric metadata |

The live website shows solid-policy/cyan-reference overlays in 20 videos: seven LAFAN previews, one overview and 12 100STYLE recordings. The 960×540, 25 fps delivery files total about 38 MiB and are hosted separately. See the [website guide](../website/README.en.md) for builds and media configuration.

MAE uses all valid 50 Hz pre-step records; failed clips include only their observed prefix. Both equal-clip and frame-weighted summaries are available. Joint MAE, root XYZ component MAE and root L2 distance have distinct definitions; see the [evaluation guide](../docs/evaluation.en.md).

[Environment validation](release_validation.json) and [robot equivalence](robot_asset_equivalence.json) are recorded separately; the tables above retain the original evaluation metrics.

Training artifacts stay on server persistent storage, with integrity and recovery checks performed there. Retrieve only small text metrics and metadata; do not automatically transfer, prefetch or mirror large files. Previously authorized shutdown does not wait for downloads. The website exporter performs no network operations.
