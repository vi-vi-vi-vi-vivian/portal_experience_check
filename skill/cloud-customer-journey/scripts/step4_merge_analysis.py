#!/usr/bin/env python3
"""Merge per-stage analysis files into one stage_analysis JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = ["感知", "下单", "支付", "使用", "续费", "变更", "退订"]


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def stage_analysis_path(root: Path, analysis_dir: Path, stage: str, slug: str | None) -> Path:
    candidates = []
    candidates.append(analysis_dir / f"{stage}.json")
    if slug:
        candidates.append(analysis_dir / f"stage_analysis_{stage}_{slug}.json")
    candidates.append(analysis_dir / f"stage_analysis_{stage}.json")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--crawl-result", default="../../output/web/manual/_crawl.json")
    parser.add_argument("--output", default="../../output/web/manual/audit.json")
    parser.add_argument("--analysis-dir", default=None)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    crawl_path = Path(args.crawl_result)
    if not crawl_path.is_absolute():
        crawl_path = root / crawl_path
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    crawl = load(crawl_path)
    slug = crawl.get("product_slug")
    analysis_dir = Path(args.analysis_dir) if args.analysis_dir else output.parent
    if not analysis_dir.is_absolute():
        analysis_dir = root / analysis_dir
    stage_analysis: dict[str, Any] = {}
    for stage in STAGES:
        path = stage_analysis_path(root, analysis_dir, stage, slug)
        item = load(path)
        if item:
            stage_analysis[stage] = item

    result = {
        "input_url": crawl.get("input_url"),
        "analysis_time": datetime.now(timezone.utc).isoformat(),
        "total_stages_analyzed": len(stage_analysis),
        "stages_analyzed": list(stage_analysis.keys()),
        "stages_missing": [stage for stage in STAGES if stage not in stage_analysis],
        "stage_analysis": stage_analysis,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
