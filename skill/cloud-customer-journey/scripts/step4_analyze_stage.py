#!/usr/bin/env python3
"""Analyze one journey stage with the shared model fallback chain."""

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


STAGES = ["感知", "下单", "支付", "使用", "续费", "变更", "退订"]
SEVERITIES = {"p0", "p1", "p2"}
STAGE4_FULL_PROMPT_PATH = Path(__file__).resolve().parents[1] / "references" / "stage4_agent_analysis_full.md"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_page(crawl: dict[str, Any], stage: str) -> dict[str, Any]:
    for page in crawl.get("pages", []):
        if page.get("stage") == stage:
            return page
    raise SystemExit(f"stage not found in crawl_result.json: {stage}")


def load_stage4_full_prompt() -> str:
    if not STAGE4_FULL_PROMPT_PATH.exists():
        raise SystemExit(f"missing full stage-4 prompt reference: {STAGE4_FULL_PROMPT_PATH}")
    return STAGE4_FULL_PROMPT_PATH.read_text(encoding="utf-8")


def collect_images(page: dict[str, Any], project_root: Path) -> list[Path]:
    candidates: list[str] = []
    if page.get("screenshot_path"):
        candidates.append(page["screenshot_path"])
    candidates.extend(page.get("region_screenshots") or [])
    paths: list[Path] = []
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_absolute():
            path = project_root / path
        if path.exists() and path.is_file():
            paths.append(path)
    return paths[:6]


def build_prompt(stage: str, page: dict[str, Any]) -> str:
    full_stage4_prompt = load_stage4_full_prompt()
    dom_payload = {
        "stage": stage,
        "url": page.get("url"),
        "title": page.get("title"),
        "body_text": (page.get("body_text") or "")[:12000],
        "structured_html": (page.get("structured_html") or "")[:60000],
        "buttons": page.get("buttons", [])[:80],
        "links": page.get("links", [])[:80],
        "price_info": page.get("price_info", [])[:80],
        "visual_details": page.get("visual_details", [])[:120],
        "element_rects": page.get("element_rects", [])[:120],
        "entry_not_found": page.get("entry_not_found", False),
        "target_product_not_found": page.get("target_product_not_found", False),
        "automation_safety": page.get("automation_safety"),
        "error": page.get("error"),
    }
    return f"""你是华为云产品客户旅程体验审查专家。请分析阶段：{stage}。

请同时利用截图和DOM数据，输出严格JSON，不要输出Markdown。

下面是必须完整遵循的 AI Agent 逐阶段分析全量规则。它来自 cloud-customer-journey 的完整步骤4规范，包含视觉分析、DOM分析、交叉验证、阶段专属探索和跨阶段一致性检查要求。即使当前脚本把视觉截图与DOM数据合并到一次模型调用中，也必须按这些全量检查项逐条覆盖，不得简化、跳过或只做摘要式检查。

<FULL_STAGE4_AGENT_ANALYSIS_RULES>
{full_stage4_prompt}
</FULL_STAGE4_AGENT_ANALYSIS_RULES>

检查维度：
1. 视觉与布局：CTA醒目度、对比度、字号、卡片层级、组件统一性。
2. 交互与流程：入口可达性、按钮href目标、禁用态原因、跳转是否符合阶段目标。
3. 文案与信息：错别字、术语一致性、产品名称一致性、状态标签一致性。
4. 计费与风险：计费周期、单位、公式、0元订单、自动续费、退订/退款后果。
5. 跨页面线索：下单/续费/变更/退订的套餐、价格、产品类型、状态是否一致。

要求：
- 每个问题必须有页面真实文字作为 locate。
- evidence 必须是可观测事实，例如 href、font-size、颜色、disabled、价格、位置、截图中的具体视觉事实。
- standard 必须引用 Nielsen、Garrett、Cooper 或 ISO 9241-110。
- suggestion 必须包含“修改前 -> 修改后”。
- 如果阶段 entry_not_found 为 true，只输出一个入口不可达问题。
- 如果证据不足，issues 返回空数组。

输出JSON schema：
{{
  "stage": "{stage}",
  "score": 1-10,
  "is_compliant": true/false,
  "issues": [
    {{
      "title": "短标题",
      "area": "区域",
      "locate": ["真实页面文字"],
      "evidence": "客观依据",
      "standard": "Nielsen #4",
      "severity": "p0|p1|p2",
      "suggestion": "修改前：... -> 修改后：..."
    }}
  ],
  "suggestions": ["可选汇总建议"],
  "analysis_content": "简要说明"
}}

DOM数据：
{json.dumps(dom_payload, ensure_ascii=False)}
"""


def normalize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    for issue in analysis.get("issues") or []:
        severity = str(issue.get("severity", "p2")).lower()
        issue["severity"] = severity if severity in SEVERITIES else "p2"
        locate = issue.get("locate")
        if isinstance(locate, str):
            issue["locate"] = [locate]
        elif not isinstance(locate, list):
            issue["locate"] = []
    return analysis


def default_output_path(project_root: Path, crawl_path: Path, crawl: dict[str, Any], stage: str) -> Path:
    slug = crawl.get("product_slug")
    if slug and crawl_path.name == "_crawl.json":
        return crawl_path.parent / "stages" / f"{stage}.json"
    return project_root / "../../output/web/manual/stages" / f"{stage}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--crawl-result", default="../../output/web/manual/_crawl.json")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--model-config", default=None, help="Shared provider config JSON. Defaults to skill/shared/model_providers.json.")
    parser.add_argument("--model", default=None, help="Deprecated. Use --model-config.")
    parser.add_argument("--models", default=None, help="Deprecated. Use --model-config.")
    parser.add_argument("--retries-per-model", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=30.0)
    parser.add_argument("--model-switch-sleep-seconds", type=float, default=45.0)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    crawl_path = Path(args.crawl_result)
    if not crawl_path.is_absolute():
        crawl_path = project_root / crawl_path
    crawl = load_json(crawl_path)
    output = Path(args.output) if args.output else default_output_path(project_root, crawl_path, crawl, args.stage)
    if not output.is_absolute():
        output = project_root / output
    page = find_page(crawl, args.stage)
    images = collect_images(page, project_root)
    if args.model or args.models:
        print("Warning: --model/--models are deprecated; edit shared/model_providers.json or use --model-config.", flush=True)
    analysis, model_meta = call_model_with_fallback(
        build_prompt(args.stage, page),
        images,
        config_path=args.model_config,
        timeout=args.timeout,
        retries_per_model=max(1, args.retries_per_model),
        retry_sleep_seconds=max(0, args.retry_sleep_seconds),
        model_switch_sleep_seconds=max(0, args.model_switch_sleep_seconds),
    )
    analysis.setdefault("stage", args.stage)
    analysis["provider"] = model_meta["provider"]
    analysis["model"] = model_meta["model"]
    analysis["model_fallback_chain"] = model_meta["fallback_chain"]
    analysis["model_config_path"] = model_meta["config_path"]
    analysis.setdefault("url", page.get("url"))
    analysis.setdefault("title", page.get("title"))
    analysis.setdefault("screenshot_path", page.get("screenshot_path"))
    analysis = normalize_analysis(analysis)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
