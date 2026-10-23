# Evaluation snapshots

This directory contains selected, portable text evidence for the frozen **98,000-iteration** policy. It is a historical snapshot, not a claim about the newest training checkpoint. Raw recordings, checkpoints, motion datasets and videos are excluded from Git.

| File | Purpose |
| --- | --- |
| [098000/REPORT.md](098000/REPORT.md) | Chinese / English findings and limitations |
| [098000/summary.json](098000/summary.json) | Full-precision aggregates and evaluation conditions |
| [098000/training_coverage.json](098000/training_coverage.json) | 40-clip retargeted release versus original 77-sequence LAFAN1 |
| [098000/lafan_per_clip.csv](098000/lafan_per_clip.csv) | 40 training-motion evaluations |
| [098000/100style_per_clip.csv](098000/100style_per_clip.csv) | All 3,573 converted 100STYLE segments |
| [098000/100style_per_style.csv](098000/100style_per_style.csv) | 100 style summaries |
| [098000/media_manifest.json](098000/media_manifest.json) | Media IDs, selection rules, original hashes; no media payloads |
| [098000/provenance.json](098000/provenance.json) | SHA256 of the source metadata before public-field selection |

The [static results site](../website/index.html) reads these committed snapshots. See [website/README.md](../website/README.md) for rebuilding and separately hosted media.

The [public evaluation page](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site) serves the same metrics. Five complete demonstration videos use external object storage; [media_delivery.json](098000/media_delivery.json) records their delivery encoding, sizes and hashes. Their compact 960×360, 25 fps copies total 11.93 MiB. Original evaluation recordings remain unchanged and outside Git.

Training artifacts stay on server persistent storage. Evaluation, backup and publication requests do not imply permission to download remote weights, datasets, replay or full archives. This snapshot was exported from already-authorized local text evidence; its exporter performs no network operations.

The [release validation](release_validation.json) records the subsequent
38-test CPU/CUDA check and 40-clip LAFAN evaluation of the bundled policy
with the reproducibly generated robot. [Robot equivalence](robot_asset_equivalence.json)
compares the compiled models; the frozen 98k tables above retain their original
run metrics. The 100STYLE evaluation was not rerun for this packaging change.
