# User Instruction Memory

This file records user instructions, preferences, and project knowledge for future sessions.

## Format

### User Instruction Entry
- Date: [YYYY-MM-DD]
- Context: [scenario]
- Instructions:
  - [content]

### Project Knowledge Entry
- Date: [YYYY-MM-DD]
- Context: [discovered while doing X]
- Category: [Operations & Deployment | Build Methods | Testing Methods | Troubleshooting & Debugging | Workflow & Collaboration | Environment Configuration]
- Instructions:
  - [content]

## Entries

### 项目目标与迭代方向
- Date: 2026-11-19
- Context: 平台定位与后续迭代
- Instructions:
  - 目标：降低中文学术论文的 AI 检测率，保持原意、段落数量与顺序、标题和序号不变
  - 核心路线：规则库覆盖优先 + LLM 受规则约束改写 + 改写后审计
  - 规则库：持续从公开 AI 特征清单补充，覆盖面优先；多轮删除/替换直到收敛
  - 写作节奏：句长 CV、连接词密度、信息密度、限定语、句首多样性是主要优化目标
  - LLM 约束：先扫描本段命中的具体规则，把命中清单写进提示词；按句组分片改写；逐片复检；残留再纠正
  - 本地模型：当前只做逐句困惑度诊断；下一步用低困惑度句触发定向改写，先与用户检测器的标红段落做相关性验证
  - 质量红线：数字、引用、术语、公式、标题、序号不动；改写后必须审计；异常或重复结果回退
  - 迭代方式：用户用实际检测平台复测，把标红句子发回，按具体句式补规则或调提示词
  - 待办：GitHub 推送（需要仓库 URL）；检测器反馈闭环；低困惑度句定向改写

### 项目运行方式
- Date: 2026-11-19
- Context: 降 AI 味改写平台开发
- Category: Build Methods / Operations
- Instructions:
  - 后端：`cd /workspace/backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 18438`
  - 前端开发：`cd /workspace/frontend && npm run dev`（端口 18437）
  - 前端预览现用生产模式：`npm run build` 后 `npm start`；改完代码需要重新 build 再重启
  - 一键部署：先 `curl -o /tmp/deploy.sh` 再 `sudo bash /tmp/deploy.sh`；脚本会自动转入后台并写 `.run/deploy.log`，断 SSH 不影响
  - 部署可重复执行：venv/node_modules 已存在时跳过或增量安装，失败后直接重跑即可续上
  - 首次启动后端才下载 Qwen2.5-1.5B（约 3.1G），用 `journalctl -u ai-rewrite -f` 看进度
  - 本地模型统一用 `Qwen/Qwen2.5-1.5B`（float16 约 3.5G），8G 机器可跑；部署脚本默认 LOCAL_ENABLED=1 并在首次启动时下载
  - 环境变量可覆盖默认值：LOCAL_MODEL、LOCAL_DTYPE、LOCAL_ENABLED；如需更省内存再切 Qwen2.5-0.5B
  - 服务托管：`bash scripts/serve.sh` 启动前后端并自动重启，PID 写在 `.run/`；不要再单独起 uvicorn/next
  - 在线更新：管理员后台「在线更新」或 `POST /api/admin/update/run`，脚本 `scripts/update.sh` 执行 fetch + ff-only + 依赖安装 + 前端构建 + 重启
  - 可配置 GitHub webhook：`POST /api/webhooks/github`，环境变量 `GITHUB_WEBHOOK_SECRET`，仅处理 main 分支 push
  - 预览环境带宽约 500KB/s，dev 模式 main-app.js 有 6MB（eval-source-map），首屏要 10s+；生产包约 460KB，首屏 0.2s
  - 一键启动：`/workspace/start.sh`
  - 前端 `next.config.js` 把 `/api/*` 反代到 `http://127.0.0.1:18438`
  - 预览地址：`https://18437-8cc70a671b4b3627.monkeycode-ai.online`
  - Next dev 首次访问新页面编译可能 1-2 分钟，属于正常现象

### 本地模型
- Date: 2026-11-19
- Category: Environment Configuration / Troubleshooting
- Instructions:
  - HuggingFace 不可达；`hf-mirror.com` 会 308 跳回 `huggingface.co`，实际不可用
  - 模型下载走 ModelScope 文件接口：`https://www.modelscope.cn/api/v1/models/{model}/repo?Revision=master&FilePath={file}`
  - 当前使用 `Qwen/Qwen2.5-1.5B`，float16，缓存目录 `/workspace/data/models/Qwen__Qwen2.5-1.5B`（约 3.1GB）
  - 旧模型 `Qwen/Qwen2.5-0.5B` 仍在 `/workspace/data/models/Qwen__Qwen2.5-0.5B`（约 954MB）
  - 后端启动时若 `local_enabled=true` 会自动从缓存加载，不会重复下载
  - 1.5B 从缓存加载约 1-2 分钟；CPU 推理较慢，加载后剩余内存约 500MB
  - 1.5B 必须用 float16；用 float32 重新加载会被 OOM killer 杀掉（exit 137），后端随之退出，需改回 float16 再重启
  - `/api/settings/llm/local/load` 重复点击会重载模型；已改为先释放旧权重再加载，且接口直接拒绝 float32，避免内存翻倍被 OOM
  - 逐句困惑度接口：`POST /api/settings/llm/perplexity`

### LLM 与任务
- Date: 2026-11-19
- Category: Troubleshooting / Environment Configuration
- Instructions:
  - LLM 设置：`/api/settings/llm`，当前网关 `https://wbapi.topsygf.cn/v1`，模型 `deepseek-v4.1-flash-sg`
  - API Key 用 Fernet 加密存 `data/app.db`，密钥文件 `data/secret.key`
  - 当前网关不返回 `logprobs`，无法直接用 API 算困惑度，所以用本地模型算
  - 任务持久化在 SQLite `rewritejob` 表；服务重启会把 `running` 标记为 `interrupted`
  - SQLModel 要求时间字段带时区：必须用 `datetime.now(timezone.utc)`；`datetime.utcnow()` 会导致插入失败
  - 改写任务走 `POST /api/rewrite/jobs`，前端轮询 `GET /api/rewrite/jobs/{job_id}`
  - LLM 偶发返回空内容，已加 3 次重试；异常长度或重复结果会被清理或回退
  - 空内容根因：该网关模型带推理，`reasoning_tokens` 会吃满 `max_tokens`（4096），触发 `finish_reason=length` 且 `content` 为空；节奏调整提示词最重，最容易命中
  - 复现方式：直接 POST `/chat/completions` 打印 `finish_reason`、`usage.completion_tokens_details.reasoning_tokens`、`content` 长度
  - 排查结论：重试沿用相同参数，3 次可能全部失败；需要按 `finish_reason=length` 单独处理（提高 max_tokens 或降低推理消耗）

### Git 与推送
- Date: 2026-11-19
- Category: Workflow & Collaboration
- Instructions:
  - `/workspace` 已 `git init`，首次提交 `8f3bc4a`
  - `.gitignore` 已排除 `data/models/`、`node_modules`、`.next`、`data/app.db`、`data/secret.key`
  - 平台通过 `GIT_CONFIG_*` 注入凭据助手 `/app/agent/bin/agent git-credential-helper`，返回的 `ghs_` 令牌是 GitHub App 安装令牌，可直接用 git 推送
  - 已绑定仓库 `https://github.com/198748052/d-ai.git`，remote 名为 origin，`main` 已跟踪 `origin/main`
  - 令牌可访问该账号下 12 个仓库，可用 `curl -H "Authorization: Bearer $T" https://api.github.com/installation/repositories` 列出
  - 推送流程：`git add .` → `git commit` → `git push origin main`

### C 端账号与计费
- Date: 2026-11-20
- Category: Operations & Deployment / Workflow
- Instructions:
  - 首个注册用户自动成为管理员；管理员可见运营后台、规则库、预设、LLM 设置
  - 注册赠送 100 字；按提交正文的非空白字符数扣费，任务在产出任何段落前失败会自动退款
  - 兑换码由管理员生成，用户在我页面兑换；管理员可在 /admin 直接加/减额度
  - 接口分组：`/api/auth/*` 认证、`/api/credits/*` 余额与兑换、`/api/admin/*` 运营
  - 当前测试管理员账号 `admin@example.com`，密码需用户自行修改；不要再把密码写入仓库
  - 任务记录按 `rewrite_job.user_id` 隔离，历史无归属任务仅管理员可见
  - 设置页 `/settings/llm`、规则库写入、预设写入、踩坑记录删除均要求管理员
  - 踩坑记录按小句（逗号/分号/冒号切分）落库，每句最多取 2 个低困惑度小句，避免整段长句

### 用户偏好
- Date: 2026-11-19
- Context: 平台需求与多轮反馈
- Instructions:
  - 用中文回复
  - 平台聚焦学术论文降 AI 率，只保留「学术论文」一个预设
  - 改写固定「规则 + LLM 混合」；没有 LLM 配置时直接报错，不降级
  - 保持段落数量、顺序、标题和序号；保护数字、引用、术语、公式
  - 避免过度润色和过于工整的短句；要长短句交错、允许适度冗余和限定语
  - 改写后必须做 AI 特征审计；任务记录要能复制、暂停/继续、支持移动端
  - 本地模型文件不能因重启丢失，必须自动从缓存加载
