### 步骤4: AI Agent逐阶段分析（SKILL.md编排，非脚本）

这是最复杂的步骤，由AI Agent按SKILL.md的指令执行，不通过Python脚本。每个阶段包含4a-4g子步骤：

#### 4a. 视觉截图分析 — 调用 `codespec ai vl-model` 命令

**实现方式**：AI Agent通过bash工具调用codespec CLI，对每张截图执行视觉分析

**截图分析顺序**（每阶段3张截图）：
```
1. 全页截图 — 整体布局扫描
   codespec ai vl-model --model Qwen3.5-35B-A3B-Think \
     --image "screenshot_1_awareness.png" "<全页视觉分析提示词>"

2. 上半部分 — 导航+首屏+定价区细节
   codespec ai vl-model --model Qwen3.5-35B-A3B-Think \
     --image "region_1_awareness_top.png" "<上半部分提示词>"

3. 下半部分 — 功能介绍+FAQ+Footer细节
   codespec ai vl-model --model Qwen3.5-35B-A3B-Think \
     --image "region_1_awareness_bottom.png" "<下半部分提示词>"
```

**多模型降级策略**（6级）：

```
优先级1: codespec ai vl-model --model Qwen3.5-35B-A3B-Think (默认)
优先级2: codespec ai vl-model-codeagent (Qwen2.5-VL-72B)
优先级3: codespec ai vl-model --model Qwen3.5-27B
优先级4: codespec ai vl-model --model Qwen3.5-35B-A3B-AWQ-VL
优先级5: codespec ai vl-model --model Qwen3.5-35B-A3B
优先级6: codespec ai vl-model --model Gemma-4-26B-A4B-it-AWQ-3
优先级7: 纯文本回退（仅基于DOM数据分析）
```

**降级执行规则（伪代码）**：
```python
def 视觉分析(截图路径, 提示词, 是全页截图=True):
    优先级表 = [优先级1, 优先级2, ..., 优先级6]
    
    for 优先级 in [1, 2, 3, 4, 5, 6]:
        重试次数 = 0
        while 重试次数 < 3:
            结果 = 执行bash命令(优先级表[优先级], timeout=120000)
            if 结果成功:
                return 结果
            elif 结果是413错误:  # 图片太大
                # 不降级模型！切换到分区截图从优先级1重试
                分区截图 = 获取对应的分区截图(截图路径)
                if 分区截图存在:
                    return 视觉分析(分区截图, 提示词, 是全页截图=False)
                else:
                    break  # 无分区截图，降级到下一优先级
            elif 结果是429错误:  # 限流
                sleep(30)
                重试次数 += 1
            elif 结果是504或超时:
                重试次数 += 1  # 同一优先级重试！不跳到分区截图
            else:
                break  # 其他错误，降级
    
    # 所有优先级的全页截图均失败 → 回退到分区截图
    if 是全页截图:
        for 分区 in 获取所有分区截图(截图路径):
            结果 = 视觉分析(分区, 提示词, 是全页截图=False)
        return 合并分区结果(分区结果)
    
    # 分区截图也全部失败 → 纯文本回退
    return "纯文本回退：仅基于DOM数据分析，无视觉分析结果"
```

**关键约束**：
- 每张截图都从优先级1开始，绝不沿用上一次的降级结果
- 413时不降级模型，切换到分区截图
- 全页截图504/超时时必须重试全页截图3次，不得跳过
- 重试时必须使用完整提示词，不得缩短或简化

**视觉分析提示词模板**（3套，分别对应全页/上半/下半）：

##### 全页截图提示词

```
你是华为云产品体验审查专家。请分析这个产品页面截图，逐区域扫描找出体验问题。

⚠️ 重要：这个页面一定存在问题，请仔细检查，不要轻易给出"无明显问题"的结论。

阶段: {stage_cn}

== 扫描方法（必须逐区域检查，不要跳过）==
请按以下区域从上到下依次扫描，每个区域都要给出结论：
1. 【顶部导航区】Logo、导航链接、登录/注册、搜索框
2. 【首屏主视觉区】产品名称、核心卖点、主CTA按钮、背景图/Banner
3. 【定价/套餐区】套餐卡片、价格、资源量、功能对比、购买按钮、约束提示
4. 【功能介绍区】功能卡片、图标、描述文案
5. 【FAQ/常见问题区】问题列表、折叠/展开状态
6. 【底部Footer区】链接、服务入口、法律声明

== 具体检查项（每个区域都要对照检查）==

【视觉与布局】[Garrett: Surface Plane | Nielsen #8: Aesthetic and Minimalist Design | 华为云设计系统]
- 核心CTA按钮（购买/订阅/试用）颜色是否醒目？与背景对比度是否足够？是否存在查找困难或误点误触？
- 关键约束信息的字号/颜色/位置是否足够突出？还是容易被忽略？
- 套餐卡片之间的视觉层级是否一致？推荐标签（如"最受欢迎"）是否突出？
- 同一页面不同区域的按钮/卡片/图标样式是否统一？有无差异化乱象？

【文案与信息】[Nielsen #2: Match Between System and Real World | Nielsen #4: Consistency and Standards]
- 是否有错别字、语病、用词不当？（特别注意形近字、同音字混淆）
- 同一页面不同区域对同一事物的描述是否前后矛盾？（特别注意正文与Footer/弹窗/提示之间的口径不一致）
- 约束性文案是否清晰无歧义？用户能否准确理解限制条件？

【交互与流程】[Garrett: Skeleton Plane | Nielsen #1: Visibility of System Status | Nielsen #3: User Control and Freedom | Nielsen #6: Recognition Rather Than Recall | Cooper: Goal-Directed Design]
- 核心操作入口位置是否醒目？同类操作入口的交互方式是否一致？
- 是否缺少用户期望的入口？（如免费试用、演示、价格计算器）
- 操作按钮是否过多/过少？核心操作是否被淹没？
- ⚠️ **购买/开通按钮跳转验证**：点击"购买"/"开通"按钮后，是否跳转到正确的购买/开通页面？还是跳到了控制台或其他无关页面？
- ⚠️ **搜索可达性**：在官网/控制台搜索框搜索产品关键词，能否找到开通/购买入口？搜索结果链接是否跳转到正确页面？

【信息完整性】[Garrett: Structure Plane | Nielsen #5: Error Prevention | Nielsen #10: Help and Documentation | ISO 9241-110: 适合学习性]
- 产品能力/计费标准/试用权益/优惠使用规则是否完整透明？有无前后矛盾？
- ⚠️ **计费规则完整性**：价格/费用说明是否包含计费区间、计费单位、计费周期等必要信息？是否缺少关键计费规则说明？
- ⚠️ **0元订单/免费产品**：免费体验版是否有明确的"0元"说明？是否缺少二次确认机制？自动续费机制是否清晰（0元自动续费需特别说明）？

【信息准确性与一致性】[Nielsen #4: Consistency and Standards | Cooper: Conceptual Integrity]
- 展示的产品名称/类型是否与用户实际购买的产品一致？是否有名称重复/冗余？（如产品类型字段出现同一名称重复拼接）
- 订单/支付页中每个字段是否准确反映用户购买内容？服务提供方、产品类型等是否正确？
- 页面中出现的所有名称、术语是否前后一致？是否存在同一事物在不同位置用不同名称？

【跨页面一致性】[Nielsen #4: Consistency and Standards]
（下单/变更/续费/退订阶段重点检查）
- ⚠️ 购买页与变更套餐页的套餐展示样式是否一致？功能描述/价格/文案是否统一？
- ⚠️ 同一产品在不同页面（官网/控制台/费用中心/订阅管理）的产品名称是否一致？
- ⚠️ 交易对账/订单页面中产品类型名称是否正确？是否显示了错误的产品类型（如显示"软件开发生产线"而非实际产品名）？

【状态一致性】[Nielsen #1: Visibility of System Status]
（续费/退订阶段重点检查）
- ⚠️ 产品状态（生效中/已过期/宽限期/退款中）是否与实际状态一致？是否出现已过期但仍显示"生效中"？
- ⚠️ 退订/退款操作后，各页面状态是否及时同步更新？

【交互模式评估】[Cooper: Modeless vs Modal | Nielsen #8: Aesthetic and Minimalist Design]
- ⚠️ 是否应使用轻量化弹窗而非页面跳转来完成简单操作（如续费、增购席位、支付确认）？
- ⚠️ 信息提示是否过于密集导致阅读超载？

【领域术语与费用说明可理解性】[Nielsen #2: Match Between System and Real World | Nielsen #5: Error Prevention | Cooper: Persona-Based Evaluation | ISO 9241-110: 自描述性]
- ⚠️ 页面是否使用了用户可能不理解的专业术语/缩写？是否提供了足够解释？用户能否仅从页面文字理解每个选项的含义和后果？
- ⚠️ 涉及费用时，是否有计算公式或明细拆解？用户能否验证费用合理性？还是只有一个总价？
- ⚠️ 操作是否有不可逆后果或额外费用产生？这些关键风险是否醒目提示（而非隐藏在小字或次级链接中）？
- ⚠️ 不同选项的生效时间、适用场景是否有对比说明？用户能否做出知情决策？

== 输出格式（严格遵守）==
逐区域扫描结果：
- 【顶部导航区】：（有问题/无明显问题，如有问题请简述）
- 【首屏主视觉区】：（有问题/无明显问题，如有问题请简述）
- 【定价/套餐区】：（有问题/无明显问题，如有问题请简述）
- 【功能介绍区】：（有问题/无明显问题，如有问题请简述）
- 【FAQ/常见问题区】：（有问题/无明显问题，如有问题请简述）
- 【底部Footer区】：（有问题/无明显问题，如有问题请简述）

综合评分(1-10)|合规(是/否)

问题列表（每行一条，编号开头，格式：[区域]具体问题描述，含视觉细节 | locate: 页面上能定位到该问题的实际文字 | evidence: 判定依据）：
1. [定价/套餐区]...

⚠️ 每个问题必须附带以下字段：
- locate：页面上能定位到该问题的实际文字（按钮文案、价格数字、约束提示原文等），用于后续DOM标注定位
  - 必须是页面上真实存在的文字，不要写分析结论
  - 优先使用该区域独有的文字，避免使用页面上多次出现的通用文字（如产品名称、通用按钮文案）
  - 多个locate文字时，第一个应是最精准的定位词
- evidence：判定该问题的客观依据，必须来自截图中的可观测事实，例如：
  - 视觉问题：「按钮宽约80px高约28px，在1920px宽页面中占比不足5%」
  - 文案问题：「按钮文案为"去在线支付"，用户更习惯"确认支付"」
  - 一致性问题：「定价区显示"¥59.00/月"，FAQ区描述为"59元每月"，单位格式不统一」
  - ⛔ 禁止写无依据的主观判断，如"不够醒目""视觉权重不足"而不说明具体尺寸/颜色/位置
  - ⛔ 禁止写"根据截图可见"等空泛描述，必须给出可量化或可对比的具体数据
  - ⛔ 涉及时间/数值的结论必须给出计算过程，禁止仅凭单个数字下判断。例如：不要写"截止时间为2026年，有效期过长"，必须写"订单创建时间2026/06/21，截止时间2026/06/28，有效期7天"
- standard：该问题违反的业界标准依据，取自上方检查项中【】后标注的标准编号，例如：
  - 视觉/布局类问题 → `Garrett: Surface Plane | Nielsen #8`
  - 交互/流程类问题 → `Garrett: Skeleton Plane | Nielsen #1 | Nielsen #6`
  - 信息完整性类问题 → `Garrett: Structure Plane | Nielsen #5`
  - 一致性类问题 → `Nielsen #4`
  - 术语/可理解性类问题 → `Nielsen #2 | ISO 9241-110`
  - 状态同步类问题 → `Nielsen #1`
  - 搜索/可达性类问题 → `Nielsen #6`
  - 风险提示/确认类问题 → `Nielsen #5`
  - 新手引导/帮助类问题 → `Nielsen #10`

格式：
1. [定价/套餐区]价格数字字号约12px，远小于套餐名称的18px，在定价区视觉权重不足 | locate: ¥59.00, ¥149.00, ¥399.00, ¥799.00 | evidence: 截图中价格数字字号约12px，套餐名称字号约18px，价格字号仅为名称的67% | standard: Garrett: Surface Plane | Nielsen #8

建议列表（每行一条，编号与问题对应，必须可操作，必须包含修改前→修改后示例）：
1. [问题描述] 修改前："当前文案" → 修改后："建议文案"；或 修改前：当前样式(fontSize:12px, color:#999) → 修改后：建议样式(fontSize:16px, color:#333, font-weight:700)

⚠️ 建议必须包含具体的修改示例，格式为"修改前→修改后"：
- 文案类问题：给出修改前后的文案对比，如 修改前："立即购买"/"购买"/"免费开通" → 修改后：统一为"立即购买"（付费）/"免费开通"（免费）
- 样式类问题：给出修改前后的样式参数对比，如 修改前：fontSize:12px, color:rgb(128,128,128) → 修改后：fontSize:14px, color:rgb(220,38,38), font-weight:700
- 流程类问题：给出修改前后的交互流程对比，如 修改前：点击购买→跳转控制台 → 修改后：点击购买→跳转购买页
- 信息类问题：给出修改前后的信息展示对比，如 修改前：仅显示"¥1,981.45" → 修改后：显示"基础版 ¥39/席位/月 × 50席位 × 剩余31天 = ¥1,981.45"
```

##### 上半部分截图提示词（聚焦导航+首屏+定价区细节）

```
你是华为云产品体验审查专家。这是产品页面的上半部分截图（顶部导航+首屏主视觉+定价/套餐区）。

⚠️ 请仔细检查每个细节，重点关注小字、约束提示、按钮样式。这个区域一定存在问题。

请检查以下区域：
1. 【顶部导航区】Logo、导航链接、登录/注册、搜索框
2. 【首屏主视觉区】产品名称、核心卖点、主CTA按钮
3. 【定价/套餐区】套餐卡片、价格、资源量、购买按钮、约束提示文字

重点检查项：[Garrett: Surface Plane + Skeleton Plane | Nielsen #2 #4 #6 #8 | Cooper: Conceptual Integrity]
- 各套餐的操作按钮颜色、背景、文字颜色是否完全一致？如有差异请具体描述
- 约束提示文字（如限制条件、免责声明、购买须知）的字号和颜色是否足够醒目？还是容易被忽略？
- 价格/资源量单位是否统一？用户能否直观对比？
- 是否有错别字、语病？
- 首屏是否有核心CTA按钮？
- 套餐卡片视觉层级是否一致？推荐标签是否突出？
- 产品名称/类型是否与实际购买产品一致？是否有名称重复/冗余？

输出格式：
逐区域扫描结果（每个区域都要给出结论）
问题列表（编号开头，格式：[区域]具体问题描述，含视觉细节如颜色、字号、位置 | locate: 页面上能定位到该问题的实际文字 | evidence: 判定依据，必须来自截图中的可观测事实，如具体尺寸/颜色/位置数据。涉及时间/数值的结论必须给出计算过程 | standard: 违反的业界标准编号）
建议列表（编号与问题对应，必须可操作，必须包含修改前→修改后示例，如 修改前："当前文案" → 修改后："建议文案" 或 修改前：fontSize:12px → 修改后：fontSize:16px,font-weight:700）
```

##### 下半部分截图提示词（聚焦功能介绍+FAQ+Footer细节）

```
你是华为云产品体验审查专家。这是产品页面的下半部分截图（功能介绍区+FAQ+Footer）。

⚠️ 请逐字检查FAQ文字内容，逐条核对Footer信息。这个区域一定存在问题。

请检查以下区域：
1. 【功能介绍区】功能卡片、折叠面板、描述文案
2. 【FAQ/常见问题区】问题列表、折叠/展开状态、每个问题的文字内容
3. 【底部Footer区】链接、服务入口

重点检查项：[Nielsen #2 #4 #10 | Garrett: Structure Plane | Cooper: Persona-Based Evaluation]
- FAQ文字：请逐条读取每个问题的文字，检查是否有错别字、语病（特别注意形近字、同音字混淆）
- 折叠面板默认展开/折叠状态是否合理？是否有关键信息被折叠隐藏？
- Footer中的服务入口是否与页面正文描述一致？（如退订、试用等入口与正文口径是否矛盾）
- 功能介绍区视觉层级是否清晰？折叠面板是否默认展开了足够多的内容？
- 信息是否完整？是否缺少关键说明？
- 展示的产品名称/类型是否与实际购买产品一致？是否有名称重复/冗余？

输出格式：
逐区域扫描结果（每个区域都要给出结论）
问题列表（编号开头，格式：[区域]具体问题描述，含视觉细节 | locate: 页面上能定位到该问题的实际文字 | evidence: 判定依据，必须来自截图中的可观测事实。涉及时间/数值的结论必须给出计算过程 | standard: 违反的业界标准编号）
建议列表（编号与问题对应，必须可操作，必须包含修改前→修改后示例，如 修改前："当前文案" → 修改后："建议文案" 或 修改前：fontSize:12px → 修改后：fontSize:16px,font-weight:700）
```

#### 4b. DOM数据分析 — Task子agent直接分析

**实现方式**：AI Agent启动Task子agent（general类型），直接读取crawl_result.json中的DOM数据分析

完整提示词如下：

```
Task(
  subagent_type="general",
  description="DOM数据分析-感知阶段",
  prompt="""你是华为云产品体验分析专家，正在审查[感知]页面的DOM数据。请根据以下页面数据，找出体验问题。

请先读取文件 <workspace>/temp/crawl_result.json 获取页面数据（取pages数组中stage匹配的元素），然后直接分析给出结果。

== 说明 ==
- structured_html字段包含页面元素的结构化HTML，style属性含实际渲染的字号、颜色、背景色、字重、透明度等
- disabled属性表示按钮/输入框的禁用状态
- class属性包含组件类型信息（如activity-promotion-card=套餐卡片，por-collapse-trigger=折叠触发器）
- 请结合HTML结构和样式信息分析，不要只看纯文本

== 具体检查项 ==

【交互与流程】[Garrett: Skeleton Plane | Nielsen #1: Visibility of System Status | Nielsen #3: User Control and Freedom | Nielsen #6: Recognition Rather Than Recall | Nielsen #7: Flexibility and Efficiency | Cooper: Goal-Directed Design]
- 核心操作入口位置是否醒目、层级合理？是否存在查找困难或误点误触？
- 操作链路是否简洁高效？是否有多余步骤或无效填写项？流程走向是否贴合用户习惯？
- 价格/优惠明细是否就近同步刷新？操作与结果展示是否割裂？
- 开通/下单/支付等全流程是否形成完整闭环？每步操作是否有明确结果反馈？
- 同类操作入口的交互方式是否一致？
- ⚠️ **购买按钮跳转目标**：购买/开通按钮的链接（href）是否指向正确的购买/开通页面？还是指向控制台首页？
- ⚠️ **交互模式评估**：简单操作（续费、增购席位、支付确认）是否应使用弹窗而非页面跳转？

【控制台跳转可达性】[Nielsen #6: Recognition Rather Than Recall | Nielsen #7: Flexibility and Efficiency | ISO 9241-110: 适合学习性]（仅使用阶段需要检查，其他阶段忽略此项）
- 在华为云主控制台搜索框输入产品名称，能否直接搜索到产品控制台入口？
- 在服务分类（如"人工智能"）下，产品是否可见？跳转路径是否过长（超过3步）？
- 产品控制台首页是否有产品/订阅管理的快捷入口？
- "最近访问"中是否显示产品入口？

【搜索可达性】[Nielsen #6: Recognition Rather Than Recall]（感知阶段重点检查）
- 官网搜索框输入产品关键词，搜索结果是否包含开通/购买入口？
- 搜索结果链接的href是否指向正确的购买页？
- 关联搜索是否缺失（搜索"开通+产品名"应出现开通入口）？

【规则与信息展示】[Garrett: Structure Plane | Nielsen #5: Error Prevention | Nielsen #8: Aesthetic and Minimalist Design | Nielsen #10: Help and Documentation | ISO 9241-110: 自描述性]
- 产品能力/计费标准/试用权益/优惠规则是否完整透明？各页面间规则口径是否统一？有无前后矛盾？
- 置灰/禁用选项是否搭配清晰文字说明告知不可选原因？
- 关键约束信息的字号/颜色是否足够突出？还是容易被忽略？
- ⚠️ **计费规则完整性**：是否缺少计费区间说明、计费单位、计费周期等关键信息？
- ⚠️ **0元订单/免费产品**：免费体验版是否缺少二次确认？自动续费机制是否清晰（0元自动续费需特别说明）？
- ⚠️ **按需计费说明可见性**：按需计费的扣费说明是否隐藏在问号悬浮框/资料链接中？是否应在显眼位置说明？
- ⚠️ **信息密度**：提示信息是否过多导致阅读超载？

【文案与信息一致性】[Nielsen #2: Match Between System and Real World | Nielsen #4: Consistency and Standards]
- 是否有错别字、语病、用词不当？
- 同一页面不同区域对同一事物的描述是否前后矛盾？
- 价格/资源量的单位是否统一且易于对比？
- 全局文案/功能提示/状态标签/报错话术风格是否统一？有无引导错误/文案疏漏？
- 是否有重复文本、冗余信息？
- 按钮文案是否过多/重复？核心操作是否被淹没？

【信息准确性与一致性】[Nielsen #4: Consistency and Standards | Cooper: Conceptual Integrity]
- 展示的产品名称/类型是否与用户实际购买的产品一致？是否有名称重复/冗余？
- 订单/支付页中每个字段是否准确反映用户购买内容？服务提供方、产品类型等是否正确？
- 页面中出现的所有名称、术语是否前后一致？是否存在同一事物在不同位置用不同名称？

【跨页面一致性】[Nielsen #4: Consistency and Standards]
（下单/变更/续费/退订阶段重点检查）
- ⚠️ 购买页与变更套餐页的套餐展示样式、功能描述、价格文案是否统一？
- ⚠️ 交易对账/订单页面中产品类型名称是否正确？是否显示了错误的产品类型（如显示"软件开发生产线"而非实际产品名）？
- ⚠️ 同一产品在不同页面（官网/控制台/费用中心/订阅管理）的产品名称是否一致？
- ⚠️ 即时变更vs续费变更的说明是否清晰易懂？费用差异是否明确？

【状态一致性】[Nielsen #1: Visibility of System Status]
（续费/退订阶段重点检查）
- ⚠️ 产品状态（生效中/已过期/宽限期/退款中）是否与实际状态一致？
- ⚠️ 退订/退款操作后，各页面状态是否及时同步更新？
- ⚠️ 套餐到期进入宽限期后，状态标签是否正确显示（而非仍显示"生效中"）？

【品牌与图标一致性】[Nielsen #4: Consistency and Standards]
- ⚠️ 购买页/控制台的产品图标是否正确？是否使用了错误的产品图标（如使用了父产品/关联产品的图标）？

【领域术语与费用说明可理解性】[Nielsen #2: Match Between System and Real World | Nielsen #5: Error Prevention | Cooper: Persona-Based Evaluation | ISO 9241-110: 自描述性]
- ⚠️ 页面是否使用了用户可能不理解的专业术语/缩写？是否提供了足够解释？用户能否仅从页面文字理解每个选项的含义和后果？
- ⚠️ 涉及费用时，是否有计算公式或明细拆解？用户能否验证费用合理性？还是只有一个总价？
- ⚠️ 操作是否有不可逆后果或额外费用产生？这些关键风险是否醒目提示（而非隐藏在小字或次级链接中）？
- ⚠️ 不同选项的生效时间、适用场景是否有对比说明？用户能否做出知情决策？

【视觉权重分析（基于HTML样式）】[Garrett: Surface Plane | Nielsen #8: Aesthetic and Minimalist Design]
- 关键约束信息的font-size和color是否与普通文本区分度足够？
- CTA按钮的字号/颜色是否醒目？
- 禁用元素的opacity是否过低导致用户注意不到？

== 输出格式 ==
问题列表（每行一条，编号开头，格式：[元素位置]具体问题描述 | locate: 页面上能定位到该问题的实际文字 | evidence: 判定依据 | standard: 违反的业界标准编号）：
1. [元素位置]问题描述 | locate: 实际文字1, 实际文字2 | evidence: 具体依据 | standard: Nielsen #4

⚠️ locate要求：
- 必须是页面上真实存在的文字，不要写分析结论
- 优先使用该区域独有的文字，避免使用页面上多次出现的通用文字（如产品名称、通用按钮文案）
- 多个locate文字时，第一个应是最精准的定位词

⚠️ evidence要求：
- 必须来自DOM数据中的可观测事实，例如：
  - 样式依据：「font-size: 12px，color: #999（灰色），而标题font-size: 18px，color: #333」
  - 结构依据：「该按钮嵌套在3层div内，被2个overflow:hidden的父元素包裹」
  - 数据依据：「buttons数据中该按钮width仅36px、height仅14px」
  - 文案依据：「按钮文案为"去在线支付"，常见支付流程用"确认支付"」
  - 一致性依据：「定价区显示"¥59.00/月"，FAQ区描述为"59元每月"，单位格式不统一」
- ⛔ 禁止写无依据的主观判断，如"不够醒目""视觉权重不足"而不说明具体样式数据
- ⛔ 禁止写"根据数据分析"等空泛描述，必须给出具体的属性值或对比数据

⚠️ standard要求：
- 取自上方检查项中【】后标注的标准编号
- 示例：视觉/布局类 → `Garrett: Surface Plane | Nielsen #8`；一致性类 → `Nielsen #4`；术语类 → `Nielsen #2 | ISO 9241-110`

建议列表（每行一条，编号与问题对应，必须可操作，必须包含修改前→修改后示例）：
1. 具体可操作的优化建议，格式：修改前："当前文案/样式" → 修改后："建议文案/样式"

示例：
1. 修改前：产品选择器显示"码道代码智能体套餐" → 修改后：统一为"华为云码道（CodeArts）代码智能体"
2. 修改前：fontSize:12px, color:rgb(128,128,128) → 修改后：fontSize:14px, color:rgb(220,38,38), font-weight:700
3. 修改前：仅显示"配置费用:¥1,981.45" → 修改后：显示"基础版 ¥39/席位/月 × 50席位 × 剩余31天 = ¥1,981.45"

请直接输出分析结果。"""
)
```

**DOM分析特有的检查能力**（视觉分析做不到的）：
- 精确的样式数据（font-size: 12px, color: #999）
- 按钮的disabled状态和原因
- href链接指向（购买按钮是否指向正确页面）
- DOM嵌套结构（元素被几层overflow:hidden包裹）
- 精确的元素尺寸（width: 36px, height: 14px）

#### 4c. 交叉验证+合并 — AI Agent直接执行

```
交叉验证流程:
1. 入口缺失检查
   ├── 读取 crawl_result.json 中该阶段page数据
   ├── 如果 entry_not_found: true
   └── 直接生成一条问题: "未找到[阶段]入口"，评分1-2分，跳过视觉和DOM分析

2. 目标产品匹配检查（最常遗漏）
   ├── 检查 page数据中是否包含 target_product_not_found: true
   ├── 如果包含 → 必须立即执行入口探索:
   │   ├── 回到产品自身的订阅管理页 (从pages中找含subscription/settings/manage的URL)
   │   ├── 查找该阶段的操作按钮 (如"续费"/"变更套餐"/"退订")
   │   ├── 点击进入后截图并提取数据
   │   └── 将补充数据追加到crawl_result.json
   ├── 探索后仍未找到 → 生成问题: "[阶段]页面未找到目标产品记录"，评分1-2分
   └── 该阶段仅保留"未找到目标产品记录"这一条问题

3. 验证视觉分析的问题是否真实
   ├── 视觉分析声称某元素不存在 → DOM数据中能找到 → 剔除该问题
   └── 视觉分析的描述与DOM数据矛盾 → 以DOM数据为准

4. 交叉验证时间/数值类结论
   ├── 视觉分析说"有效期过长" → 从DOM数据找创建时间和截止时间，计算实际间隔
   ├── 计算结果不成立 → 剔除该问题
   └── 计算结果成立 → 保留，补充具体数据到evidence

5. 剔除模板/检查清单式输出
   └── 去除"无明显问题"等空泛结论

6. 视觉分析和DOM的问题去重合并
   └── 同一问题在视觉和DOM分析中都出现 → 合并为一条，取更详细的evidence

7. 提取locate字段
   └── 从视觉分析和DOM分析的locate字段提取，合并为issue的locate数组

8. 写入 temp/stage_analysis.json
```

**stage_analysis.json 格式**：
```json
{
  "input_url": "产品URL",
  "analysis_time": "分析时间",
  "total_stages_analyzed": 7,
  "stages_analyzed": ["感知", "下单", ...],
  "stages_missing": [],
  "stage_analysis": {
    "感知": {
      "stage": "感知",
      "url": "页面URL",
      "title": "页面标题",
      "screenshot_path": "temp/screenshots/screenshot_1_awareness.png",
      "score": 8,
      "is_compliant": true,
      "issues": [
        {
          "title": "问题简要描述",
          "locate": ["页面上能定位到该问题的实际文字1", "实际文字2"],
          "evidence": "判定依据，来自截图/DOM数据的客观事实",
          "standard": "Garrett: Surface Plane | Nielsen #8"
        }
      ],
      "suggestions": ["建议1", "建议2"],
      "analysis_content": "详细分析内容",
      "model": "vl-model-codeagent+dom-ascend"
    }
  }
}
```

#### 4d. DOM标注截图 — 调用 `step4_annotate.py`

**执行方式**：
```bash
python scripts/step4_annotate.py --project-root "$PWD" --stage "感知"
```

**实现细节**（383行），详见下方"步骤4d详解"章节。

#### 4e. 使用阶段专属：控制台跳转可达性检查

**实现方式**：AI Agent通过agent-browser手动操作

```
执行步骤:
1. 打开主控制台:
   agent-browser --session journey_auto_session open "https://console.huaweicloud.com/console/"

2. 搜索产品名称:
   agent-browser --session journey_auto_session fill "#cf-service-input" "<产品名称>"
   # 等待2秒后检查搜索结果
   agent-browser --session journey_auto_session eval "document.querySelector('.components-service-list-container-service-list').innerText.substring(0,500)"

3. 检查服务分类:
   agent-browser --session journey_auto_session find text "人工智能" click
   # 获取分类下的服务列表
   agent-browser --session journey_auto_session eval "JSON.stringify(Array.from(document.querySelectorAll('.components-service-list-container-service-list a')).slice(0,20).map(e=>({text:e.innerText.trim().substring(0,60),href:(e.href||'').substring(0,80)})))"

4. 截图保存:
   agent-browser --session journey_auto_session screenshot "temp/screenshots/screenshot_4_usage_console.png"

5. DOM标注控制台问题:
   # 使用step4_annotate模块的annotate_element函数标注
   # 标注完成后截图保存为 annotated_使用_console.png

6. 更新数据文件:
   - 在stage_analysis.json的使用阶段中增加控制台跳转问题到issues数组
   - 增加extra_screenshots字段:
     {
       "extra_screenshots": [{
         "path": "temp/screenshots/screenshot_4_usage_console.png",
         "label": "控制台跳转检查 - 搜索产品名称",
         "issues": ["搜索产品名称找不到产品", "只能通过父产品间接找到"]
       }]
     }
   - 在annotated_screenshots_map.json中增加 使用_extra0 键映射
```

**检查项**：
- 在主控制台搜索框输入产品名称，能否直接搜索到产品控制台入口？
- 在服务分类下，产品是否可见？跳转路径是否过长（超过3步）？
- 产品控制台首页是否有产品/订阅管理的快捷入口？
- "最近访问"中是否显示产品入口？

#### 4f. 感知阶段专属：交互探索检查

**实现方式**：AI Agent通过agent-browser手动操作

```
执行步骤:
1. 购买按钮跳转验证:
   agent-browser --session journey_auto_session open "<感知页URL>"
   agent-browser --session journey_auto_session find text "购买" click
   # 等待2秒后检查跳转结果
   agent-browser --session journey_auto_session eval "JSON.stringify({url: window.location.href, title: document.title})"
   # 记录每个CTA按钮的跳转URL和页面标题
   # 如果跳转到控制台而非购买页 → 记录为问题

2. 官网搜索可达性检查:
   agent-browser --session journey_auto_session open "https://www.huaweicloud.com/"
   agent-browser --session journey_auto_session find css "input[type='search']" fill "<产品关键词>"
   # 等待搜索结果加载
   agent-browser --session journey_auto_session eval "document.querySelector('.search-result')?.innerText?.substring(0,500)"
   # 检查搜索结果是否包含开通/购买入口

3. 价格页购买按钮验证:
   agent-browser --session journey_auto_session open "<价格页URL>"
   agent-browser --session journey_auto_session find text "购买" click
   agent-browser --session journey_auto_session eval "JSON.stringify({url: window.location.href, title: document.title})"

4. 更新数据文件:
   - 将交互探索发现的问题追加到stage_analysis.json的感知阶段issues数组
   - 增加interaction_findings字段:
     {
       "interaction_findings": [{
         "action": "点击购买按钮",
         "button_text": "购买",
         "expected": "购买/开通页面",
         "actual": "产品控制台",
         "issue": "已开通用户点击购买跳转到控制台而非开通页面"
       }]
     }
```

#### 4g. 跨阶段一致性检查（所有7个阶段分析完成后执行一次）

**实现方式**：AI Agent直接执行，读取 `temp/stage_analysis.json` 和 `temp/crawl_result.json`

```
检查项:
1. 产品名称一致性
   ├── 从每个阶段的body_text/title/buttons中提取产品名称
   └── 同一产品出现2种以上名称 → 记录为问题

2. 购买页vs变更页样式一致性
   ├── 对比下单阶段和变更阶段的套餐展示样式
   └── 套餐卡片布局/价格展示方式/功能描述文案不一致 → 记录为问题

3. 交易对账页面产品类型名称
   ├── 检查支付/变更/续费/退订阶段的订单页面
   └── 产品类型名称与实际购买产品不一致 → 记录为问题

4. 状态标签一致性
   ├── 对比续费/退订阶段的状态显示
   └── 同一产品在不同页面显示不同状态 → 记录为问题

5. 文案一致性
   └── 同一操作在不同页面使用不同文案（如"续费"vs"续订"）→ 记录为问题

输出:
- 将跨阶段一致性问题追加到stage_analysis.json对应阶段的issues数组
- 每个问题标注 "source": "cross-stage-check"
```

**视觉分析与DOM的职责分工**：

| 检查项 | 视觉分析 | DOM分析 | 交互探索 | 跨阶段检查 |
|--------|:---:|:---:|:---:|:---:|
| 核心操作入口是否醒目 | ✅ | | | |
| 操作链路是否简洁 | ✅ | | | |
| 交互反馈是否即时 | | ✅ | | |
| 价格与配置是否就近同步 | ✅ | ✅ | | |
| 流程闭环 | ✅ | | | |
| 信息完整透明 | ✅ | ✅ | | |
| 置灰配原因说明 | | ✅ | | |
| 文案统一准确 | ✅ | ✅ | | |
| 布局视觉突出 | ✅ | | | |
| 组件样式统一 | ✅ | | | |
| 控制台跳转可达性 | | ✅ | ✅ | |
| 购买按钮跳转验证 | | | ✅ | |
| 搜索可达性 | | | ✅ | |
| 计费规则完整性 | | ✅ | | |
| 跨页面样式/文案一致性 | | ✅ | | ✅ |
| 交易对账页产品类型名称 | | ✅ | | ✅ |
| 状态标签一致性 | | ✅ | | ✅ |
| 交互模式评估 | ✅ | ✅ | | |
| 术语可理解性 | ✅ | ✅ | | |
| 费用计算是否透明 | | ✅ | | |
