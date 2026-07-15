---
name: mobile-cloud-customer-journey
description: Audit Huawei Cloud mobile web pages for mobile UX quality, responsive layout, navigation, tap targets, sticky bars, menus, readability, screenshots, DOM evidence, and HTML reports. Use when Codex needs to inspect Huawei Cloud public pages in an iPhone-sized browser viewport and produce mobile-specific findings or reports.
---

# 华为云移动端页面体验审查

## 功能定位

使用这个 skill 对华为云公开页面做移动端体验走查。它不是完整七阶段客户旅程审查；完整产品旅程、登录态、下单/支付/续费/退订流程使用 `cloud-customer-journey`。

默认使用 Playwright 以 iPhone 视口打开目标 URL，采集首屏、滚动后、菜单展开和全页截图，并提取 DOM、可点击元素、CTA、菜单、横向溢出、字号、触控区域和点击反馈证据。

如需模型分析，使用 `scripts/analyze_mobile_audit.py`。它和网页版 skill 共用 `../shared/model_providers.json` 与 `../shared/ai_provider.py`，默认 fallback 顺序是 Gemini 3.5 -> Gemini 2.5。Gemini 全部失败时，脚本会停止并提示由当前 Codex agent 基于已采集 JSON 和截图继续分析。

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

`generate_mobile_html_report.py` 用于把人工整理后的 Markdown 报告转换为 HTML，并可嵌入截图：

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
- CTA 无反馈类问题优先引用 `tapActionAudit.issues`。
- 横向溢出、遮挡、字号和触控面积问题优先引用 DOM 中的尺寸、坐标、viewport 和截图证据。
- 严重度建议：`P1` 表示阻断或重要入口无效，`P2` 表示不阻断但影响效率、理解或可读性。

## 资源索引

- `scripts/mobile_page_audit.py`：移动端页面采集与交互检测。
- `scripts/analyze_mobile_audit.py`：移动端模型分析，复用共享 fallback 链。
- `scripts/generate_mobile_html_report.py`：Markdown 报告转自包含 HTML。
- `../shared/model_providers.json`：Gemini fallback 与 agent fallback 说明配置。
- `../shared/ai_provider.py`：共享模型调用与 fallback 逻辑。
