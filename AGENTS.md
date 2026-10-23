# Scope and storage

## Current publication restriction

This checkout's origin is public. Publish only changes within the user's authorized scope after checking the exact file list and diff. Stage explicit paths; never include unrelated worktree files, private research details or unreviewed artifacts. These restrictions apply to all agents and survive context compaction.

The current task is explicitly authorized to publish the reviewed evaluation website and its 20 existing demonstration MP4 files to the existing public Site, and to simplify and synchronize the repository documentation. Keep videos in independent object storage, outside Git. This authorization does not cover other artifacts or projects. Disable the temporary media-upload endpoint after verifying storage integrity.

This independent repository ports zita-ch/supermimic_vibed to MuJoCo / MJLab.
Do not modify other projects or their environments. This repository has no dependency on another application checkout.

Raw experiment protocols, frozen configurations, logs, checkpoints and evaluation records remain in the task's configured external experiment directory. Set SUPERMIMIC_EXPERIMENT_ROOT accordingly for local validation, or to persistent storage on a server. Keep machine-specific absolute paths and unrelated research plans out of this repository.

The user's 2026-10-23 publication request explicitly authorizes curated, portable result snapshots in results/ and website/ source in this repository. Those snapshots must contain only small public metrics, reports, provenance and media indexes; strip machine paths, credentials and private operational details. The canonical raw experiment records remain in the experiment directory. Videos, replay, raw motion data and environments never enter Git. Public demonstration videos may be served from independent media storage under this publication request; this does not authorize retrieving new server artifacts.

The user's subsequent explicit request authorizes committing the already-local, tested 98k inference policy as checkpoints/g1_29dof/policy_098000.pt to this repository. The user's latest instruction explicitly authorizes making the clean code and this bundled policy public. This is a single-file exception, not permission to download further server weights or include full training checkpoints, optimizer states or replay. Preserve every policy tensor, sanitize machine-specific metadata, and record source/output hashes and compatibility in the accompanying manifest. Other checkpoint files remain excluded.

Default robot g1_29dof must remain compatible with the trained model. g1_29dof_rev_1_0 is a separate model/training condition. Preserve source-specific asset licenses; do not claim the whole repository is MIT.

Training artifacts remain on the training server's persistent disk. Never automatically download, prefetch, mirror, resume-transfer or stream archives, replay, weights or other large artifacts. Only small text status, metrics and necessary metadata may be retrieved. Integrity and recovery checks run on the server. Existing authorized shutdown happens after training, persistent-storage checks and authorized tests; do not wait for downloads. No scripts here download data or models.
