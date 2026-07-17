#!/usr/bin/env python3
"""Merge per-stage analysis files into one stage_analysis JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGES = ["感知", "下单", "支付", "使用", "续费", "变更", "退订"]
SEVERITIES = ["p0", "p1", "p2"]


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


def issue_id(source: str, section: str, index: int) -> str:
    safe_section = "".join(ch if ch.isalnum() else "-" for ch in section).strip("-") or "section"
    return f"{source}-{safe_section}-{index:03d}"


def normalize_issue(issue: dict[str, Any], source: str, section: str, index: int, screenshot: str | None) -> dict[str, Any]:
    severity = str(issue.get("severity", "p2")).lower()
    if severity not in SEVERITIES:
        severity = "p2"
    locate = issue.get("locate")
    if isinstance(locate, str):
        locate = [locate]
    elif not isinstance(locate, list):
        locate = []
    return {
        "id": issue.get("id") or issue_id(source, section, index),
        "section": section,
        "severity": severity,
        "title": issue.get("title", ""),
        "area": issue.get("area", ""),
        "locate": locate,
        "evidence": issue.get("evidence", ""),
        "standard": issue.get("standard", ""),
        "suggestion": issue.get("suggestion", ""),
        "screenshot": issue.get("screenshot") or screenshot,
    }


def summarize(sections: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [section.get("score") for section in sections if isinstance(section.get("score"), (int, float))]
    summary = {
        "score": round(sum(scores) / len(scores), 1) if scores else None,
        "issue_count": len(issues),
        "p0": 0,
        "p1": 0,
        "p2": 0,
    }
    for issue in issues:
        severity = issue.get("severity")
        if severity in {"p0", "p1", "p2"}:
            summary[severity] += 1
    return summary


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
    sections: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    model_info: dict[str, Any] = {}
    for stage in STAGES:
        path = stage_analysis_path(root, analysis_dir, stage, slug)
        item = load(path)
        if item:
            stage_analysis[stage] = item
            screenshot = item.get("screenshot_path")
            stage_issues = []
            for index, issue in enumerate(item.get("issues") or [], start=1):
                normalized = normalize_issue(issue, "web", stage, index, screenshot)
                stage_issues.append(normalized)
                issues.append(normalized)
            sections.append(
                {
                    "id": stage,
                    "name": stage,
                    "url": item.get("url"),
                    "title": item.get("title"),
                    "score": item.get("score"),
                    "is_compliant": item.get("is_compliant"),
                    "screenshot": screenshot,
                    "issues": stage_issues,
                    "suggestions": item.get("suggestions") or [],
                    "analysis_content": item.get("analysis_content", ""),
                }
            )
            if not model_info and item.get("model"):
                model_info = {
                    "provider": item.get("provider"),
                    "name": item.get("model"),
                    "fallback_chain": item.get("model_fallback_chain") or [],
                    "config_path": item.get("model_config_path"),
                }

    result = {
        "schema_version": "1.0",
        "source": "web",
        "input_url": crawl.get("input_url"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize(sections, issues),
        "sections": sections,
        "issues": issues,
        "model": model_info,
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
