#!/usr/bin/env python3
"""Analyze a mobile UX audit JSON with the shared model fallback chain."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHARED_DIR = Path(__file__).resolve().parents[2] / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from ai_provider import call_model_with_fallback


SEVERITIES = {"p1", "p2"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def collect_images(audit: dict[str, Any], audit_path: Path) -> list[Path]:
    paths: list[Path] = []
    for value in (audit.get("artifacts") or {}).values():
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = audit_path.parent / path
        if path.exists() and path.is_file():
            paths.append(path)
    return paths[:6]


def build_prompt(audit: dict[str, Any]) -> str:
    payload = {
        "input_url": audit.get("input_url"),
        "audit_time": audit.get("audit_time"),
        "dom": audit.get("dom"),
        "tapActionAudit": audit.get("tapActionAudit"),
        "tapActionIssues": audit.get("tapActionIssues"),
        "after_scroll_ctas": audit.get("after_scroll_ctas"),
        "menu": audit.get("menu"),
    }
    return f"""你是华为云移动端页面体验审查专家。请基于移动端截图和 DOM/交互证据输出严格 JSON，不要输出 Markdown。

重点检查：
1. 首屏信息层级、产品/页面主题识别、主 CTA 可发现性。
2. 移动端响应式布局：横向溢出、遮挡、固定栏遮挡、文字换行和可读性。
3. 导航和菜单：是否可打开/关闭/滚动，入口层级是否清晰。
4. 触控体验：点击区域大小、看起来可点但无反馈、CTA 点击结果。
5. 证据质量：每个问题必须引用截图、DOM 字段、按钮文案、元素尺寸、URL 或点击结果。

输出 JSON schema：
{{
  "score": 1-10,
  "is_compliant": true/false,
  "issues": [
    {{
      "title": "短标题",
      "area": "区域",
      "locate": ["真实页面文字或元素"],
      "evidence": "客观依据",
      "standard": "Nielsen #4",
      "severity": "p1|p2",
      "suggestion": "修改前：... -> 修改后：..."
    }}
  ],
  "suggestions": ["可选汇总建议"],
  "analysis_content": "简要说明"
}}

移动端采集数据：
{json.dumps(payload, ensure_ascii=False)[:90000]}
"""


def normalize_issue(issue: dict[str, Any], index: int, screenshot: str | None, page_url: str | None) -> dict[str, Any]:
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
        "id": issue.get("id") or f"mobile-mobile-page-{index:03d}",
        "section": "mobile-page",
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


def first_screenshot(audit: dict[str, Any]) -> str | None:
    artifacts = audit.get("artifacts") or {}
    return artifacts.get("top_screenshot") or artifacts.get("full_screenshot") or artifacts.get("scroll_screenshot")


def summary(score: Any, issues: list[dict[str, Any]]) -> dict[str, Any]:
    result = {"score": score if isinstance(score, (int, float)) else None, "issue_count": len(issues), "p0": 0, "p1": 0, "p2": 0}
    for issue in issues:
        severity = issue.get("severity")
        if severity in {"p0", "p1", "p2"}:
            result[severity] += 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="mobile_page_audit.py output JSON.")
    parser.add_argument("--output", default=None)
    parser.add_argument("--model-config", default=None, help="Shared provider config JSON. Defaults to skill/shared/model_providers.json.")
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--retries-per-model", type=int, default=None)
    parser.add_argument("--retry-sleep-seconds", type=float, default=None)
    parser.add_argument("--model-switch-sleep-seconds", type=float, default=None)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    audit = load_json(input_path)
    default_output = input_path.parent / "audit.json" if input_path.name == "_capture.json" else input_path.with_name("audit.json")
    output = Path(args.output) if args.output else default_output
    if not output.is_absolute():
        output = input_path.parent / output
    analysis, model_meta = call_model_with_fallback(
        build_prompt(audit),
        collect_images(audit, input_path),
        config_path=args.model_config,
        timeout=args.timeout,
        retries_per_model=args.retries_per_model,
        retry_sleep_seconds=args.retry_sleep_seconds,
        model_switch_sleep_seconds=args.model_switch_sleep_seconds,
    )
    screenshot = first_screenshot(audit)
    issues = [normalize_issue(issue, index, screenshot, audit.get("input_url")) for index, issue in enumerate(analysis.get("issues") or [], start=1)]
    section = {
        "id": "mobile-page",
        "name": "移动端页面",
        "url": audit.get("input_url"),
        "title": None,
        "score": analysis.get("score"),
        "is_compliant": analysis.get("is_compliant"),
        "screenshot": screenshot,
        "issues": issues,
        "suggestions": analysis.get("suggestions") or [],
        "analysis_content": analysis.get("analysis_content", ""),
    }
    result = {
        "schema_version": "1.0",
        "source": "mobile",
        "input_url": audit.get("input_url"),
        "generated_at": audit.get("audit_time"),
        "summary": summary(analysis.get("score"), issues),
        "sections": [section],
        "issues": issues,
        "model": {
            "provider": model_meta["provider"],
            "name": model_meta["model"],
            "fallback_chain": model_meta["fallback_chain"],
            "config_path": model_meta["config_path"],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
