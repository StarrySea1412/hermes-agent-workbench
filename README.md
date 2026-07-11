# AI-skill Hermes 工作台

AI-skill 是一个本地优先的 Hermes Agent 工作台。当前主路径是：打开聊天、配置模型、上传资料、观察工具调用、产出可下载成果。

项目包含：

- React/Vite 前端：聊天工作台、资料区、技能目录、运行设置、实验性 Agent 页面
- Django 后端：会话、项目资料、模型配置、Hermes 监控、工具调用和文件导出
- Hermes Gateway 本地运行链路：通过 OpenAI-compatible `/v1` 接口承接聊天和工具调用

## 快速启动

在项目根目录执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\start-ai-skill.ps1
```

启动成功后访问：

- 前端：`http://127.0.0.1:5173/`
- 后端健康检查：`http://127.0.0.1:8000/api/health`
- Hermes 模型列表：`http://127.0.0.1:8642/v1/models`

启动脚本会优先使用 PATH 中的 `hermes` 命令；如果找不到，会扫描当前用户常见的 Python `Scripts\hermes.exe` 安装目录。

停止服务：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\stop-ai-skill.ps1
```

检查状态和最近日志：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\status-ai-skill.ps1
```

`status-ai-skill.ps1` 会先用 `Get-NetTCPConnection` 检查监听端口，失败时自动回退到 `netstat -ano`。最终仍以 HTTP 探测为准：只要 `HttpStatus=200`，服务就是可访问的。

## 统一验证

提交或继续大改前，优先执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\verify-ai-skill.ps1
```

它会检查 PowerShell 脚本语法、前端 UI 质量门、ESLint、前端构建、后端聊天流、模型列表诊断和导出产物测试。

如果还要确认当前本地服务是否可访问：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\verify-ai-skill.ps1 -CheckServices
```

## 模型配置

运行时模型不再写死在启动脚本里。

模型来源优先级：

1. 当前环境变量 `API_SERVER_MODEL_NAME`
2. `.hermes-runtime/config.yaml` 中的 `model.default` 或 `model.name`
3. Hermes 自身默认行为

前端设置页用于保存当前账号模型配置，并提供：

- 获取模型列表
- 测试 `/chat/completions`
- 中文诊断详情
- 复制诊断信息

注意：`/models` 成功只证明模型列表可取，不等于聊天可用。聊天可用性要看 `/chat/completions` 测试或实际对话结果。

## 常用页面

- `/`：聊天工作台
- `/chat/:convId`：指定会话
- `/projects`：资料/工作空间列表
- `/projects/:projectId`：工作空间详情、资料上传、导出
- `/settings`：模型配置、Hermes 状态、技能检查
- `/skills`：本地 Hermes skills
- `/agent`、`/runs`、`/workflows`：实验性 Agent/工作流页面

## 本地账号

开发环境通常使用：

- 用户名：`admin`
- 密码：`admin123`

如果需要重建：

```powershell
cd backend
.\venv\Scripts\python.exe manage.py ensure_demo_user --username admin --password admin123 --force-password
```

## 开发命令

后端：

```powershell
cd backend
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

前端：

```powershell
cd ai-skill-app
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

前端构建：

```powershell
cd ai-skill-app
npm run check:ui
npm run lint
npm run build
```

`check:ui` 是不依赖浏览器的前端质量检查，会验证聊天页响应式断点、移动端运行状态入口、工作台移动端紧凑导航、设置页模型诊断闭环、总览页任务闭环、侧栏主入口、运行历史搜索筛选、运行详情产物卡片、全局 CSS 边界、中文工作流文案和常见乱码回归。
`lint` 用于捕捉 React hooks、刷新边界和基础代码质量问题。

后端相关测试：

```powershell
cd backend
.\venv\Scripts\python.exe manage.py test apps.projects.tests.ConversationHermesStreamTests --keepdb
.\venv\Scripts\python.exe manage.py test apps.ai_config.tests.AIModelListApiTests --keepdb
.\venv\Scripts\python.exe manage.py test apps.agents.tests.AgentRunApiTests.test_doc_export_persists_generated_xlsx_file --keepdb
```

## 常见问题

### 页面请求很久或出现 502

先执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\status-ai-skill.ps1
```

重点看：

- frontend 是否 `200`
- backend 是否 `200`
- hermes 是否 `200`
- 后端日志是否有 `/api/hermes/monitor`
- Hermes 日志是否有 gateway 错误

### API call failed after 3 retries: Connection error

含义是后端或 Hermes 已经重试多次，但仍无法连到上游聊天接口。常见原因：

- `base_url` 不是 OpenAI-compatible `/v1`
- 上游 `/chat/completions` 不通，但 `/models` 能通
- API key 无权限或额度不足
- TLS 证书域名不匹配
- Cloudflare / 403 拦截
- 上游服务超时或 5xx

在设置页使用“测试连接”，复制诊断信息再定位。聊天页失败时也会显示同一类结构化诊断。

## 更多文档

- [项目优化规划](docs/PROJECT_OPTIMIZATION_PLAN.md)
- [运行排错手册](docs/RUNBOOK.md)
- [Hermes 集成说明](HERMES_INTEGRATION.md)
- [部署说明](DEPLOY.md)
