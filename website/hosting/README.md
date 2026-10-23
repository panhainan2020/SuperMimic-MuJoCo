# Sites Worker with separate R2 media

The Worker embeds only the small static HTML/JS/CSS/JSON/CSV/report files. Videos reside in the Site's R2 binding `BUCKET`, never Git or the deployment bundle. It has no npm dependencies and does not use D1.

```sh
node --test website/hosting/test_worker.mjs
python website/hosting/build_host.py --checkout "$REGISTERED_SITE_CHECKOUT" --node node
```

The checkout must already contain `.openai/hosting.json` with the existing Site project ID. The builder preserves other manifest fields, removes the static-site declaration, sets `r2: "BUCKET"` and `d1: null`, and emits source and `dist/server/index.js` plus `dist/.openai/hosting.json`. Rebuild from the generated checkout using `node scripts/build.mjs`; validate with `node scripts/validate-artifact.mjs`. The repository's portable site references the public HTTPS media URLs; the hosted build uses only the five same-origin showcase URLs and omits the repository link. The source repository is now public; changing repository visibility does not redeploy the existing website.

Public `GET`/`HEAD /media/<key>` supports one byte range, suffix/open ranges, `206`, unsatisfiable `416`, ETag validation and `If-Range`. Only these keys exist in the route whitelist:

- `lafan/overview.mp4`
- `100style/ood_low.mp4`
- `100style/ood_median.mp4`
- `100style/ood_high.mp4`
- `100style/ood_failure.mp4`

To publish owner-authorized media, temporarily configure the runtime secret **`MEDIA_UPLOAD_TOKEN`** and the runtime flag **`MEDIA_UPLOAD_ENABLED="true"`** through Sites. Both are required: a missing flag, `"false"`, or any other value keeps the route disabled even if an older token remains in the runtime. `PUT /admin/media/<key>` requires `Authorization: Bearer …`, exact `Content-Length`, `Content-Type: video/mp4`, a nonempty body and at most **25 MiB per file**. The body streams into R2 through a fixed-length stream; the response includes R2's stored size and ETag. No token is written by the build or returned to visitors. After verified uploads, explicitly set **`MEDIA_UPLOAD_ENABLED="false"`**, remove the token, deploy the new source/environment version, and confirm that an anonymous empty PUT returns `404`. Do not place secrets in CLI arguments, source files, manifests, browser configuration or logs.

The builder and unit tests do not upload, download or access the network. They do not copy media into the code repository. Training artifacts remain on server persistent storage; this hosting implementation does not imply permission to retrieve remote weights, motion datasets, replay or full archives. Media publication uses already-local, explicitly approved demonstration encodings as a separate operation.
