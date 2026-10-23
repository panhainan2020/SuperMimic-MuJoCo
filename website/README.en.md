# Portable evaluation site

[简体中文](README.md) | **English**

Open `index.html` directly or serve this directory from a static host. Metrics work without a server or external JavaScript dependencies. Reports in the repository layout use relative links to `../results/098000/`.

```sh
# Rebuild the committed small text snapshots, including whole-record MAE and ghost video indexes.
python website/build.py

# Self-contained deployment directory: HTML + small text results, no media.
python website/build.py --output-dir /tmp/supermimic-site

# Maintainer-only refresh from an explicitly selected, existing experiment root.
python website/build.py --experiment-dir "$EXPERIMENT_ROOT"
```

The export selects public JSON fields and CSV metrics, records original metadata hashes, and rejects private machine paths. It reads no checkpoints, datasets, trajectories or videos. No remote artifact download or upload is performed. Preserve raw experiment evidence separately on persistent storage; do not use publication as an implicit authorization to transfer large training artifacts.

## Local preview with ghost overlays and whole-record MAE

Use the [evaluation tools](../docs/evaluation.en.md) to compute MAE and render ghost videos from existing recordings. Supply the media manifest and metrics explicitly and build into the experiment directory, without replacing the published snapshots in this checkout:

```sh
python website/build.py \
  --mae-dir "$SUPERMIMIC_EXPERIMENT_ROOT/trajectory_mae" \
  --media-manifest "$SUPERMIMIC_EXPERIMENT_ROOT/media/media_manifest.json" \
  --output-dir "$SUPERMIMIC_EXPERIMENT_ROOT/site_preview"
```

Ghost videos show a solid policy and cyan reference in the same world frame, preserving position differences. The page distinguishes video preview length, full reference duration and failure status. MAE uses all valid recorded samples, independent of video excerpts. Joint MAE, root XYZ component MAE and root L2 error are labeled separately. Summaries can switch between equal clip weighting and frame weighting; small JSON/CSV files provide the complete values.

This mode creates local files only. It does not upload media, push Git or deploy a website. Place media under the output directory's `media/` path or use a local symlink to existing files; the builder does not copy videos. Review an explicit file list and diff before separately approving any new submission or publication.

## Separately hosted videos

The repository now indexes 20 ghost videos: seven LAFAN previews, one overview and 12 100STYLE recordings. Video files stay outside Git. This source update does not upload media or deploy the separately hosted site. `media-config.js` disables media by default; complete metrics, MAE and video descriptions remain available. The five split-screen examples on the existing live site belong to the previous release. Their historical encoding metadata remains in `results/098000/media_delivery.json` and does not describe the new ghost files.

Configure the new media keys after media hosting is separately approved. Video source URLs are assigned only when the visitor presses play. Posters are not fetched on page load. Missing keys remain unavailable when `baseUrl` is empty.

```js
window.MEDIA_CONFIG = {
  enabled: true,
  baseUrl: "",
  overrides: {
    "ghost_v1/lafan/overview.mp4": "https://media.example.org/supermimic/overview.mp4",
    "ghost_v1/100style/ood_low.mp4": "https://media.example.org/supermimic/ood_low.mp4"
  },
  repositoryUrl: "https://github.com/OWNER/REPOSITORY"
};
```

For a media host containing all files, set `baseUrl` to its public HTTPS prefix. Media keys, presentation scope and delivery hashes are listed in `results/098000/media_manifest.json`, without raw recording paths. Use a stable public media URL with `Content-Type: video/mp4` and byte-range support. H.264/yuv420p MP4 with `faststart` is suitable. Keep compact delivery encodings outside Git; preserve original hashes and record delivery hashes separately.

No tokens, private credentials or expiring signed URLs should be committed. The website supports only HTTPS remote media, relative URLs, and localhost HTTP for development. The source repository is now public at https://github.com/panhainan2020/SuperMimic-MuJoCo. Repository visibility is managed separately from static-site hosting.

To run browser smoke checks using an already-installed Playwright/Chromium:

```sh
python website/check_site.py --browser /path/to/chromium
```

This check verifies the media-disabled page, result navigation, counts, search, sorting, mobile layout and absence of startup media requests. It neither installs a browser nor downloads artifacts. Optional `--experiment-dir` validates playback using already-local videos through a temporary loopback-only server; this reads local media without copying or publishing it.
