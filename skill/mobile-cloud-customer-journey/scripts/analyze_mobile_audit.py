#!/usr/bin/env python3
"""Analyze a mobile UX audit JSON with the shared model fallback chain."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SHARED_DIR = Path(__file__).resolve().parents[2] / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from ai_provider import call_model_with_fallback


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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
    analysis["provider"] = model_meta["provider"]
    analysis["model"] = model_meta["model"]
    analysis["model_fallback_chain"] = model_meta["fallback_chain"]
    analysis["model_config_path"] = model_meta["config_path"]
    analysis.setdefault("input_url", audit.get("input_url"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
