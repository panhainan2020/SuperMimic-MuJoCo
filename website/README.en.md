# Evaluation website

[简体中文](README.md) | **English** · **[Live results](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)**

The website presents LAFAN and 100STYLE evaluations of the fixed 98k policy:

- A solid policy robot and cyan reference ghost share one world frame and camera, preserving position differences.
- Seven LAFAN previews, one overview and 12 100STYLE videos, with video length, reference duration and failure status labeled separately.
- Whole-record joint MAE and root XYZ component MAE alongside return and pose metrics, with equal-clip/frame-weighted summaries and JSON/CSV downloads.

MAE uses all valid 50 Hz pre-step records, independently of video excerpts. Failed clips include only the observed prefix, with coverage reported separately. See the [evaluation guide](../docs/evaluation.en.md) for metric definitions and rendering commands.

## Build and preview

No external JavaScript dependencies are required. Open `index.html` directly or serve the build directory from a static host:

```sh
# Use the repository's small metric files and media manifest.
python website/build.py

# Build a standalone deployment directory without copying videos.
python website/build.py --output-dir /tmp/supermimic-site
```

Build a preview from existing experiment metrics and a media manifest:

```sh
python website/build.py \
  --mae-dir "$SUPERMIMIC_EXPERIMENT_ROOT/trajectory_mae" \
  --media-manifest "$SUPERMIMIC_EXPERIMENT_ROOT/media/media_manifest.json" \
  --output-dir "$SUPERMIMIC_EXPERIMENT_ROOT/site_preview"
```

Maintainers can refresh base result snapshots with `--experiment-dir "$SUPERMIMIC_EXPERIMENT_ROOT"`. The exporter selects public JSON/CSV fields, records metadata hashes and rejects private machine paths. It does not read or transfer weights, datasets, trajectories or videos. Raw experiment artifacts stay on server persistent storage.

## Video hosting

Videos use separate media storage. [`media_manifest.json`](../results/098000/media_manifest.json) lists their keys, presentation scope and file hashes. Configure media URLs in `media-config.js`:

```js
window.MEDIA_CONFIG = {
  enabled: true,
  baseUrl: "https://supermimic-mujoco-results.zippyaspen7.chatgpt.site/media",
  overrides: {},
  repositoryUrl: "https://github.com/panhainan2020/SuperMimic-MuJoCo"
};
```

Media keys are appended to `baseUrl`; `overrides` assigns alternative URLs to individual keys. For offline previews, use a relative `media` path and place existing videos or symlinks there. Videos load only after a visitor presses play; videos and posters are not prefetched.

The media service must support `video/mp4` and byte-range requests. H.264/yuv420p MP4 with `faststart` is recommended. Remote URLs must use HTTPS; localhost HTTP is allowed for development. Never include tokens or private credentials in configuration. See the [hosting guide](hosting/README.en.md) for Sites / R2 deployment. Building, pushing Git and deploying the live site are separate steps; the builder does not publish automatically.

## Browser checks

Use an installed Playwright and Chromium:

```sh
python website/check_site.py --browser /path/to/chromium
```

Checks cover metric navigation, video counts, search/sorting, mobile layout and absence of prefetches. Optional `--experiment-dir` tests playback from existing local videos. No browser or remote artifacts are downloaded.
