---
name: cloud-customer-journey
description: Automate Huawei Cloud product customer journey UX audits from a product URL, covering awareness, order, payment, usage, renewal, change, and unsubscribe stages. Use when Codex needs to crawl Huawei Cloud pages, inspect logged-in console or billing flows, analyze screenshots and DOM data with a shared Gemini fallback chain and current-agent fallback workflow, annotate issues, and produce a self-contained HTML experience review report.
---

# 华为云客户旅程体验审查

## 一、功能定位

这个 skill 用于从一个华为云产品 URL 出发，自动审查完整客户旅程：

`感知 -> 下单 -> 支付 -> 使用 -> 续费 -> 变更 -> 退订`

当前实现以 Playwright 浏览器自动化抓取页面、截图和 DOM 数据，再用共享 Gemini 多模态 fallback 链分析截图与 DOM 证据，最后合并为自包含 HTML 报告。如果 Gemini 全部失败，脚本会停止并提示由当前 Codex agent 基于已采集 JSON 和截图继续分析。

适用场景：

- 审查华为云官网产品页到控制台、费用中心、订单中心的端到端体验。
- 检查登录态、购买入口、支付入口、控制台入口、续费/变更/退订入口是否可达。
- 基于截图和 DOM 证据输出问题清单、严重度、行业标准依据和修改建议。

当前实现以通用产品页为默认路径：从目标 URL 和页面线索提取产品关键词，优先通过官网 CTA、控制台搜索、费用中心入口和通用阶段 marker 探索旅程。`step3_crawl_journey.py` 保留少量已知产品 profile，用于兼容 ModelArts、TokenPlan 等历史验证产品的别名、控制台回退 URL 和阶段 marker；这些 profile 只在 URL 命中对应产品时启用，不作为其他产品的默认判断依据。

## 二、执行流程

默认完整执行：

```bash
python scripts/run_audit.py --url "<URL>" --project-root "$PWD" --site cn
```

`--site cn` 用于中国站账号，`--site intl` 用于国际站账号。完整流程会依次执行工具检查、登录态准备、七阶段抓取、逐阶段模型分析、分析合并和 HTML 报告生成。默认模型 fallback 链配置在 `../shared/model_providers.json`。

```bash
python scripts/run_audit.py --url "<URL>" --project-root "$PWD" --site cn \
  --model-config "../shared/model_providers.json"
```

默认审查产物会写入独立 run 目录，避免不同页面或多次执行互相覆盖：

```text
../../output/web/<product_slug>/<YYYYMMDD-HHMMSS>/
  audit.json
  report.html
  _crawl.json
  stages/<阶段>.json
  screenshots/
```

`audit.json` 是系统集成主产物，和 mobile skill 使用同一顶层 schema：`schema_version`、`source`、`input_url`、`generated_at`、`summary`、`sections`、`issues`、`model`。系统分发问题时优先读取顶层 `issues[]`；阶段视图读取 `sections[]`。Web 额外保留 `stages/<阶段>.json` 作为中间文件。

登录态、浏览器 profile 和手动单步调试输出默认也写入父级 `../../output/web/`，避免运行产物混入 skill 源码目录。可用 `--output-root` 或 `--run-id` 控制 run 目录，用 `--output` 指定最终 HTML 报告路径。

### 1. 工具与环境检查

```bash
python scripts/step1_check_tools.py
```

要求：

- Python 3.9+。
- 已安装 `playwright`、`requests`、`Pillow`。
- Gemini 分析需要环境变量 `GEMINI_API_KEY`。
- 默认模型链在 `../shared/model_providers.json`；可用 `AUDIT_MODEL_CONFIG` 或 `--model-config` 指向其他配置文件。

### 2. 登录态准备

```bash
python scripts/step2_login_handler.py --url "<URL>" --project-root "$PWD" --site cn
```

登录态默认输出到 `../../output/web/_runtime/auth_cookie.json`。脚本会先校验已有 storage state：文件存在、非空、包含 `huaweicloud.com` cookie，并能访问当前站点的 www/console/account 验证 URL 且不跳回 `auth.huaweicloud.com` 登录页。

如果 cookie 无效，脚本会打开带界面的 Chromium 登录页，加载 `scripts/anti_detection.js`，等待人工完成登录。默认不拦截 `accountguard.js`，因为拦截可能导致登录页空白；只有定位风控脚本问题时才使用 `--block-risk-script`。

常用模式：

```bash
# 保持登录浏览器打开，并定期刷新 ../../output/web/_runtime/auth_cookie.json
python scripts/step2_login_handler.py --url "<URL>" --project-root "$PWD" --site cn --wait-seconds 180 --keep-open

# 尝试使用环境变量密码登录；遇到 CAPTCHA/MFA/风控仍需人工处理
HUAWEICLOUD_USERNAME="<账号>" HUAWEICLOUD_PASSWORD="<密码>" \
python scripts/step2_login_handler.py --url "<URL>" --project-root "$PWD" --site cn --force-login
```

约束：

- 不要把账号密码写进脚本或 skill 文件。
- `--keep-open` 运行时不要让 step3 使用 `--use-login-profile`，因为持久化 profile 会被登录浏览器锁住；此时 step3 正常导入 `../../output/web/_runtime/auth_cookie.json`。
- 脚本使用 `../../output/web/_runtime/huaweicloud_login_profile`，不能读取用户已打开的 Safari/Chrome 个人浏览器登录态。

### 3. 七阶段抓取

```bash
python scripts/step3_crawl_journey.py --url "<URL>" --project-root "$PWD" --site cn --all
```

可只抓单阶段：

```bash
python scripts/step3_crawl_journey.py --url "<URL>" --project-root "$PWD" --site cn --stage "感知"
```

如果还没有登录态：

```bash
python scripts/step3_crawl_journey.py --url "<URL>" --project-root "$PWD" --site cn --all --ensure-login --login-wait-seconds 180
```

如果 `../../output/web/_runtime/auth_cookie.json` 存在但控制台/费用中心仍跳登录，可改用持久化 profile：

```bash
python scripts/step3_crawl_journey.py --url "<URL>" --project-root "$PWD" --site cn --all --use-login-profile
```

抓取输出：

- 完整流程默认写入 `../../output/web/<product_slug>/<run_id>/_crawl.json`：所有阶段页面数据。
- 完整流程默认写入 `../../output/web/<product_slug>/<run_id>/screenshots/screenshot_{n}_{stage}.png`：全页截图。
- 完整流程默认写入 `../../output/web/<product_slug>/<run_id>/screenshots/region_{n}_{stage}_top.png`：当前视口截图。
- 手动单独调用 `step3_crawl_journey.py` 且不传 `--output`/`--screenshot-dir` 时，默认写入 `../../output/web/manual/_crawl.json` 与 `../../output/web/manual/screenshots/`。

当 `--site cn` 且输入 URL 为 `/intl/en-us/product/` 路径时，脚本会把 URL 规范化到中国站 `/product/` 路径再抓取。

## 三、探索阶段细则

### 感知阶段

入口是用户输入的产品 URL。

执行策略：

- 直接打开目标产品页，等待页面文本稳定。
- 截取全页截图和视口截图。
- 提取正文、结构化 HTML、按钮、链接、价格、样式和元素位置。
- 如果页面跳到登录页、空白页或无可见文本/按钮/链接，标记 `entry_not_found: true`。

重点检查：

- 首屏产品名称、卖点、购买/试用 CTA 是否清晰。
- 定价、套餐、计费单位、使用限制、FAQ 和 Footer 是否一致。
- 官网搜索和购买入口是否可达；当前脚本不会主动执行官网搜索补采，发现搜索可达性问题时需要基于已有 DOM/链接证据或后续人工扩展。

### 下单阶段

入口从感知页开始。

点击模式按优先级执行：

- 优先扫描 `a[href]`、`button`、`[role=button]` 中匹配购买文案的元素，并直接跳转有效 href。
- 再用 role/name 和文本定位点击按钮或链接。
- 最后用 JS 遍历可见 `a/button/[role=button]/input`，按文案模糊匹配点击。

默认 CTA 文案包括：

`立即订阅`、`立即购买`、`立即选购`、`去购买`、`免费试用`、`购买`、`Buy`、`Purchase`、`Subscribe`、`Get Started`、`Free Trial`。

阶段达成判断：

- 不能仍停留在感知页。
- 默认判断是否进入订单配置、购买准备、订阅配置或开通页面，URL/正文需出现购买、订阅、配置、协议、价格、订单等通用线索。
- 对已知产品 profile，可追加产品专属 URL marker 或文案 marker，避免历史产品的控制台路径被误判为未达；这些 marker 不影响其他产品。
- 未到达预期目标时标记 `stage_goal_not_reached: true` 和 `entry_not_found: true`，不要把感知页误当下单页分析。

### 支付阶段

入口通常继承下单阶段所在页面。

执行策略：

- 勾选协议类 checkbox：文本含 `协议`、`条款`、`声明`、`同意`、`阅读`、`服务`、`agreement`、`terms`、`agree` 的未选 checkbox 会被点击。
- 进入下单、支付、续费等页面后，会优先处理遮挡页面的可关闭弹窗：如果弹窗内有“服务声明”“升级公告”“不再提示”“我已阅读”等 checkbox 或关闭按钮，先勾选/关闭再继续截图或点击。
- 尝试点击 `立即购买`、`提交订单`、`确认订单`、`下一步`、`Pay`、`Submit Order`、`Confirm Order`、`Checkout`。
- 最多重试 3 次。
- 如果没有进入支付相关页面，不再回退到未支付订单中心；保留当前购买/订阅页并标记支付阶段未达，避免把错误页面当支付页。

阶段达成判断：

- 中国站通常要求 URL 或正文出现 `servicePay`、收银台、支付确认、应付金额、支付方式等支付线索。
- 未到达支付页时记录阶段级入口问题，不编造支付页 UI 问题。

### 使用阶段

入口是控制台首页。

执行策略：

- 访问当前站点 console URL。
- 从目标 URL 提取产品关键词；如果命中已知产品 profile，再追加 profile 中声明的产品别名。
- 在控制台搜索框尝试输入关键词并按 Enter。
- 如果搜索结果中出现目标产品关键词或 profile 别名，则点击进入。
- 搜索失败时回退到 profile 声明的产品控制台 URL；没有 profile 回退 URL 时，保留在当前站点 console URL 并按阶段达成规则判断是否覆盖。
- 进入后会勾选页面上可见且未禁用的 checkbox，这用于展开或选择部分控制台状态，但分析时必须检查该行为是否影响页面语义。

重点检查：

- 产品是否能从主控制台搜索直达。
- 产品是否出现在服务分类、最近访问或快捷入口中。
- 产品控制台是否提供订阅管理、资源池、计费或操作入口。

### 续费阶段

入口优先是账号/费用中心。

执行策略：

- 访问当前站点 account URL。
- 在费用中心页面查找 `续费`、`批量续费`、`自动续费`、`Renew`、`Renewal` 等链接或按钮。
- 优先点击 account 域名下的匹配链接。
- 找不到时尝试直接点击页面上的续费 CTA。

阶段达成判断：

- URL 包含 `renewal` 或正文出现 `续费管理` 等续费线索才算覆盖。
- 未找到目标续费入口时记录 `entry_not_found`，不要把账号总览页当续费页。

### 变更阶段

入口优先从控制台查找费用中心/账号中心相关链接，失败后回退产品控制台。

执行策略：

- 从 console 页扫描 `account.huaweicloud.com` 链接，匹配 `变更`、`规格变更`、`升级`、`降级`、`Change`、`Modify`、`Upgrade`、`Downgrade`。
- 如果没有找到 account 链接，进入产品控制台 URL，再尝试点击变更类 CTA。

阶段达成判断：

- 不能停留在 account 总览页。
- URL 或正文需出现 `change`、`modify`、`resize`、`upgrade`、`downgrade`、`规格变更`、`变更套餐` 等通用变更线索；产品 profile 可追加专属 marker。

### 退订阶段

入口策略与变更阶段类似。

执行策略：

- 从 console 页扫描 account 域名链接，匹配 `退订`、`退费`、`释放`、`取消订阅`、`Unsubscribe`、`Refund`、`Release`、`Cancel`。
- 找不到时回退产品控制台，再尝试点击退订类 CTA。
- 如果点击后出现确认弹窗，也可以视为有效退订入口，分析时必须记录弹窗文案、风险提示和二次确认是否充分。

阶段达成判断：

- 不能停留在 account 总览页。
- URL 或正文需出现 `unsubscribe`、`refund`、`cancel`、`云服务退订`、`退订资源`、`退费` 等线索。

## 四、采集数据契约

完整流程默认 `../../output/web/<product_slug>/<run_id>/_crawl.json` 顶层字段：

- `input_url`：实际抓取 URL，可能已按 `--site cn` 转换。
- `original_input_url`：用户原始输入 URL。
- `crawl_time`：抓取时间。
- `stages_covered`：未被标记为入口缺失或登录阻断的阶段。
- `stages_missing`：未覆盖阶段。
- `auth_state_path` 与 `auth_state_loaded`：登录态来源和是否加载。
- `target_product_keywords`：由目标 URL 和可选产品 profile 推导出的产品关键词与别名，用于控制台搜索和阶段达成校验。
- `pages`：各阶段页面记录。

页面记录关键字段：

- `stage`、`url`、`title`：阶段和页面身份。
- `screenshot_path`、`region_screenshots`：截图证据。
- `body_text`：可见正文，最多保留约 24000 字。
- `structured_html`：body 外层 HTML，最多约 80000 字，包含真实 DOM 结构但未精简为语义树。
- `buttons`：按钮/链接型元素，含 `text`、`href`、`isDisabled` 和位置尺寸。
- `links`：普通链接，排除 `javascript:`。
- `price_info`：从正文正则提取的价格线索。
- `visual_details`：可交互、价格、卡片、标题等元素的计算样式。
- `element_rects`：按钮、链接、标题、输入框、提示、卡片等元素的位置矩形。
- `entry_not_found`、`login_required`、`blank_page`、`stage_goal_not_reached`、`blocked_reason`：阻断和未覆盖原因。

完整字段约束见 `references/data_contract.md`。

## 五、模型分析规则

阶段分析必须遵循完整步骤4规范，详见 `references/stage4_agent_analysis_full.md`。该文件已完整纳入 AI Agent 逐阶段分析的 4a-4g 全量规则，包括视觉截图分析、DOM 数据分析、交叉验证合并、DOM 标注、使用阶段控制台可达性、感知阶段交互探索、跨阶段一致性检查，以及各类提示词、降级策略、输出格式和证据约束。

`scripts/step4_analyze_stage.py` 在构造模型 prompt 时会读取 `references/stage4_agent_analysis_full.md` 并完整拼入 `<FULL_STAGE4_AGENT_ANALYSIS_RULES>`，因此不要把该引用删减为摘要。后续调整步骤4时，应优先更新该完整参考文件，再同步必要的脚本逻辑。

逐阶段分析：

```bash
python scripts/step4_analyze_stage.py --stage "<阶段>" --crawl-result "../../output/web/manual/_crawl.json" --project-root "$PWD"
```

完整流程由 `run_audit.py` 自动传入当前 run 的 `_crawl.json`，并输出 `stages/<阶段>.json`。上面的命令是手动单步调试的兼容写法。

模型与重试：

- 默认模型链：`gemini-3.5-flash` -> `gemini-2.5-flash`，以 `../shared/model_providers.json` 为准。
- 每个模型默认重试 2 次。
- 同一模型重试默认等待 30 秒，模型切换默认等待 45 秒。
- 当某个模型返回 HTTP 429（额度或频控）且 fallback 链里还有下一个模型时，会立即切换到下一个，不再耗尽当前模型的所有重试次数。
- 可用 `--model-config`、`--retries-per-model`、`--retry-sleep-seconds`、`--model-switch-sleep-seconds`、`--timeout` 调整。
- 如果所有配置的 Gemini 模型失败，脚本会停止并提示 agent fallback；此时在当前 Codex 会话里基于已采集 JSON 和截图继续分析，不要用本地脚本猜测替代模型分析。

分析输入：

- 全页截图和最多 6 张 region 截图。
- DOM 摘要：正文、结构化 HTML、按钮、链接、价格、样式、元素位置、入口阻断标记。
- 完整步骤4分析规范：`references/stage4_agent_analysis_full.md` 的 4a-4g 全量内容。

分析输出必须是 JSON，且每个问题至少包含：

- `title`：短标题。
- `area`：页面区域。
- `locate`：页面上真实存在的定位文字数组。
- `evidence`：客观证据。
- `standard`：行业标准依据。
- `severity`：`p0`、`p1` 或 `p2`。
- `suggestion`：包含“修改前 -> 修改后”的可执行建议。

## 六、问题质量规则

必须遵守：

- `locate` 必须来自实际 UI 文本、按钮文案、价格、状态标签、字段名、提示语或链接文字，不能写分析结论。
- 多个定位词时，第一个应是最精确、最少重复的定位词。
- `evidence` 必须是可观测事实，例如 href、disabled、font-size、颜色、opacity、宽高、x/y 位置、价格、时间区间、页面实际文案或截图中的具体布局事实。
- 涉及时间或数值的结论必须给出计算过程。例如不要只写“有效期过长”，要写“订单创建时间 2026/06/21，支付截止 2026/06/28，有效期 7 天”。
- 不保留“按钮不明显”“信息不清楚”这类无证据判断，除非补充字号、颜色、对比对象、位置或缺失字段等依据。
- 建议必须可执行，包含具体修改前后对比。

标准引用建议：

- 视觉层级、对比、布局、密度：`Garrett: Surface Plane | Nielsen #8`。
- 流程、反馈、入口可发现性、效率：`Garrett: Skeleton Plane | Nielsen #1 | Nielsen #3 | Nielsen #6 | Nielsen #7`。
- 计费规则、风险披露、帮助、错误预防：`Garrett: Structure Plane | Nielsen #5 | Nielsen #10`。
- 文案、术语、产品名称一致性：`Nielsen #2 | Nielsen #4`。
- 自描述性、可学习性、可控性：`ISO 9241-110`。
- 目标导向、弹窗和页面跳转的交互模式判断：`Cooper: Goal-Directed Design`。

严重度定义：

- `p0`：阻断业务流程、入口缺失、错误产品/订单/状态、关键风险未披露。
- `p1`：重要可用性、准确性、计费透明度、状态同步或一致性问题。
- `p2`：改进建议，不阻断主流程。

## 七、合并与交叉验证

合并分析：

```bash
python scripts/step4_merge_analysis.py --project-root "$PWD"
```

完整流程下，合并目标是把当前 run 的 `stages/<阶段>.json` 汇总为顶层 `audit.json`。手动单步调用且不传输出参数时，默认使用 `../../output/web/manual/stages/<阶段>.json` 和 `../../output/web/manual/audit.json`。

交叉验证规则：

- 如果阶段页面有 `entry_not_found: true`，只保留一个阶段级入口不可达问题，评分应偏低，不分析不存在的页面 UI。
- 截图和 DOM 冲突时，精确文本、href、disabled、样式、尺寸、字段值以 DOM 为准；视觉显著性、遮挡、阅读顺序、空间拥挤以截图为准。
- 视觉或模型声称某元素缺失，但 DOM 中能找到且可见，应删除或降级该问题。
- 价格、日期、时长、状态类问题必须能从 DOM 或截图证据复核。
- 同一问题在视觉和 DOM 中重复出现时合并为一条，保留更强证据。

跨阶段重点：

- 产品名称在官网、购买页、支付页、控制台、费用中心是否一致。
- 下单、续费、变更页面的套餐名称、价格单位、资源量和描述是否一致。
- 支付/订单中心的产品类型和服务提供方是否准确。
- 使用、续费、变更、退订页面的状态标签是否同步。
- 相同操作是否出现不同话术，例如 `续费` 与 `续订` 混用。

## 八、报告生成

```bash
python scripts/step5_generate_report.py --project-root "$PWD" --analysis "<RUN_DIR>/audit.json" --crawl-result "<RUN_DIR>/_crawl.json" --output "<RUN_DIR>/report.html"
```

报告输入：

- 完整流程默认读取 `../../output/web/<product_slug>/<run_id>/_crawl.json`
- 完整流程默认读取 `../../output/web/<product_slug>/<run_id>/audit.json`
- 完整流程默认读取 `../../output/web/<product_slug>/<run_id>/screenshots/` 下的截图
- 手动单步调用报告脚本时，仍可显式传入 `--analysis`、`--crawl-result` 和 `--output`。

当前报告脚本会生成自包含 HTML，并尽量嵌入阶段截图和问题列表。当前目录没有 `step4_annotate.py`，因此不要把“红框编号标注截图”当作必然输出能力；如后续恢复标注脚本，再补充 `annotated_screenshot` 或截图映射字段。

报告结构：

- 顶部展示客户旅程总览，逐阶段显示问题总数、阻断/重要/建议数量。
- 全局问题清单按严重级别从高到低排序。
- 每个阶段的问题以表格呈现，列为级别、问题描述、优化建议。

## 九、当前限制与扩展点

- 当前抓取脚本使用通用发现策略，并通过 `PRODUCT_PROFILES` 保存少量已知产品兼容配置。新增产品如果存在特殊控制台路径、别名或阶段 marker，应扩展 profile，而不是把专属判断写入通用逻辑。
- 当前只保存全页截图和一个视口 region 截图，没有根旧版设计中的上下半页/重叠分区截图策略。
- 当前分析通过共享 Gemini fallback 完成；Gemini 全部失败后由当前 Codex agent 接管分析。不再使用根旧版设计中的 `codespec ai vl-model`、OpenAI API fallback 或 Qwen 降级链。
- 当前没有 DOM 红框标注脚本，报告使用原始截图和分析问题。
- `target_product_not_found` 在数据契约中保留，但当前 crawler 没有完整的目标产品匹配补采逻辑；如果续费/变更/退订页面进入了费用中心但不是目标产品，应优先扩展脚本而不是让模型猜测。

## 十、资源索引

- `scripts/run_audit.py`：完整流程入口。
- `scripts/step1_check_tools.py`：环境与模型 provider 配置检查。
- `scripts/step2_login_handler.py`：登录态捕获和刷新。
- `scripts/step3_crawl_journey.py`：七阶段抓取、截图、DOM 提取和阶段达成判断。
- `scripts/step4_analyze_stage.py`：单阶段多模态模型分析。
- `scripts/step4_merge_analysis.py`：合并单阶段分析。
- `scripts/step5_generate_report.py`：生成 HTML 报告。
- `../shared/model_providers.json`：Gemini fallback 与 agent fallback 说明配置。
- `../shared/ai_provider.py`：共享模型调用与 fallback 逻辑。
- `references/analysis_prompts.md`：模型 prompt 摘要。
- `references/stage4_agent_analysis_full.md`：步骤4 AI Agent 逐阶段分析全量规范，实际阶段分析 prompt 会完整拼入。
- `references/data_contract.md`：JSON 数据契约。
