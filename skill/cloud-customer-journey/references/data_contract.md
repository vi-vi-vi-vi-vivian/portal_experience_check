# Data Contract

## `crawl_result`

完整流程默认路径为 `../../output/web/<product_slug>/<run_id>/_crawl.json`。手动单步调试默认使用 `../../output/web/manual/_crawl.json`。

Required top-level fields:

- `input_url`: original Huawei Cloud product URL.
- `crawl_time`: ISO-like timestamp.
- `stages_covered`: completed stages.
- `stages_missing`: unavailable or blocked stages.
- `target_product_keywords`: product names or aliases extracted from the awareness page.
- `pages`: stage page records.

Page record fields:

- `stage`: one of `感知`, `下单`, `支付`, `使用`, `续费`, `变更`, `退订`.
- `url`, `title`.
- `screenshot_path`: full-page or viewport screenshot.
- `region_screenshots`: optional region screenshots.
- `body_text`: visible text, truncated if needed.
- `structured_html`: simplified HTML with useful styles and disabled states.
- `buttons`: array of `{text, href, isDisabled}`.
- `links`: array of `{text, href}`.
- `price_info`: array of extracted prices or pricing cards.
- `visual_details`: array of computed style facts.
- `element_rects`: array of `{tag, text, x, y, w, h}`.
- `entry_not_found`: optional boolean.
- `target_product_not_found`: optional boolean.

## `stage_analysis`

完整流程默认路径为 `../../output/web/<product_slug>/<run_id>/audit.json`。阶段中间文件默认写入 `../../output/web/<product_slug>/<run_id>/stages/<阶段>.json`；手动单步调试默认使用 `../../output/web/manual/audit.json`。

```json
{
  "input_url": "https://...",
  "analysis_time": "2026-07-09T12:00:00+08:00",
  "total_stages_analyzed": 7,
  "stages_analyzed": ["感知"],
  "stages_missing": [],
  "stage_analysis": {
    "感知": {
      "stage": "感知",
      "url": "https://...",
      "title": "页面标题",
      "screenshot_path": "../../output/web/modelarts/20260713-173000/screenshots/screenshot_1_awareness.png",
      "score": 8,
      "is_compliant": true,
      "issues": [
        {
          "title": "问题标题",
          "locate": ["定位文字"],
          "evidence": "客观依据",
          "standard": "Garrett: Surface Plane | Nielsen #8",
          "severity": "p1",
          "suggestion": "修改前：... -> 修改后：..."
        }
      ],
      "suggestions": ["可选汇总建议"],
      "analysis_content": "简要分析",
      "provider": "gemini",
      "model": "gemini-3.5-flash",
      "model_fallback_chain": ["gemini:gemini-3.5-flash", "gemini:gemini-2.5-flash"]
    }
  }
}
```

Severity values:

- `p0`: blocking or severe business-flow issue.
- `p1`: important usability, correctness, or transparency issue.
- `p2`: improvement suggestion.
