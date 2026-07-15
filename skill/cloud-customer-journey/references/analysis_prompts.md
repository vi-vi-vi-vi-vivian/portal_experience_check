# Analysis Prompts

Use these prompts with Gemini. Keep the stage name and page evidence in the prompt. Do not shorten the issue output schema.

## Full Screenshot Prompt

You are a Huawei Cloud product experience audit expert. Analyze this screenshot for the `{stage}` stage. Scan each visible region from top to bottom and identify concrete UX issues.

Check:

- Visual and layout: CTA salience, contrast, spacing, card hierarchy, disabled states, dense notices, component consistency.
- Wording and information: typos, ambiguous constraints, inconsistent terms, billing units, missing explanations.
- Interaction and flow: whether the expected next action is discoverable, whether operation feedback is clear, whether the flow reaches the correct next page.
- Billing and risk: price formula, billing period, renewal or auto-renewal behavior, refund or cancellation consequences.
- Cross-page consistency when relevant: product name, package names, status labels, and button wording.

Return Chinese JSON only:

```json
{
  "score": 1,
  "is_compliant": false,
  "issues": [
    {
      "title": "短标题",
      "area": "页面区域",
      "locate": ["页面上真实存在的定位文字"],
      "evidence": "来自截图的客观依据",
      "standard": "Nielsen #4",
      "severity": "p1",
      "suggestion": "修改前：... -> 修改后：..."
    }
  ],
  "analysis_content": "简要说明"
}
```

## Region Screenshot Prompt

Analyze this region screenshot for `{stage}`. Focus on small text, CTA state, pricing, package cards, warnings, FAQ copy, footer links, and visible interaction states.

Return the same JSON schema as the full screenshot prompt. If no issue is supported by observable evidence, return an empty `issues` array.

## DOM Analysis Prompt

You are reviewing DOM-derived evidence for a Huawei Cloud journey stage. Use `structured_html`, `buttons`, `links`, `price_info`, `visual_details`, and `element_rects`.

Check:

- Button `href` targets: purchase/open buttons must point to the correct purchase or activation flow, not an unrelated console page.
- Disabled or greyed controls: require an adjacent reason.
- Exact wording consistency across title, body, button, order fields, status labels, and package names.
- Computed visual evidence: font size, color, opacity, dimensions, x/y position, and nesting.
- Pricing transparency: units, period, formula, free/0-yuan confirmation, auto-renewal disclosure.
- Console reachability for `使用`: search result availability, service category path, recent visit and shortcut entries.

Return the same Chinese JSON schema. Every issue must cite exact DOM evidence.

## Merge Prompt

Merge visual and DOM findings for `{stage}`.

Rules:

- Prefer DOM evidence for exact text, href, disabled state, style, dimensions, and structured data.
- Prefer screenshots for visual salience, spacing, clipping, overlap, and reading order.
- Remove findings contradicted by the other source.
- Merge duplicates and keep the stronger evidence.
- Preserve `locate`, `evidence`, `standard`, `severity`, and `suggestion`.
- If `entry_not_found` or `target_product_not_found` is true, keep only the corresponding stage-level issue unless additional evidence clearly belongs to the target product.

## Cross-Stage Prompt

After all stages are analyzed, compare `crawl_result.json` and `stage_analysis.json`.

Find:

- Product name inconsistencies.
- Package or price presentation differences between order, renewal, and change pages.
- Incorrect product type names in payment or order reconciliation pages.
- Status label mismatches between renewal, change, unsubscribe, and usage pages.
- Different wording for the same operation, e.g. `续费` vs `续订`.

Append only evidence-backed issues to the relevant stage.
