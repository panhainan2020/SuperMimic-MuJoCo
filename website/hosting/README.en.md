# Sites Worker and R2 media

[简体中文](README.md) | **English**

The Worker embeds static pages and small metric files. Videos reside in the R2 binding `BUCKET`, outside Git and the deployment bundle. It has no npm dependencies and does not use D1.

```sh
node --test website/hosting/test_worker.mjs
python website/hosting/build_host.py --checkout "$REGISTERED_SITE_CHECKOUT" --node node
```

Use Node.js 22 or later. The checkout must contain the existing Site's `.openai/hosting.json`. The builder preserves its project ID, configures R2, and emits Worker source and the `dist/` artifact. Run `node scripts/build.mjs` and `node scripts/validate-artifact.mjs` in the generated checkout to rebuild and validate it.

Media routes, same-origin video URLs, accepted sizes and SHA-256 hashes come from [media_manifest.json](../../results/098000/media_manifest.json), with no duplicate allowlist. `GET` / `HEAD /media/<key>` supports single byte ranges, `206` / `416`, ETag and `If-Range`. Verified objects return the full-file hash in `X-Content-SHA256`; HEAD transfers no video.

To publish approved local demonstration videos:

1. Temporarily set the runtime secret `MEDIA_UPLOAD_TOKEN` and flag `MEDIA_UPLOAD_ENABLED="true"` through Sites, then deploy that environment.
2. Send `PUT /admin/media/<key>` with `Authorization: Bearer …`, exact `Content-Length` and `Content-Type: video/mp4`. Each file must match the manifest size and be at most 25 MiB. The Worker reads within that bound and verifies SHA-256 before writing to R2; the receipt includes size, hash and ETag.
3. Verify receipts and HEAD metadata, set the flag to `"false"`, remove the secret and deploy. Confirm that anonymous PUT returns `404`.

Keep secrets in the runtime environment, never CLI arguments, source, manifests or logs. Building and testing require no network access. Training artifacts remain on server persistent storage; this procedure does not authorize downloading remote weights, datasets, replay or archives. It publishes only already-local, explicitly approved demonstration videos.
