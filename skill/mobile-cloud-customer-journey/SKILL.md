---
name: mobile-cloud-customer-journey
description: Audit Huawei Cloud mobile web pages for mobile UX quality, responsive layout, navigation, tap targets, sticky bars, menus, readability, screenshots, DOM evidence, and HTML reports. Use when Codex needs to inspect Huawei Cloud public pages in an iPhone-sized browser viewport and produce mobile-specific findings or reports.
---

# 华为云移动端页面体验审查

## 功能定位

使用这个 skill 对华为云公开页面做移动端体验走查。它不是完整七阶段客户旅程审查；完整产品旅程、登录态、下单/支付/续费/退订流程使用 `cloud-customer-journey`。

默认使用 Playwright 以 iPhone 视口打开目标 URL，采集首屏、滚动后、菜单展开和全页截图，并提取 DOM、可点击元素、CTA、菜单、横向溢出、字号、触控区域和点击反馈证据。全页截图用于留档和模型/人工取证，默认不要在 HTML 报告正文展示完整长图。

如需模型分析，使用 `scripts/analyze_mobile_audit.py`。它和网页版 skill 共用 `../shared/model_providers.json` 与 `../shared/ai_provider.py`，默认 fallback 顺序是 Gemini 3.5 -> Gemini 2.5。Gemini 全部失败时，脚本会停止并提示由当前 Codex agent 基于已采集 JSON 和截图继续分析。此时仍必须产出与 web skill 同顶层 schema 的 `audit.json`，不要只生成 Markdown/HTML。

## 默认输出

产物统一写到 skill 父目录，和网页版检测分开：

```text
../../output/mobile/<page_slug>/<YYYYMMDD-HHMMSS>/
  _capture.json
  audit.json
  report.html
  screenshots/<page_slug>_top.png
  screenshots/<page_slug>_scroll.png
  screenshots/<page_slug>_menu.png
  screenshots/<page_slug>_full.png
```

`audit.json` 是系统集成主产物，和 web skill 使用同一顶层 schema：`schema_version`、`source`、`input_url`、`generated_at`、`summary`、`sections`、`issues`、`model`。Mobile 的 `sections[]` 默认只有一个 `mobile-page` section。无论模型分析成功还是 agent fallback 人工整理，都必须写入 `audit.json`。

如需兼容旧流程，可显式传 `--output-dir`，此时 JSON 与截图会写入同一个目录。

## 页面采集

```bash
python scripts/mobile_page_audit.py --url "<URL>"
```

常用参数：

- `--output-root ../../output/mobile`：移动端 run 根目录。
- `--run-id <id>`：指定本次 run 的目录名，默认当前时间。
- `--output-dir <dir>`：兼容旧版扁平输出，优先级高于 `--output-root`。
- `--headed`：打开有界面浏览器调试。

采集重点：

- 首屏是否能识别页面主题、主 CTA 和关键信息。
- 页面是否存在横向溢出、文字遮挡、固定栏遮挡或响应式断裂。
- 菜单是否可打开、关闭、滚动，层级和入口是否清晰。
- 重要 CTA、详情链接、卡片点击是否有可见反馈。
- 可点击区域是否足够大，是否存在看起来可点但无反馈的元素。

## 模型分析

```bash
python scripts/analyze_mobile_audit.py \
  --input "../../output/mobile/<page_slug>/<run_id>/_capture.json"
```

Gemini 分析需要环境变量 `GEMINI_API_KEY`。可用 `AUDIT_MODEL_CONFIG` 或 `--model-config` 指向其他配置文件。不要在配置文件里放 OpenAI API key；当前设计不通过本地脚本调用 OpenAI API。

## 报告生成

`generate_mobile_html_report.py` 用于把人工整理后的 Markdown 报告转换为 HTML，并可嵌入截图。Markdown 正文应沿用旧版报告结构：总体结论、检查矩阵、主要问题、通过项与不适用项、建议修复优先级；涉及点击/触控/菜单的问题优先用表格展示元素、实测结果和证据摘要。默认只展示首屏、滚动后、菜单展开截图，不展示完整长截图；只有明确需要时才加 `--include-full-screenshot`：

```bash
python scripts/generate_mobile_html_report.py \
  --input "../../output/mobile/<page_slug>/<run_id>/report.md" \
  --output "../../output/mobile/<page_slug>/<run_id>/report.html" \
  --screenshot-dir "screenshots" \
  --image-prefix "<page_slug>" \
  --embed-images
```

`--screenshot-dir` 相对 HTML 输出目录解析；也可以传绝对路径。不要再依赖 skill 内的 `temp/mobile_audit`。

## 问题记录规则

- 每个问题必须能回指到截图、DOM 字段、按钮文案、元素尺寸、URL 或点击结果。
- 不写“移动端不友好”这类泛化结论；要写清楚具体区域、可观测事实和影响。
- CTA 无反馈类问题优先引用 `tapActionAudit.issues`，并必须在最终报告中展示“点击后 URL/弹窗/滚动/DOM 是否变化”的证据；不要因为模型摘要遗漏而丢弃。
- 不要轻易跳过点击回放。仅在采集卡死调试时使用 `--skip-tap-actions`，正式报告需说明该限制；常规检测可用 `--tap-max-candidates` 控制耗时。
- 横向溢出、遮挡、字号和触控面积问题优先引用 DOM 中的尺寸、坐标、viewport 和截图证据。
- 严重度建议：`P1` 表示阻断或重要入口无效，`P2` 表示不阻断但影响效率、理解或可读性。

## 后置结果质量复核

报告生成后必须对 `audit.json` 做一次后置质量门禁。复核不是重新抓页面，而是基于当前 run 的 `_capture.json`、截图和 `audit.json`，检查模型或 agent fallback 输出的问题是否成立、分类是否准确、时效判断是否使用当前日期。

复核范围：

- 顶层 `issues[]`。
- `sections[].issues[]`。
- `summary.issue_count`、`summary.p0/p1/p2` 与清理后的顶层 `issues[]` 是否一致。

逐条 issue 复核规则：

- 问题必须能被 `_capture.json` 中的页面 URL、标题、可见文本、DOM 结构、可点击元素、CTA、菜单、横向溢出、字号、触控区域、点击反馈或截图证据支撑。
- `locate` 必须来自页面真实可见文案、按钮文案、字段名、提示语、链接文字或可定位元素描述；不能写分析结论。
- 当前日期和年份必须以执行时环境为准。例如当前年份为 2026 时，不得保留“`©2026 Huaweicloud.com` 是未来年份”或“当前年份为 2024”这类过时误报。
- 如果采集页面是登录页、404、空白页或目标内容未加载，只保留页面级入口/内容不可达问题，不分析不存在页面上的细节 UI。

全量 `type` 复核规则：

- `typo`：仅用于真实错别字、漏字、多字、词语误写，必须给出明确的“修改前 -> 修改后”。按钮尺寸、触控热区、版权年份、格式规范、布局问题不能归为 `typo`。
- `copy_format`：标点、空格、大小写、命名格式、FAQ 句式、文案格式规范不统一。
- `layout`：移动端视觉层级、字号、颜色、对比、遮挡、拥挤、横向溢出、固定栏遮挡、触控热区尺寸、响应式断裂。
- `interaction`：按钮状态、点击反馈、控件行为、触屏可操作性、菜单打开/关闭/滚动问题。
- `link_target`：链接错误、404、跳转目标不符、入口不可达、路由问题。
- `billing_risk`：支付、计费、价格、续费、退订、退款、订单、权益、风险披露问题。
- `content_clarity`：信息缺失、说明不清、术语不一致、帮助解释不足、用户难以理解但不属于格式规范的问题。
- `unknown`：只有证据不足以归入以上类型时才保留；复核时应尽量归入更具体类型。

严重度复核规则：

- `p0`：流程阻断、入口不可达、错误页面/状态、关键支付/退订/计费风险缺失。
- `p1`：影响主流程理解、决策、效率或重要一致性，但仍可继续操作。
- `p2`：不阻断流程的文案、格式、视觉细节或辅助体验优化。

清理与同步要求：

- 明显误报必须删除。
- 问题成立但 `type` 错误时必须改为正确类型。
- 问题成立但严重度过高或过低时必须调整 `severity`。
- 漏检且证据明确的问题可以补充，但必须满足同样的 `locate`、`evidence`、`standard`、`suggestion` 质量要求。
- 修改后必须同步顶层 `issues[]` 和 `sections[].issues[]` 中的副本，并重新计算 `summary`。
- 复核再次执行时应无新增变更，才视为通过质量门禁。

## 资源索引

- `scripts/mobile_page_audit.py`：移动端页面采集与交互检测。
- `scripts/analyze_mobile_audit.py`：移动端模型分析，复用共享 fallback 链。
- `scripts/generate_mobile_html_report.py`：Markdown 报告转自包含 HTML。
- `../shared/model_providers.json`：Gemini fallback 与 agent fallback 说明配置。
- `../shared/ai_provider.py`：共享模型调用与 fallback 逻辑。
