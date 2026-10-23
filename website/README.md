# Portable evaluation site

Open `index.html` directly or serve this directory from a static host. Metrics work without a server or external JavaScript dependencies. Reports in the repository layout use relative links to `../results/098000/`.

```sh
# Rebuild using only the committed small text snapshots.
python website/build.py

# Self-contained deployment directory: HTML + small text results, no media.
python website/build.py --output-dir /tmp/supermimic-site

# Maintainer-only refresh from an explicitly selected, existing experiment root.
python website/build.py --experiment-dir "$EXPERIMENT_ROOT"
```

The export selects public JSON fields and CSV metrics, records original metadata hashes, and rejects private machine paths. It reads no checkpoints, datasets, trajectories or videos. No remote artifact download or upload is performed. Preserve raw experiment evidence separately on persistent storage; do not use publication as an implicit authorization to transfer large training artifacts.

## Separately hosted videos

The configured demonstration site serves five selected examples from R2; `media-config.js` uses public HTTPS URLs so a repository checkout can play them too. The full result tables are always available. Unpublished video slots say “该片段暂未公开，指标见下表 / Video not published.” Video source URLs are assigned only when the visitor presses play. Posters are not fetched on page load. Missing keys remain unavailable when `baseUrl` is empty. Set `enabled: false` for an entirely offline metadata-only page.

```js
window.MEDIA_CONFIG = {
  enabled: true,
  baseUrl: "",
  overrides: {
    "lafan/overview.mp4": "https://media.example.org/supermimic/overview.mp4",
    "100style/ood_low.mp4": "https://media.example.org/supermimic/ood_low.mp4",
    "100style/ood_median.mp4": "https://media.example.org/supermimic/ood_median.mp4",
    "100style/ood_high.mp4": "https://media.example.org/supermimic/ood_high.mp4",
    "100style/ood_failure.mp4": "https://media.example.org/supermimic/ood_failure.mp4"
  },
  repositoryUrl: "https://github.com/OWNER/REPOSITORY"
};
```

For a media host containing all files, set `baseUrl` to its public HTTPS prefix. Keys and original experiment-relative source filenames are listed in `results/098000/media_manifest.json`. Use a stable public media URL with `Content-Type: video/mp4` and byte-range support. H.264/yuv420p MP4 with `faststart` is suitable. Keep compact delivery encodings outside Git; preserve original hashes and record delivery hashes separately.

No tokens, private credentials or expiring signed URLs should be committed. The website supports only HTTPS remote media, relative URLs, and localhost HTTP for development. A private GitHub repository link may be omitted from public deployment until source publication. Publishing the static website does not make the private code repository public.

To run browser smoke checks using an already-installed Playwright/Chromium:

```sh
python website/check_site.py --browser /path/to/chromium
```

This check verifies the media-disabled page, result navigation, counts, search, sorting, mobile layout and absence of startup media requests. It neither installs a browser nor downloads artifacts. Optional `--experiment-dir` validates playback using already-local videos through a temporary loopback-only server; this reads local media without copying or publishing it.
