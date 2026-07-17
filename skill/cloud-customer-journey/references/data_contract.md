# Data Contract

## Final `audit.json`

Web and mobile final reports use the same top-level schema.

Web default path:

`../../output/web/<product_slug>/<run_id>/audit.json`

Mobile default path:

`../../output/mobile/<page_slug>/<run_id>/audit.json`

```json
{
  "schema_version": "1.0",
  "source": "web",
  "input_url": "https://...",
  "generated_at": "2026-07-16T12:00:00+00:00",
  "summary": {
    "score": 8.2,
    "issue_count": 3,
    "p0": 0,
    "p1": 2,
    "p2": 1
  },
  "sections": [
    {
      "id": "感知",
      "name": "感知",
      "url": "https://...",
      "title": "页面标题",
      "score": 8,
      "is_compliant": true,
      "screenshot": "screenshots/screenshot_1_awareness.png",
      "issues": [],
      "suggestions": [],
      "analysis_content": "简要分析"
    }
  ],
  "issues": [
    {
      "id": "web-感知-001",
      "section": "感知",
      "severity": "p1",
      "title": "问题标题",
      "area": "区域",
      "locate": ["定位文字"],
      "evidence": "客观依据",
      "standard": "Garrett: Surface Plane | Nielsen #8",
      "suggestion": "修改前：... -> 修改后：...",
      "screenshot": "screenshots/screenshot_1_awareness.png"
    }
  ],
  "model": {
    "provider": "gemini",
    "name": "gemini-3.5-flash",
    "fallback_chain": ["gemini:gemini-3.5-flash", "gemini:gemini-2.5-flash"],
    "config_path": "../shared/model_providers.json"
  }
}
```

Source values:

- `web`: full customer journey audit. `sections` are the seven journey stages.
- `mobile`: single mobile page audit. `sections` contains one item with `id: "mobile-page"`.

Severity values:

- `p0`: blocking or severe business-flow issue.
- `p1`: important usability, correctness, or transparency issue.
- `p2`: improvement suggestion.

## Web Intermediate Files

Web keeps stage intermediate files for debugging and review:

`../../output/web/<product_slug>/<run_id>/stages/<阶段>.json`

Each stage file is the raw model output plus normalized metadata:

- `stage`
- `url`
- `title`
- `screenshot_path`
- `score`
- `is_compliant`
- `issues`
- `suggestions`
- `analysis_content`
- `provider`
- `model`
- `model_fallback_chain`

## Crawl Capture Files

Web crawl capture:

`../../output/web/<product_slug>/<run_id>/_crawl.json`

Mobile capture:

`../../output/mobile/<page_slug>/<run_id>/_capture.json`

These files are evidence inputs, not the system integration contract. Integrate with `audit.json` by default.
