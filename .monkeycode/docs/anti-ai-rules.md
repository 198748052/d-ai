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
