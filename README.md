# 降 AI 味改写平台

面向中文学术论文的「规则 + LLM + 审计」改写平台。目标是在保留原意、段落结构、数字、引用和术语的前提下，降低文本中的机器生成特征。

## 功能

- 规则库：词汇替换、模板句式、句长节奏、上下文白名单、AFTER 侧替换黑名单。
- LLM 改写：按命中清单约束模型，多轮复检，保留占位符和事实。
- 内容层：扫描空泛断言和无源权威，生成澄清问题，把用户提供的真实数据、引用、案例写入正文。
- 诊断：五类味型、结构指标、改写前后对比。
- 过程痕迹清洗：思维链、UI 残留、agent 独白、checkbox、自用 Mermaid 图。
- 检测器反馈：手动或 CSV 录入真实送检结果，按检测器/版本分组校准代理指标。
- 账号与计费：注册、额度、兑换码、任务历史、管理员运营后台。

## 目录

```text
backend/    FastAPI + SQLModel 后端
frontend/   Next.js 14 前端
scripts/    部署、启动、在线更新脚本
data/       运行数据（数据库、密钥、模型、校准文件）
```

## 本地运行

```bash
# 后端
cd backend
python3 -m pip install --break-system-packages -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 18438

# 前端
cd frontend
npm install --no-audit --no-fund
npm run dev
```

一键启动：

```bash
bash start.sh
```

生产模式由 `scripts/serve.sh` 管理，后端 18438，前端 18437，前端把 `/api/*` 反代到后端。

## 测试

```bash
cd backend
python3 -m unittest discover -s tests -q

cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

Python lint（需要先安装 `backend/requirements-dev.txt`）：

```bash
ruff check backend/app backend/tests
```

## 固定参数

为避免误改导致效果回退，以下参数固定，Web 端不开放修改：

- 单候选、关闭深度改写、保持段落结构。
- 温度 1.2、最大输出 4096 tokens、并发 3、超时 120 秒、推理强度 medium。
- 困惑度阈值：达标 45、重写 2 次、严重标记 20。
- 本地模型：Qwen/Qwen2.5-1.5B + float16。

`/presets` 页面只读，`PUT /api/presets/{id}` 返回 400；`PUT /api/settings/llm` 会忽略固定字段。

## 环境变量

| 变量 | 说明 |
|---|---|
| `APP_DATA_DIR` | 数据目录，默认 `data/` |
| `MAX_INPUT_CHARS` | 单次改写上限，默认 30000 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | QQ 邮箱验证码 |
| `EMAIL_CODE_ECHO` | 测试时把验证码直接返回 |
| `ALERT_WEBHOOK_URL` | 错误告警 webhook |
| `LOCAL_MODEL` / `LOCAL_DTYPE` / `LOCAL_ENABLED` | 本地困惑度模型 |
| `GITHUB_WEBHOOK_SECRET` | 在线更新 webhook |

## 文档

- 规则与机制说明：`.monkeycode/docs/anti-ai-rules.md`
- 需求与设计：`.monkeycode/specs/`
