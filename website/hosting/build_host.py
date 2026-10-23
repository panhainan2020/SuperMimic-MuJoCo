#!/usr/bin/env python3
"""Compile the public text site into a dependency-free Sites Worker checkout.

No network operations. No videos, weights, datasets or secrets enter this build.
Large training artifacts remain on server persistent storage. Media publication
is a separate, explicitly authorized action by the owner.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEBSITE = HERE.parent
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8", ".csv": "text/csv; charset=utf-8", ".md": "text/plain; charset=utf-8"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    manifest_path = checkout / ".openai/hosting.json"
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get("project_id"):
        raise ValueError("Use an already registered Site checkout with its existing project_id")
    manifest.pop("static", None)
    manifest.update({"r2": "BUCKET", "d1": None})
    assets = {}
    with tempfile.TemporaryDirectory(prefix="supermimic-site-build-") as temp:
        out = Path(temp)
        subprocess.run([sys.executable, str(WEBSITE / "build.py"), "--output-dir", temp], check=True)
        config = {"enabled": True, "baseUrl": "", "overrides": {key: "media/" + key for key in ["lafan/overview.mp4", "100style/ood_low.mp4", "100style/ood_median.mp4", "100style/ood_high.mp4", "100style/ood_failure.mp4"]}, "repositoryUrl": ""}
        (out / "media-config.js").write_text("window.MEDIA_CONFIG = " + json.dumps(config, indent=2) + ";\n")
        # Published labels describe the five hosted examples, not the full local recordings.
        index = (out / "index.html").read_text().replace("查看完整动作、对照参考运动", "查看代表动作、对照参考运动").replace("<small>8 段视频</small>", "<small>概览已公开 · 完整指标可查</small>")
        (out / "index.html").write_text(index)
        for path in sorted(out.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in TYPES:
                raise ValueError("Only approved small text types are embedded")
            raw = path.read_bytes()
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("Individual static text asset exceeds 2 MiB")
            assets["/" + path.relative_to(out).as_posix()] = {"body": raw.decode("utf-8"), "type": TYPES[path.suffix], "bytes": len(raw), "etag": '"' + hashlib.sha256(raw).hexdigest() + '"'}
    template = (HERE / "worker.mjs").read_text()
    marker = "/*__STATIC_ASSETS__*/ {}"
    if template.count(marker) != 1:
        raise ValueError("Expected exactly one static asset marker")
    source = template.replace(marker, json.dumps(assets, ensure_ascii=False, separators=(",", ":")))
    if "MEDIA_UPLOAD_TOKEN =" in source:
        raise ValueError("Secrets belong in runtime environment, never a source assignment")
    (checkout / "worker").mkdir(exist_ok=True)
    (checkout / "scripts").mkdir(exist_ok=True)
    (checkout / "worker/index.js").write_text(source, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    (checkout / "package.json").write_text('{"private":true,"type":"module"}\n')
    for name in ["build.mjs", "validate-artifact.mjs"]:
        shutil.copyfile(HERE / name, checkout / "scripts" / name)
    subprocess.run([args.node, "scripts/build.mjs"], cwd=checkout, check=True)
    subprocess.run([args.node, "scripts/validate-artifact.mjs"], cwd=checkout, check=True)
    print(json.dumps({"embedded_assets": len(assets), "embedded_text_bytes": sum(item["bytes"] for item in assets.values()), "worker_bytes": len(source.encode()), "media_embedded": False}))


if __name__ == "__main__":
    main()
