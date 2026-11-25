# 降 AI 味规则与机制集成说明

本项目参考了两个公开项目，并把其中可落地的规则与机制接入到现有「规则 + LLM + 审计」流水线中：

- `zihanshen29/AI-Text-Anti-Detection-Framework`：三层工作流（诊断/计划/执行）、C-01~C-18 词汇规则、S-01~S-20 句法规则、上下文白名单、AFTER 侧替换黑名单、结构指标工具。
- `ln9527/evidence-based-humanizer`：五阶段流水线（诊断/减法/改写/泄露清洗/终检）、五类味型打分、语体对照、思维链与 agent 痕迹清洗、反过拟合原则。

## 一、规则库

### 词汇层（C 规则）

`backend/app/data/lexicons/zh_academic.json` 已补充：

- C-04 互联网黑话：赋能、抓手、闭环、生态、壁垒、颗粒度、底层逻辑、深耕等。
- C-05 “化”字后缀：系统化、结构化、可视化、模块化、流程化等。
- C-06 四字堆叠：全面提升、深度融合、扎实推进、持续优化等。
- C-07 抽象名词：格局、站位、范畴等。
- C-14 结尾抒情：必将、势必、指日可待、前景广阔、任重道远、未来可期。
- C-16 过度平衡：需要辩证看待、一分为二、不可一概而论等。
- C-17 伪总结反问：为什么会这样、问题出在哪里、原因有三等。
- P15 双刃剑；L3 意义拔高；L4 抒情腔（仅检测，不做机械替换）。

### 句法层（S / P 规则）

`backend/app/data/patterns/academic_patterns.json` 已补充：

- C-10 因果链套句、C-15 “这一 X”指代链。
- S-06 “对…进行/加以/作出/开展”改为直接动宾。
- S-09 “使得…成为可能”、S-10 “从…的角度来看”。
- 检测型正则：顿号堆叠（C-18）、长定语堆叠（S-04）、的字收尾（S-16）。

结构性指标由 `features.py` 的 `structural_metrics` / `structural_issues` 计算：句长 CV、连续短句、长句嵌套、三层“的”链、被字句密度、“它”字密度、的字收尾比例、破折号密度、段落长度 CV、完美列举、开头重复。

## 二、上下文保护

- `backend/app/data/context_whitelist.json`：生态环境、控制闭环、数字化转型、人工智能、技术壁垒等固定搭配整体占位保护。
- `context_guard.py` 提供 `Whitelist`，改写前由 `Protector` 遮罩，审计时跳过误报。
- 管理、流程语境的“闭环”标记为 `review`，避免机械替换。

## 三、AFTER 侧替换黑名单与多样性

- `backend/app/data/replacement_blacklist.json`：硬禁止产物（不只仅、再往下、完整流程等）与分语境替换池。
- `ReplacementGuard` 在规则替换时跳过黑名单词，并限制同一替换词在段内重复次数，防止“修掉旧模板又生成新模板”。
- 替换后的候选仍要经过 `guards.acceptable`：长度比、重复片段、连续短句、句长过度拉大、过程痕迹都会被拦截。

## 四、五类味型诊断

`diagnosis.py` 按每千字给五类味型打分：

1. 空洞升华
2. 模板句式
3. 高频套话
4. 语体错位（学术语境下的黑话、抒情腔、意义拔高、无源权威）
5. 思维链泄露

同时输出主导味型、结构问题、修改计划（按优先级排序），并生成改写前后的对比报告。前端「AI 特征审计」面板会展示诊断分表和前后变化。

## 五、过程痕迹清洗

`leakage.py` 在改写前和改写后各执行一次，覆盖：

- 推理自我修正（等等，让我想想、我重新看了一下）
- UI 残留（已深度思考（用时 X 秒）、Thought for X seconds）
- agent 过程独白（我现在将、接下来我来）
- 任务清单 checkbox
- 自用 Mermaid 图
- 讨好型元话语
- 内心戏残留

过程痕迹对读者信息量为零，命中即清；如果 LLM 改写后又带出痕迹，会再次清除。

## 六、反过拟合

`guards.py` 与 `diagnosis.compare` 负责：

- 改写后总特征密度显著上升时保留原文。
- 新增连续短句时先合并，再比较诊断分。
- 句长 CV 从正常被拉到 0.95 以上时视为刻意规避。
- 全文未下降时给出警告，提示补具体数据或人工复核。

## 七、验证方式

```bash
# 后端语法检查
cd /workspace/backend && python3 -m compileall -q app

# 前端类型检查
cd /workspace/frontend && npx tsc --noEmit
```

## 八、内容层（2026-11 增补）

- `content.py` 扫描空泛断言、无源权威、缺少实验条件和缺少局限的段落，生成澄清问题。
- `POST /api/rewrite/clarify` 返回问题清单和内容密度。
- 前端「扫描内容缺口」面板让用户填写真实数据、引用、案例、失败条件和判断。
- 填写结果作为 `content_facts` 传给 LLM；提示词只允许使用这些事实，禁止编造。
- 改写后 `verify_content` 核验事实是否写入、数字/引用/案例/局限数量是否下降。

## 九、结构层（2026-11 增补）

- `structure.py` 在 `structure_mode=flexible` 时执行段落边界调整。
- 操作包括：拆分过长段落、合并相邻短段、把末尾短句独立成单句段。
- 保持标题、序号和段落顺序不变，不新增内容。
- 响应里的 `structure_changes` 记录每次调整。

## 十、句子层（2026-11 增补）

- `deep_rewrite` 开关启用深度改写提示：改变信息顺序、主被动/把字句/无主句交替、删除显式因果连接词、在语义切换点断句。
- 规则引擎新增 `_split_at_connectives` 和 `_thin_connectives`：把“，因此/然而/从而”变成独立句，并保留第一个连接词、删掉后续重复连接词。

## 十一、模型层（2026-11 增补）

- `candidate_count` 控制每片首轮生成几个候选（默认 3）。
- `candidate.py` 用语义相似度、代理特征分、自然度和内容事实使用率综合打分，选一个候选。
- 真实检测器反馈校准后，`data/calibration.json` 中的权重会被候选选择器读取。

## 十二、评估层（2026-11 增补）

- `DetectorFeedback` 表记录检测器名称、版本、送检时间、改写前后分数、标红句和备注。
- `POST /api/detector/feedback` 录入反馈；`GET /api/detector/feedback` 查看记录。
- `GET /api/detector/calibration` 计算代理指标与检测分的相关性；`POST /api/detector/calibration` 在样本不少于 20 条时保存权重。
- 前端 `/detector` 页面提供反馈录入、记录列表和校准结果。
- 校准脚本：`python3 -c "from app.services.rewriter.calibration import build_report"` 仅用于本地验证，正式入口是 API。

## 十三、固定参数与只读页面（2026-11 增补）

- 稳定模式默认值：`deep_rewrite=False`、`candidate_count=1`、`structure_mode=preserve`。
- 生成参数固定：温度 1.2、最大输出 4096 tokens、推理强度 medium、并发 3、超时 120 秒。
- 困惑度阈值固定：达标 45、重写 2 次、严重标记 20。
- 后端启动时 `seed()` 会把 LLMSetting 中这些字段恢复为固定值；`PUT /api/settings/llm` 也会忽略前端传入的这些字段。
- 工作台不再展示深度改写、结构模式、候选数量三个手动开关，固定使用稳定模式。
- `/presets` 页面改为只读；`PUT /api/presets/{id}` 直接返回 400，预设参数只能通过后端默认配置调整。
- `/settings/llm` 页面移除了生成参数和困惑度阈值输入，只保留 Base URL、模型、API Key 和本地模型操作。

## 十四、检测器反馈增强（2026-11 增补）

- `/detector` 支持 CSV 导入和导出，表头为 `job_id, detector, detector_version, checked_at, score_before, score_after, red_sentences, notes`。
- 导入时按 `job_id + 检测器 + 版本 + 改写后分数` 去重，重复记录自动跳过。
- 标红句按模板连接词、不是…而是、不仅…而且、随着…发展、对…进行、被字句、三层的字链、长句、短句聚类展示。
- 校准按 `检测器 / 版本` 分组计算相关性和权重，样本最多的组作为当前权重组；分组结果写入 `data/calibration.json` 的 `groups` 字段。
- 本地模型固定为 Qwen/Qwen2.5-1.5B + float16；`LLMSettingIn` 只保留连接配置和本地模型开关。

## 十五、规则挖掘与文档级改写（2026-11 增补）

- 内容补充保持选填，不填也可以直接改写；页面已标注「选填」。
- 新增 `/mining` 规则挖掘页：上传或粘贴高 AI 率、低 AI 率文章，统计高频词、句式和结构差异，生成候选规则。
- 候选规则需要人工勾选后通过 `POST /api/mining/apply` 加入规则库，写入 `FeatureRule`，`builtin=False`。
- 挖掘只做离线统计，不自动改写，也不自动启用规则。
- 新增 `rewrite_granularity`：默认 `hybrid`（句分片 + 段落复检），可选 `document`（整篇改写）。
- 文档级改写要求段落数一致；超过 8000 字或段落数不一致时自动回退混合粒度。

## 十六、公开规则补充（2026-11 增补）

本轮规则只从公开项目、公开词表和公开文章整理，不新增模型自造规则。新增规则都写入 `backend/app/data/lexicons/zh_academic.json` 和 `backend/app/data/patterns/academic_patterns.json`，`note` 字段保留来源。

公开来源：

- `op7418/Humanizer-zh`：24 种中文 AI 写作模式，基于维基百科 `Signs of AI writing` 和 `blader/humanizer`。
- `baibanbao/qu-ai-wei`：中文去 AI 味规则，包含翻案腔、顿号罗列过密、翻译腔、拟人化喻体、名词化概括等实测规则。
- `xiaofenggan01/aigc-reduce`：72 个中文 AI 高频词替换表和学术改写协议。
- 公开文章：论文降 AIGC 高频词清单、AI 高频词替换表、AI 味结构清单等。

新增词汇规则（示例）：

- 拔高与宣传：不断演变的格局、关键转折点、重要里程碑、不可磨灭的印记、深深植根于、意义深远、前所未有的、充满活力、坐落于。
- 空洞评价：提供有力支撑、注入新动能、开辟新路径、发挥重要作用、提供理论支撑、奠定基础、深远影响。
- 模糊归因：学者认为、业内人士认为、相关研究显示。
- 书面套话：全面解析、多角度分析、归因于、涵盖、倾向于、见证了、这意味着、从某种程度上、蓬勃发展、与时俱进、日新月异、举足轻重、深入剖析。

新增句式规则（示例）：

- 翻案腔：不仅…而是、不在于…而在于、与其说…不如说、表面…实际、说到底。
- 拟人化喻体：就像…导师/灯塔/钥匙/桥梁/镜子/引擎/基石/纽带。
- 名词化概括：实现了…的提升/优化/增长/改善/转变。
- 客服与知识截止残留：如果您有任何问题、欢迎随时提问、如需进一步了解、截至知识截止。
- 翻译腔起手式：说白了。
- 拔高结构：标志着…关键转折点。

维护方式：

- 规则 JSON 改动后需要重启后端，`seed()` 会把新规则同步到 `FeatureRule`。
- 用 `python3 -m app.services.rewriter.rule_audit --summary` 检查重复、冲突和非法正则。
- 用 `python3 -m app.services.rewriter.eval` 跑固定样本，确认规则层没有让代理分回退。
