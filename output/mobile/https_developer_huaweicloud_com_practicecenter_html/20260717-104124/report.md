# 华为云实践中心移动端体验走查报告

目标页面：https://developer.huaweicloud.com/practicecenter.html
生成时间：2026-07-17T02:47:45.203676+00:00

## 总体结论

移动端综合评分：3 / 10。共发现 4 个问题，其中 P1 1 个，P2 3 个。

华为云开发者实践中心移动端页面存在严重的可用性阻碍。核心功能（点击实践卡片查看详情）因前端脚本加载及安全策略配置错误完全失效，导致用户无法在移动端开展实践。此外，侧边栏菜单排版严重变形，部分容器存在横向溢出，且按钮触控热区普遍偏小，整体移动端适配质量亟待提升。

## 检查矩阵

| 检查维度 | 检查结果 | 关键证据 | 风险判断 |
| --- | --- | --- | --- |
| 视口与页面尺寸 | 已采集 iPhone 级视口 | viewport {"width": 390, "height": 844, "devicePixelRatio": 3}；scroll {"documentElementScrollWidth": 390, "bodyScrollWidth": 390, "clientWidth": 390, "scrollHeight": 2414} | 存在横向溢出 |
| 首屏与主 CTA | 已采集首屏截图 | 首屏截图：`../../output/mobile/https_developer_huaweicloud_com_practicecenter_html/20260717-104124/screenshots/https_developer_hua…`；滚动后 CTA 1 个 | CTA 有点击问题 |
| 点击反馈 | 测试 12 / 候选 18 | 无反馈问题 11 个；有效点击示例含 `立即了解` | P1：多个详情卡片无响应 |
| 菜单导航 | 可展开 | 覆盖层 16 个；关闭目标 1 个 | 菜单/侧栏布局需优化 |
| 触控热区 | 小尺寸目标 38 个 | 典型小目标见下方 DOM 风险表 | 存在触控效率风险 |
| 文本与布局 | 文本风险 6 个 | overflow/textRisk 数据见下方表格 | 存在可读性或布局变形 |

## 点击回放详情

| 序号 | 元素/文案 | 点击前 URL | 点击后 URL/弹窗 | 结果 | 证据摘要 |
| --- | --- | --- | --- | --- | --- |
| 1 | 立即了解 | https://developer.huaweicloud.com/practicecenter.html | https://auth.huaweicloud.com/authui/login.html?service=https%3A%2F%2Fdevstation.connect.huaweicloud.com%2Fhands-on%2F | effective | hitInsideTarget=True; mutations=3; scrollChanged=0; bodyLengthDelta=0; cause=None |
| 2 | Agentic DevOps Hands-On最佳实践 基于华为云码道（CodeArts）代码智能体与原生CCE能力，从代码生成到部署优化，践行规范驱动开发（SDD） 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=0; scrollChanged=0; bodyLengthDelta=0; cause=console-error-after-tap |
| 3 | 华为云VPC从入门到精通：手动创建与Terraform一键部署Hands-On最佳实践 从可视化到自动化：通过 Console、 Terraform等多种方式，实现华为云 VPC 创建 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=1; scrollChanged=0; bodyLengthDelta=0; cause=console-error-after-tap |
| 4 | OpenClaw开发者最佳实践指南 OpenClaw 使用与配置的最佳实践，提升OpenClaw的安全能力以及扩展技能 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=4; scrollChanged=0; bodyLengthDelta=5; cause=console-error-after-tap |
| 5 | 查看更多 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=4; scrollChanged=0; bodyLengthDelta=5; cause=href-present-but-no-navigation,console-error-after-tap |
| 6 | 立即了解 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=0; scrollChanged=0; bodyLengthDelta=0; cause=console-error-after-tap |
| 7 | Agentic DevOps Hands-On最佳实践 基于华为云码道（CodeArts）代码智能体与原生CCE能力，从代码生成到部署优化，践行规范驱动开发（SDD） 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=0; scrollChanged=0; bodyLengthDelta=0; cause=console-error-after-tap |
| 8 | 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=5; scrollChanged=0; bodyLengthDelta=0; cause=object-or-overlay-may-intercept-tap,console-error-after-tap |
| 9 | 华为云VPC从入门到精通：手动创建与Terraform一键部署Hands-On最佳实践 从可视化到自动化：通过 Console、 Terraform等多种方式，实现华为云 VPC 创建 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=1; scrollChanged=0; bodyLengthDelta=0; cause=console-error-after-tap |
| 10 | 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=4; scrollChanged=0; bodyLengthDelta=5; cause=object-or-overlay-may-intercept-tap,console-error-after-tap |
| 11 | OpenClaw开发者最佳实践指南 OpenClaw 使用与配置的最佳实践，提升OpenClaw的安全能力以及扩展技能 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=4; scrollChanged=0; bodyLengthDelta=5; cause=console-error-after-tap |
| 12 | 查看详情 | https://developer.huaweicloud.com/practicecenter.html | https://developer.huaweicloud.com/practicecenter.html | no-visible-effect | hitInsideTarget=True; mutations=4; scrollChanged=0; bodyLengthDelta=5; cause=object-or-overlay-may-intercept-tap,console-error-after-tap |

## DOM 与布局风险详情

### 横向溢出 / 容器风险

| 元素路径 | 文案 | left/right/width | 样式/类别 |
| --- | --- | --- | --- |
| div.header-container > div.header-wrapper > div.header-user-detail.slide-panel > div.user-info > img.user-avatar |  | left=-4, right=52, width=56 | user-avatar |

### 文本换行 / 可读性风险

| 元素路径 | 文案摘要 | client/scroll | CSS 线索 |
| --- | --- | --- | --- |
| div.loaded.mb > div.header-container > div.header-wrapper > div.header-user-detail.slide-panel > ul.my-menu | 个人主页 我的开发者 我的博客 我的论坛 我的圈子 我的直播 我的活动 我的关注 我的开发者学堂 我的课程 我的认证 我的实验 我的收藏 我的Programs 我的支持 我的技术支持 我的云声建议 | client=48x536, scroll=48x763 | wordBreak=normal; overflowWrap=normal; height=536px |
| div#section-1 > div.pep-scenario-experience > div.por-section > div.por-container > div.por-section-body | Agentic DevOps Hands-On最佳实践 基于华为云码道（CodeArts）代码智能体与原生CCE能力，从代码生成到部署优化，践行规范驱动开发（SDD） 查看详情 华为云VPC从入门到精通：手动创建与Terraform一键部署Hands-On最佳实践 从可视化到自动化：通过 Console、 Terraf | client=342x545, scroll=346x545 | wordBreak=normal; overflowWrap=normal; height=545px |
| div#section-3 > div.pep-common-card-v2 > div.por-section.showMb > div.por-container > div.por-section-body | 华为云码道×仓颉实战：零基础开发你的专属音乐编辑器 本案例基于华为云码道（CodeArts）代码智能体与开源仓颉 Skills，设计实现一个有趣且实用的乐谱“编程”语言，在码道上用 AI + Cangjie 开发这个乐谱语言的编译器，它可以将相关乐谱编译为可播放的 MIDI 文件。 AssetMgmt固定资产管理系统（ | client=342x1026, scroll=346x1026 | wordBreak=normal; overflowWrap=normal; height=1026px |
| div.pep-common-card-v2 > div.por-section.showMb > div.por-container > div.por-section-body > div.por-tab-container | 华为云码道×仓颉实战：零基础开发你的专属音乐编辑器 本案例基于华为云码道（CodeArts）代码智能体与开源仓颉 Skills，设计实现一个有趣且实用的乐谱“编程”语言，在码道上用 AI + Cangjie 开发这个乐谱语言的编译器，它可以将相关乐谱编译为可播放的 MIDI 文件。 AssetMgmt固定资产管理系统（ | client=342x1026, scroll=346x1026 | wordBreak=normal; overflowWrap=normal; height=1026px |
| div.por-section.showMb > div.por-container > div.por-section-body > div.por-tab-container > div.por-tab-wrapper | 华为云码道×仓颉实战：零基础开发你的专属音乐编辑器 本案例基于华为云码道（CodeArts）代码智能体与开源仓颉 Skills，设计实现一个有趣且实用的乐谱“编程”语言，在码道上用 AI + Cangjie 开发这个乐谱语言的编译器，它可以将相关乐谱编译为可播放的 MIDI 文件。 AssetMgmt固定资产管理系统（ | client=342x1026, scroll=346x1026 | wordBreak=normal; overflowWrap=normal; height=1026px |
| div.por-container > div.por-section-body > div.por-tab-container > div.por-tab-wrapper > div.por-tab-content.active | 华为云码道×仓颉实战：零基础开发你的专属音乐编辑器 本案例基于华为云码道（CodeArts）代码智能体与开源仓颉 Skills，设计实现一个有趣且实用的乐谱“编程”语言，在码道上用 AI + Cangjie 开发这个乐谱语言的编译器，它可以将相关乐谱编译为可播放的 MIDI 文件。 AssetMgmt固定资产管理系统（ | client=342x1026, scroll=346x1026 | wordBreak=normal; overflowWrap=normal; height=1026px |

### 触控热区风险

| 序号 | 元素路径 | 文案 | 尺寸 | 面积 |
| --- | --- | --- | --- | --- |
| 0 | div.header-wrapper > div.header-inner.isDeveloper > div.hwc-header-bottom > h2.hwc-header-logo-outer > a.hwc-header-logo |  | 70x25 @ (20,11) | 1750 |
| 1 | div.header-wrapper > div.header-inner.isDeveloper > div.hwc-header-bottom > div.logo-title > a | 开发者 | 48x24 @ (169,12) | 1152 |
| 2 | div.header-wrapper > div.header-user-detail.slide-panel > ul.my-menu > li.level1 > a | 个人主页 | 16x163 @ (24,229) | 2608 |
| 3 | ul.my-menu > li.level1.active > ul.children > li > a | 我的博客 | 14x160 @ (40,519) | 2240 |
| 4 | ul.my-menu > li.level1.active > ul.children > li > a | 我的论坛 | 14x160 @ (40,567) | 2240 |
| 5 | ul.my-menu > li.level1.active > ul.children > li > a | 我的圈子 | 14x160 @ (40,615) | 2240 |
| 6 | ul.my-menu > li.level1.active > ul.children > li > a | 我的直播 | 14x160 @ (40,663) | 2240 |
| 7 | ul.my-menu > li.level1.active > ul.children > li > a | 我的活动 | 14x160 @ (40,711) | 2240 |
| 8 | ul.my-menu > li.level1.active > ul.children > li > a | 我的关注 | 14x160 @ (40,759) | 2240 |
| 9 | ul.my-menu > li.level1 > ul.children > li > a | 我的课程 | 14x160 @ (40,1144) | 2240 |
| 10 | ul.my-menu > li.level1 > ul.children > li > a | 我的认证 | 14x160 @ (40,1192) | 2240 |
| 11 | ul.my-menu > li.level1 > ul.children > li > a | 我的实验 | 14x160 @ (40,1240) | 2240 |
| 12 | ul.my-menu > li.level1 > ul.children > li > a | 我的收藏 | 14x160 @ (40,1288) | 2240 |
| 14 | ul.my-menu > li.level1 > ul.children > li > a | 我的技术支持 | 14x256 @ (40,1096) | 3584 |
| 15 | ul.my-menu > li.level1 > ul.children > li > a | 我的云声建议 | 14x256 @ (40,1144) | 3584 |
| 16 | div.activity-banner-container > div.activity-banner-content > div.activity-banner-context > div.activity-banner-button-container > a.activity-banner-button.por-btn.por-btn-middle | 立即了解 | 98x32 @ (24,170) | 3136 |
| 18 | div.por-row.hide-pc > div.por-col-24 > a.por-card.has-border > div.card-content > object.btn-group | 查看详情 | 82x24 @ (49,460) | 1968 |
| 19 | div.por-col-24 > a.por-card.has-border > div.card-content > object.btn-group > a.por-btn.por-btn-md-small.por-btn-secondary | 查看详情 | 82x24 @ (49,460) | 1968 |
| 21 | div.por-row.hide-pc > div.por-col-24 > a.por-card.has-border > div.card-content > object.btn-group | 查看详情 | 82x24 @ (49,638) | 1968 |
| 22 | div.por-col-24 > a.por-card.has-border > div.card-content > object.btn-group > a.por-btn.por-btn-md-small.por-btn-secondary | 查看详情 | 82x24 @ (49,638) | 1968 |

## 主要问题

| 编号 | 级别 | 区域 | 问题 | 定位 | 证据 | 建议 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | p1 | 最佳实践列表区 | 实践案例卡片及“查看详情”按钮点击无响应 | div.por-section > div.por-container > div.por-section-body > div.por-row.hide-pc > div.por-col-24 > a.por-card.has-border、查看详情 | 移动端点击测试中，点击“Agentic DevOps Hands-On最佳实践”、“华为云VPC从入门到精通”等卡片及“查看详情”按钮，页面均返回 'no-visible-effect'。控制台抛出 CSP 安全策略冲突及 MIME 类型不匹配错误（Refused to execute script from... because its MIME type is not executable），导致核心跳转逻辑失效。 | 修改后：修复前端路由与脚本加载逻辑，解决 CSP 策略冲突，确保移动端用户点击卡片能正常跳转至对应的实践详情页。 |
| 2 | p2 | 个人中心侧边栏 | 侧边栏导航菜单项布局严重变形 | ul.my-menu > li.level1 > a | DOM 树中“个人主页”宽度仅 16px，高度 163px；“我的博客”宽度仅 14px，高度 160px。表明菜单项在移动端发生了极端的垂直拉伸与折行，文字完全无法正常阅读。 | 修改后：重构 `ul.my-menu` 的 CSS 布局，将 `flex-direction` 或宽度限制调整为适合移动端横向展开的样式，确保文字单行正常显示。 |
| 3 | p2 | 全局 | 关键操作按钮触控热区过小 | a.por-btn-secondary、a.por-link-more | “查看详情”按钮尺寸仅为 82x24px，“查看更多”链接尺寸仅为 74x16px，远低于移动端推荐的最小触控热区（48x48px），极易导致用户漏触或误触。 | 修改后：通过增加 padding 或设置 min-height: 44px / min-width: 44px 扩大物理触控热区，提升移动端操作便利性。 |
| 4 | p2 | 实践列表及卡片容器 | 页面容器存在横向溢出 | div#section-1 > div.pep-scenario-experience > div.por-section > div.por-container > div.por-section-body | DOM 数据显示该容器 clientWidth 为 342px，而 scrollWidth 为 346px，存在 4px 的横向溢出，会导致移动端页面整体产生不必要的左右微幅晃动。 | 修改后：检查并修正该容器的左右 padding/margin，确保子元素宽度不超过 100%，消除横向滚动条。 |

### 问题 1：实践案例卡片及“查看详情”按钮点击无响应

| 字段 | 内容 |
| --- | --- |
| 级别 | p1 |
| 区域 | 最佳实践列表区 |
| 定位 | div.por-section > div.por-container > div.por-section-body > div.por-row.hide-pc > div.por-col-24 > a.por-card.has-border、查看详情 |
| 证据 | 移动端点击测试中，点击“Agentic DevOps Hands-On最佳实践”、“华为云VPC从入门到精通”等卡片及“查看详情”按钮，页面均返回 'no-visible-effect'。控制台抛出 CSP 安全策略冲突及 MIME 类型不匹配错误（Refused to execute script from... because its MIME type is not executable），导致核心跳转逻辑失效。 |
| 标准 | Nielsen #4 |
| 建议 | 修改后：修复前端路由与脚本加载逻辑，解决 CSP 策略冲突，确保移动端用户点击卡片能正常跳转至对应的实践详情页。 |

### 问题 2：侧边栏导航菜单项布局严重变形

| 字段 | 内容 |
| --- | --- |
| 级别 | p2 |
| 区域 | 个人中心侧边栏 |
| 定位 | ul.my-menu > li.level1 > a |
| 证据 | DOM 树中“个人主页”宽度仅 16px，高度 163px；“我的博客”宽度仅 14px，高度 160px。表明菜单项在移动端发生了极端的垂直拉伸与折行，文字完全无法正常阅读。 |
| 标准 | Nielsen #8 |
| 建议 | 修改后：重构 `ul.my-menu` 的 CSS 布局，将 `flex-direction` 或宽度限制调整为适合移动端横向展开的样式，确保文字单行正常显示。 |

### 问题 3：关键操作按钮触控热区过小

| 字段 | 内容 |
| --- | --- |
| 级别 | p2 |
| 区域 | 全局 |
| 定位 | a.por-btn-secondary、a.por-link-more |
| 证据 | “查看详情”按钮尺寸仅为 82x24px，“查看更多”链接尺寸仅为 74x16px，远低于移动端推荐的最小触控热区（48x48px），极易导致用户漏触或误触。 |
| 标准 | Nielsen #7 |
| 建议 | 修改后：通过增加 padding 或设置 min-height: 44px / min-width: 44px 扩大物理触控热区，提升移动端操作便利性。 |

### 问题 4：页面容器存在横向溢出

| 字段 | 内容 |
| --- | --- |
| 级别 | p2 |
| 区域 | 实践列表及卡片容器 |
| 定位 | div#section-1 > div.pep-scenario-experience > div.por-section > div.por-container > div.por-section-body |
| 证据 | DOM 数据显示该容器 clientWidth 为 342px，而 scrollWidth 为 346px，存在 4px 的横向溢出，会导致移动端页面整体产生不必要的左右微幅晃动。 |
| 标准 | Nielsen #8 |
| 建议 | 修改后：检查并修正该容器的左右 padding/margin，确保子元素宽度不超过 100%，消除横向滚动条。 |

## 通过项与不适用项

- 本次检测对象为公开移动端页面，不涉及登录态、下单、支付、续费或退订流程。
- 首屏、滚动后、菜单展开和全页截图均已采集；HTML 默认展示前三类截图，全页截图保留在产物目录。
- 风险点击词如“购买/支付/提交订单”在采集脚本中被排除，不会执行交易类动作。

## 建议修复优先级

| 优先级 | 问题 | 建议动作 |
| --- | --- | --- |
| P1 | 实践案例卡片及“查看详情”按钮点击无响应 | 修改后：修复前端路由与脚本加载逻辑，解决 CSP 策略冲突，确保移动端用户点击卡片能正常跳转至对应的实践详情页。 |

| 优先级 | 问题 | 建议动作 |
| --- | --- | --- |
| P2 | 侧边栏导航菜单项布局严重变形 | 修改后：重构 `ul.my-menu` 的 CSS 布局，将 `flex-direction` 或宽度限制调整为适合移动端横向展开的样式，确保文字单行正常显示。 |
| P2 | 关键操作按钮触控热区过小 | 修改后：通过增加 padding 或设置 min-height: 44px / min-width: 44px 扩大物理触控热区，提升移动端操作便利性。 |
| P2 | 页面容器存在横向溢出 | 修改后：检查并修正该容器的左右 padding/margin，确保子元素宽度不超过 100%，消除横向滚动条。 |