#!/usr/bin/env python3
"""Export selected text evidence and build the portable static evaluation site.

No network, model/video reads, training, uploads or artifact downloads. Raw
training artifacts remain on server persistent storage. The export option reads
only explicitly selected, already-local JSON/CSV metadata; it copies no media.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results" / "098000"
LABELS = {"dance": "舞蹈 / Dance", "fallAndGetUp": "跌倒与起身 / Recovery", "fight": "格斗与运动 / Fight", "jumps": "跳跃 / Jump", "run": "跑步 / Run", "sprint": "冲刺 / Sprint", "walk": "行走 / Walk"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pick(value, keys):
    return {key: copy.deepcopy(value[key]) for key in keys if key in value}


def validate_public(value):
    text = json.dumps(value, ensure_ascii=False)
    if re.search(r"/(?:home|root|workspace)/|(?:ssh|scp)\s|root@|hf_[A-Za-z0-9]{15,}|gh[pousr]_[A-Za-z0-9]{15,}", text):
        raise ValueError("Export contains a private path or credential-like value")


def export(experiment):
    source_files = []

    def source(name):
        path = experiment / name
        payload = path.read_bytes()
        source_files.append({"source": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        return json.loads(payload)

    id_report = source("local_evaluation_098000/evaluation_report.json")
    ood = source("ood_100style_20261023/ood_report.json")
    coverage = source("ood_100style_20261023/training_coverage.json")
    id_videos = source("local_evaluation_098000/videos/video_index.json")
    ood_videos = source("ood_100style_20261023/videos/ood_video_index.json")
    summary = {
        "schema_version": 1,
        "evaluation_date": "2026-10-23",
        "checkpoint_iteration": 98000,
        "third_party_baseline": {"repository": "https://github.com/zita-ch/supermimic_vibed", "revision": "a1508d42c9d1699a52e8233ab16d08c488441ab9"},
        "policy": pick(ood["policy"], ["iteration", "policy_sha256", "source_commit", "adaptation"]),
        "evaluation_protocol": ood["evaluation_protocol"],
        "id": pick(id_report, ["checkpoint_iteration", "n_clips", "normalized_return", "failed_clips", "success_fraction", "criterion", "criterion_met", "tracking_metrics_clip_equal_weighted", "completed_at_utc"]),
        "id_drift": {"mean_last_recorded_pre_step_root_error_m": id_report["drift_audit_summary"]["mean_last_recorded_pre_step_root_error_m"]},
        "ood": pick(ood, ["overall", "tracking_diagnostics", "return_precision", "endpoint_loss", "joint_limit_audit_summary"]),
        "comparison": ood["id_ood_comparison"],
        "source_dataset": pick(ood["source_dataset"], ["repo", "revision", "manifest_sha256", "file_index_sha256", "source_mjcf", "source_declared_total_hours", "scope"]),
        "source_url": ood["source_url"],
        "caveats": ood["web_ood"]["notes"],
    }
    public_coverage = {
        "schema_version": 1,
        "conclusion_zh": coverage["conclusion_zh"],
        "training": pick(coverage["training"], ["dataset_families", "contains_100style", "clip_count", "source_frames", "source_fps", "duration_hours_approx", "duration_convention", "clip_names", "theme_counts", "subject_clip_counts", "training_includes_subject5", "scope", "control_resampling", "input_sha256"]),
        "retargeted_release": pick(coverage["retargeted_release"], ["repository", "revision", "folder", "csv_file_count_from_pinned_public_metadata", "all_release_clip_names_equal_protocol_names", "training_coverage_of_this_g1_release_percent", "metadata_items"]),
        "original_lafan1": coverage["original_lafan1"],
        "public_sources": coverage["public_sources"],
    }
    manifest = {"schema_version": 1, "media_in_git": False, "videos": [], "selection": {"lafan": id_videos["selection"], "ood": ood_videos["selection_rule"]}}

    def add_video(item, key, source_dir, is_ood=False):
        path = item.get("path", item.get("output_path"))
        poster = item.get("poster", item.get("preview_path"))
        entry = pick(item, ["category", "clip", "title", "style", "failed", "normalized_return", "duration_seconds", "reference_duration_seconds", "size_bytes", "sha256", "selection"])
        entry.update({"key": key, "poster_key": key[:-4] + ".png", "source_relative_path": source_dir + "/" + Path(path).name, "source_poster_relative_path": source_dir + "/" + Path(poster).name})
        if is_ood:
            entry["poster_sha256"] = item["validation"]["poster_sha256"]
        else:
            entry["poster_sha256"] = item["preview_sha256"]
        manifest["videos"].append(entry)

    add_video(id_videos["overview"], "lafan/overview.mp4", "local_evaluation_098000/videos")
    for item in id_videos["videos"]:
        add_video(item, "lafan/" + item["category"] + ".mp4", "local_evaluation_098000/videos")
    for item in ood_videos["videos"]:
        add_video(item, "100style/" + Path(item["path"]).name, "ood_100style_20261023/videos", True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    for name, obj in [("summary.json", summary), ("training_coverage.json", public_coverage), ("media_manifest.json", manifest)]:
        validate_public(obj)
        write(RESULTS / name, obj)
    csv_inputs = [("local_evaluation_098000/per_clip_metrics.csv", "lafan_per_clip.csv"), ("ood_100style_20261023/per_clip_metrics.csv", "100style_per_clip.csv"), ("ood_100style_20261023/style_metrics.csv", "100style_per_style.csv")]
    for source_name, target_name in csv_inputs:
        path = experiment / source_name
        payload = path.read_bytes()
        source_files.append({"source": source_name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        table = list(csv.DictReader(io.StringIO(payload.decode())))
        # Server/local comparison fields are operational records, not benchmark metrics.
        fields = [key for key in table[0] if key not in ("server_normalized_return", "local_minus_server_return")]
        validate_public(table)
        with (RESULTS / target_name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(table)
    write(RESULTS / "provenance.json", {"schema_version": 1, "sources": source_files, "exporter": "website/build.py", "raw_artifacts_included": False, "note": "Source names are relative evidence labels, not local machine paths. SHA256 identifies the original evidence; exported fields are an explicit public subset."})


def rows(name):
    with (RESULTS / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build(output):
    summary = read(RESULTS / "summary.json")
    manifest = read(RESULTS / "media_manifest.json")
    id_metrics = summary["id"]["tracking_metrics_clip_equal_weighted"]
    all_media = manifest["videos"]
    overview, videos, out_videos = None, [], []
    for item in all_media:
        if item["key"].startswith("100style/"):
            out_videos.append({**pick(item, ["title", "clip", "style", "failed", "normalized_return", "duration_seconds", "reference_duration_seconds"]), "path": item["key"], "poster": item["poster_key"]})
        else:
            row = {"path": item["key"], "poster": item["poster_key"], "durationSeconds": item["duration_seconds"], "sizeBytes": item["size_bytes"]}
            if item["key"] == "lafan/overview.mp4":
                overview = row
            else:
                row.update({"category": item["category"], "label": LABELS[item["category"]], "clip": item["clip"], "return": item["normalized_return"], "failed": item["failed"]})
                videos.append(row)
    prefix = "../results/098000/" if output is None else "results/098000/"
    data = {
        "checkpoint": 98000, "evaluationCompletedUtc": summary["id"]["completed_at_utc"],
        "metrics": {"return": summary["id"]["normalized_return"], "nClips": 40, "nFailed": 0, "criterionMet": summary["id"]["criterion_met"], "jointDeg": id_metrics["joint_mae_deg"], "alignedBodyCm": 100 * id_metrics["tracked_body_xy_yaw_anchored_mpjpe_m"], "rootCm": 100 * id_metrics["root_position_mean_m"], "endRootM": summary["id_drift"]["mean_last_recorded_pre_step_root_error_m"]},
        "labels": LABELS, "videos": videos, "overview": overview,
        "clips": [{"name": r["name"], "category": next((k for k in LABELS if r["name"].startswith(k)), "other"), "return": float(r["normalized_return"]), "failed": r["failed"].lower() == "true", "jointDeg": float(r["joint_mae_deg"]), "alignedBodyCm": 100 * float(r["tracked_body_xy_yaw_anchored_mpjpe_m"]), "rootCm": 100 * float(r["root_position_mean_m"]), "durationSeconds": float(r["expected_transitions"]) / 50} for r in rows("lafan_per_clip.csv")],
        "links": {"report": prefix + "REPORT.md", "csv": prefix + "lafan_per_clip.csv", "metrics": prefix + "summary.json"},
        "dataset": {"description": "本页评估覆盖训练使用的全部 40 条动作，每条从起始帧运行至结束。", "scope": "训练库内评估；不代表未见动作的泛化能力。", "coverage": "LAFAN1 G1 重定向发布版：40 条、264,705 帧、约 2.45 小时，全部参与训练；原始 LAFAN1 为 77 条、约 4.6 小时，本次未覆盖全部原始序列。"},
        "ood": {"status": "complete", "title": "100STYLE 分布外测试", "headline": "100STYLE 全 3573 段 / 100 风格：平均回报 0.8045，完成 3569/3573（99.89%）。", "scope": "固定 98k LAFAN1 策略；100 风格、3573 个独立重置分段；无训练或微调。", "n_clips": 3573, "n_styles": 100, "normalized_return": summary["ood"]["overall"]["normalized_return"], "n_failed": 4, "notes": summary["caveats"], "comparison": summary["comparison"], "sourceUrl": summary["source_url"], "videos": out_videos,
            "links": [{"label": "3573 片段完整指标 CSV", "path": prefix + "100style_per_clip.csv"}, {"label": "100 风格汇总 CSV", "path": prefix + "100style_per_style.csv"}, {"label": "完整报告 / Report", "path": prefix + "REPORT.md"}],
            "styles": [{"name": r["style"], "nClips": int(r["n_clips"]), "nFailed": int(r["n_failed"]), "successFraction": float(r["success_fraction"]), "return": float(r["normalized_return_clip_equal_from_4dp"]), "jointDeg": float(r["clip_equal_weighted_joint_mae_deg"]), "alignedBodyCm": 100 * float(r["clip_equal_weighted_tracked_body_xy_yaw_anchored_mpjpe_m"])} for r in rows("100style_per_style.csv")]},
    }
    validate_public(data)
    target = output or HERE
    target.mkdir(parents=True, exist_ok=True)
    if output:
        if output.resolve() == HERE.resolve():
            raise ValueError("Use no --output-dir for in-place build")
        for name in ("index.html", "app.js", "styles.css", "media-config.js"):
            shutil.copyfile(HERE / name, target / name)
        shutil.copytree(RESULTS, target / "results" / "098000", dirs_exist_ok=True)
    (target / "data.js").write_text("/* Generated by website/build.py; metadata only. */\nwindow.EVALUATION_DATA = " + json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/") + ";\n", encoding="utf-8")
    print(json.dumps({"clips": len(data["clips"]), "styles": len(data["ood"]["styles"]), "media_references": len(all_media), "media_copied": False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, help="Explicit already-local experiment root; omit to rebuild from committed text snapshots")
    parser.add_argument("--output-dir", type=Path, help="Optional standalone deployment folder outside the source website directory")
    args = parser.parse_args()
    if args.experiment_dir:
        export(args.experiment_dir)
    build(args.output_dir)


if __name__ == "__main__":
    main()
