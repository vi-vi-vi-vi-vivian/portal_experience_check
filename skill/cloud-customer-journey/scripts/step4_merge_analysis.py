#!/usr/bin/env python3
"""Merge per-stage analysis files into one stage_analysis JSON."""

from __future__ import annotations

import argparse
import json
import re
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


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def split_suggestion(value: Any) -> tuple[str, str]:
    text = compact_text(value)
    if not text:
        return "", ""
    patterns = [
        r"修改前[:：]?(?P<before>.*?)(?:->|→|修改后[:：])(?P<after>.*)",
        r"现状[:：](?P<before>.*?)(?:建议[:：]|修改为[:：])(?P<after>.*)",
        r"(?P<before>.+?)(?:->|→)(?P<after>.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            before = re.sub(r"^修改前[:：]\s*", "", compact_text(match.group("before")))
            after = re.sub(r"^(?:->|→)?\s*修改后[:：]\s*", "", compact_text(match.group("after")))
            after = re.sub(r"^建议[:：]\s*", "", after)
            return before, after
    return "", re.sub(r"^建议[:：]\s*", "", text)


def classify_issue(issue: dict[str, Any], before: str, after: str) -> str:
    text = compact_text(
        " ".join(
            str(issue.get(key) or "")
            for key in ["title", "area", "evidence", "standard", "suggestion"]
        )
        + f" {before} {after}"
    ).lower()
    if any(token in text for token in ["错别字", "错字", "笔误", "typo", "误写", "应为", "漏字", "多字"]):
        return "typo"
    if any(token in text for token in ["标点", "空格", "大小写", "格式", "全角", "半角", "文案规范"]):
        return "copy_format"
    if any(token in text for token in ["退订", "退款", "支付", "续费", "计费", "自动续费", "扣款", "订单", "权益"]):
        return "billing_risk"
    if any(token in text for token in ["href", "链接", "跳转", "url", "目标不精准", "错误跳转"]):
        return "link_target"
    if any(token in text for token in ["点击", "按钮", "无响应", "交互", "菜单", "触控", "热区", "禁用", "置灰"]):
        return "interaction"
    if any(token in text for token in ["布局", "遮挡", "横向溢出", "字号", "对比度", "颜色", "视觉", "卡片", "换行"]):
        return "layout"
    if any(token in text for token in ["缺少", "不完整", "说明不清", "术语", "解释", "信息"]):
        return "content_clarity"
    return "unknown"


def normalize_issue(issue: dict[str, Any], source: str, section: str, index: int, screenshot: str | None, page_url: str | None) -> dict[str, Any]:
    severity = str(issue.get("severity", "p2")).lower()
    if severity not in SEVERITIES:
        severity = "p2"
    locate = issue.get("locate")
    if isinstance(locate, str):
        locate = [locate]
    elif not isinstance(locate, list):
        locate = []
    before, after = split_suggestion(issue.get("suggestion"))
    issue_type = classify_issue(issue, before, after)
    return {
        "id": issue.get("id") or issue_id(source, section, index),
        "section": section,
        "type": issue_type,
        "severity": severity,
        "title": issue.get("title", ""),
        "area": issue.get("area", ""),
        "page_url": page_url or "",
        "locate": locate,
        "evidence": issue.get("evidence", ""),
        "standard": issue.get("standard", ""),
        "suggestion_before": before,
        "suggestion_after": after,
        "auto_fix_eligible": issue_type in {"typo", "copy_format"},
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
            screenshot = item.get("screenshot_path")
            page_url = item.get("url")
            stage_issues = []
            for index, issue in enumerate(item.get("issues") or [], start=1):
                normalized = normalize_issue(issue, "web", stage, index, screenshot, page_url)
                stage_issues.append(normalized)
                issues.append(normalized)
            normalized_item = dict(item)
            normalized_item["issues"] = stage_issues
            stage_analysis[stage] = normalized_item
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
