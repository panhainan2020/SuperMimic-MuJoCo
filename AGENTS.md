# Scope and storage

## Current publication restriction

The user's latest instruction on 2026-10-23 supersedes earlier publication permissions for new changes: do not stage, commit, push, upload media, or deploy a website automatically. This checkout's origin is public. Prepare and validate changes locally, then present the exact proposed file list and diff for the user's explicit approval before any new submission or publication. Never include unrelated worktree files. Existing public releases remain unchanged. This restriction applies to all agents and survives context compaction.

The user's subsequent approval on 2026-10-23 authorizes committing and pushing the reviewed evaluation website update, its rendering/MAE tools and tests, supporting documentation, sanitized media index and small public MAE tables. This approval covers only that update. It does not authorize uploading video, deploying the hosted website, publishing unrelated worktree files, or any later unreviewed changes. Stage explicit reviewed paths only.

This independent repository ports zita-ch/supermimic_vibed to MuJoCo / MJLab.
Do not modify other projects or their environments. This repository has no dependency on another application checkout.

Raw experiment protocols, frozen configurations, logs, checkpoints and evaluation records remain in the task's configured external experiment directory. Set SUPERMIMIC_EXPERIMENT_ROOT accordingly for local validation, or to persistent storage on a server. Keep machine-specific absolute paths and unrelated research plans out of this repository.

The user's 2026-10-23 publication request explicitly authorizes curated, portable result snapshots in results/ and website/ source in this repository. Those snapshots must contain only small public metrics, reports, provenance and media indexes; strip machine paths, credentials and private operational details. The canonical raw experiment records remain in the experiment directory. Videos, replay, raw motion data and environments never enter Git. Public demonstration videos may be served from independent media storage under this publication request; this does not authorize retrieving new server artifacts.

The user's subsequent explicit request authorizes committing the already-local, tested 98k inference policy as checkpoints/g1_29dof/policy_098000.pt to this repository. The user's latest instruction explicitly authorizes making the clean code and this bundled policy public. This is a single-file exception, not permission to download further server weights or include full training checkpoints, optimizer states or replay. Preserve every policy tensor, sanitize machine-specific metadata, and record source/output hashes and compatibility in the accompanying manifest. Other checkpoint files remain excluded.

Default robot g1_29dof must remain compatible with the trained model. g1_29dof_rev_1_0 is a separate model/training condition. Preserve source-specific asset licenses; do not claim the whole repository is MIT.

Training artifacts remain on the training server's persistent disk. Never automatically download, prefetch, mirror, resume-transfer or stream archives, replay, weights or other large artifacts. Only small text status, metrics and necessary metadata may be retrieved. Integrity and recovery checks run on the server. Existing authorized shutdown happens after training, persistent-storage checks and authorized tests; do not wait for downloads. No scripts here download data or models.
