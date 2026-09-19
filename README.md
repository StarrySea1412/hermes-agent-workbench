# AI-skill · Hermes Agent 工作台

一个本地优先的 AI Agent 工作台，可直接运行、可持续扩展：React 19 + Vite 液态玻璃前端、Django 5 + DRF 后端、Hermes 网关运行时，把「对话、资料检索、工具执行、交付产物」放进同一个工作流。

技术栈全景：React 19 + Vite 8 + TanStack Query ｜ Django 5 + DRF + SQLite/PostgreSQL ｜ Hermes 网关（Anthropic / OpenAI 兼容协议）｜ ddgs 免 key 搜索 ｜ 21 项前端 UI 质量门禁 + 178 项后端测试（全绿）。

> 模型在聊天里会**真实调用工具**（联网搜索 / Python 沙箱 / 文件读写 / 文档导出），每一次敏感调用都走**受控审批**，每一次文件写入都可**版本回滚**。

## 参考项目

- 交互与信息结构参考了 OpenAI Codex / Claude 的对话式 Agent 界面（工具轨迹、任务清单、节点跳转），只借鉴交互语言，未复制代码。
- 供应商配置导入能力借鉴 [cc-switch](https://github.com/farion1231/cc-switch) 的渠道管理思路，读取其本地数据库完成迁移。
- 网关运行时基于 [hermes-agent](https://github.com/anthropics/hermes-agent)（外部依赖，需本机安装）。

## 已实现功能

### 聊天与工具循环

- SSE 流式输出；思考过程 / 工具轨迹 / 任务清单全程可见
- 左侧刻度轨（tick rail）按用户 / 工具 / 回答节点列出全程，点击跳转 + 滚动追踪，悬停显示多行内容卡片
- 会话级模型切换（覆盖全局配置，下一轮生效）；聊天主动取消（前后端协同，半截回复与轨迹保留）
- 首 token 看门狗：上游 hang 90s 自动中止并沿降级链回退（网关 → 兼容直连 → 本地保底），不再无限等待

### 受控审批

- Python 沙箱等敏感工具逐次审批：pending → approved / denied / expired，决策接口幂等
- 审批记录轮询展示，到期自动失效；决策与状态同步全程可追溯

### 文件写入与回滚

- `workspace_files` 写入保留版本链，可查看文本差异并一键回滚到改动前内容
- 写入记录与审批面板统一管理

### 工具集

- `web_search`：优先 Brave / SerpAPI key，缺省走免 key 的 DuckDuckGo（ddgs）
- `doc_parse` / `doc_export`：资料解析与 xlsx / docx / html 导出
- `python_sandbox`：子进程隔离 + 超时强杀 + 导入阻断，图表以图片 artifact 回传
- `workspace_files`：受审批保护的文件读写
- MCP 服务器接入：stdio 服务器会话池、工具名前缀分发、管理 API 与管理 UI

### 记忆系统

- 用户 / 工作台 / 运行三级作用域的长期记忆，手动创建 + 对话后自动沉淀（0-3 条长期事实）
- 哈希相似度去重、置顶优先召回、每轮注入 system prompt 并回写使用时间

### 知识库 RAG

- 上传文档后台分块向量化入库，删除级联；支持配置 embedding 模型，无配置时降级本地哈希向量（CJK 切词）
- 召回结果注入两条聊天链路的 system prompt；换 embedding 模型后可手动重建索引

### 任务与运行

- 智能体模板：自定义 skill 路径、system prompt、工具白名单、步数上限
- AgentRun 运行实体：状态机、步骤与产物持久化、运行历史搜索筛选、取消与恢复

### 快速接入

- 从 CC Switch 一键导入供应商配置（后端读库保存 key，前端不见明文）
- 设置页内置模型拉取 / 连接测试 / 中文诊断详情 / 一键复制诊断

### 液态玻璃 UI

- 亮 / 暗双主题，aurora 光晕与玻璃质感贯穿全部页面
- `check:ui` 21 项质量门禁静态锁定页面结构与响应式断点，防止重构走样

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | React 19、Vite 8、TanStack Query、原生 CSS 设计令牌（无 UI 框架） |
| 后端 | Django 5、DRF、SQLite（默认）/ PostgreSQL、Fernet 加密、JWT |
| 网关 | hermes-agent 运行时（Anthropic / OpenAI 兼容协议） |
| 工具 | ddgs、PyPDF2、python-docx、openpyxl、MCP JSON-RPC |

## 快速开始

### 前置要求

- Python 3.12+、Node.js 18+
- Hermes 网关运行时（提供 `hermes` 命令；未安装时聊天退化为本地保底答复，工具循环不可用）

### 后端

```bash
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt   # Windows
copy .env.example .env                          # 按需修改
venv\Scripts\python manage.py migrate
venv\Scripts\python manage.py createsuperuser
venv\Scripts\python manage.py runserver 127.0.0.1:8000
```

### 前端

```bash
cd ai-skill-app
npm install
npm run dev        # http://localhost:5173
```

### 一键启动（Windows）

```powershell
.\start-ai-skill.ps1
```

脚本会拉起前端(5173) / 后端(8000) / Hermes 网关(8642) 并做健康检查；停止与状态检查分别用 `stop-ai-skill.ps1` / `status-ai-skill.ps1`。

## 配置与模型接入

| 配置 | 位置 | 说明 |
| --- | --- | --- |
| AI 供应商 | 登录后 → 设置页 | 提供方 / 模型 / Key / Base URL，Fernet 加密存储于后端 |
| 网关上游 | `.hermes-runtime/config.yaml` | 网关访问上游模型的协议与地址，设置页保存时自动同步 |
| 联网搜索 | `backend/.env` | 可选 `BRAVE_SEARCH_API_KEY` / `SERPAPI_API_KEY`，缺省走 ddgs 免 key |
| 服务密钥 | `start-ai-skill.ps1` | 网关服务密钥 `API_SERVER_KEY`，须与后端 `HERMES_GATEWAY_KEY` 一致 |

模型来源优先级：环境变量 `API_SERVER_MODEL_NAME` → `.hermes-runtime/config.yaml` 的 `model.default` / `model.name` → Hermes 默认行为。`/models` 可取列表不代表聊天可用，聊天可用性以 `/chat/completions` 测试或实际对话为准。

### 已知坑：点号模型名会被改写

Hermes 的 Anthropic 适配层默认把模型名里的 `.` 改写成 `-`（`grok-4.6` → `grok-4-6`）。多数中转站按**原始名**提供渠道，改写名一律 503 `No available channel`，且直接 curl 中转站用原始名明明是通的——这是最容易被误诊为"上游渠道挂了"的问题。

解决：`.hermes-runtime/config.yaml` 里把 `provider:` 设为 `zai`（同走 Anthropic 协议但保留模型名点号），并注入 `GLM_API_KEY` 环境变量（`start-ai-skill.ps1` 已自动处理）。不要把 provider 改回 `anthropic`。

## 数据与隐私

- 用户模型密钥经 Fernet 加密落库（`AI_CONFIG_ENCRYPTION_KEY`），设置页不回显明文
- `backend/.env`、`backend/db.sqlite3`、`.hermes-runtime/`、`media/`、日志均已被 .gitignore 排除，不会进入版本库
- 聊天数据默认存本地 SQLite；本仓库不含任何运行数据
- 网关服务密钥（`dev-test-key-for-local`）仅限本地开发，部署时必须更换

## 测试

后端全量测试：

```bash
cd backend
.\venv\Scripts\python.exe manage.py test --keepdb
```

当前 **178 项测试全部通过**，覆盖：受控审批状态机、文件写入回滚、MCP 子进程往返、SSE 流与取消、降级链（网关→兼容直连→本地保底）、记忆抽取与去重、RAG 分块、模型列表诊断等。

前端：

```bash
cd ai-skill-app
npm run check:ui    # 21 项 UI 质量门禁
npm run lint        # ESLint
npm run build
```

`check:ui` 会验证聊天页响应式断点、移动端运行状态入口、设置页模型诊断闭环、总览页任务闭环、全局 CSS 边界、中文工作流文案和常见乱码回归。

## 项目结构

```
├── ai-skill-app/            # React 前端
│   ├── src/pages/           # 聊天、资料、任务、记忆、技能、设置等页面
│   ├── src/components/chat/ # 消息气泡、审批面板、共享框架（ChatFrame）
│   └── scripts/check-ui-quality.mjs
├── backend/
│   ├── apps/agents/         # 智能体模板、运行、记忆 + 编排循环
│   ├── apps/tools/          # 工具注册表、受控审批、MCP、各工具 handler
│   ├── apps/projects/       # 会话、消息、项目资料
│   ├── apps/ai_config/      # 供应商配置（加密存储）、CC Switch 导入
│   ├── apps/files/          # 文件与 RAG 分块
│   └── services/            # 工具循环、审批、RAG、记忆、降级链、看门狗
├── hermes_skills/           # 本地技能目录（auto / manual）
├── start-ai-skill.ps1       # 一键启动三服务
└── verify-ai-skill.ps1      # 统一验证入口
```

## License

MIT License. Copyright (c) 2026 starry-sea-1412

完整文本见 [LICENSE](LICENSE)。
