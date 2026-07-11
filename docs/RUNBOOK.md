# AI-skill 运行排错手册

本手册用于本地开发和演示环境，重点覆盖 5173 前端、8000 后端、8642 Hermes Gateway 三条链路。

## 服务端口

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 前端 | `http://127.0.0.1:5173/` | Vite dev server |
| 后端 | `http://127.0.0.1:8000/api/health` | Django API |
| Hermes | `http://127.0.0.1:8642/v1/models` | OpenAI-compatible Gateway |

## 启动

在项目根目录执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\start-ai-skill.ps1
```

脚本会：

1. 停止 5173、8000、8642 上已有监听进程
2. 设置 Hermes API Server 环境变量
3. 从 `.hermes-runtime/config.yaml` 读取模型名
4. 启动 Hermes Gateway、Django 后端和 Vite 前端
5. 请求三个 HTTP 探针确认服务状态

Hermes CLI 查找顺序：

1. PATH 中的 `hermes`
2. `%LOCALAPPDATA%\Programs\Python\Python*\Scripts\hermes.exe`
3. `%APPDATA%\Python\Python*\Scripts\hermes.exe`

如果仍找不到，脚本会直接报 `Hermes executable not found`。

## 停止

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\stop-ai-skill.ps1
```

## 状态检查

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\status-ai-skill.ps1
```

判断规则：

- `HttpStatus=200` 表示服务可访问
- `Listening=True` 来自 `Get-NetTCPConnection`，如果该命令不可用会回退到 `netstat -ano`
- `Listening=False` 且 `HttpStatus` 为空时，优先检查对应进程是否启动
- 日志尾部会过滤空字符，避免旧日志刷屏

## 日志位置

| 文件 | 内容 |
| --- | --- |
| `hermes-gateway.out.log` | Hermes Gateway 标准输出 |
| `hermes-gateway.err.log` | Hermes Gateway 错误输出 |
| `backend/codex-backend-run.out.log` | Django 标准输出 |
| `backend/codex-backend-run.err.log` | Django 错误和请求日志 |
| `ai-skill-app/codex-frontend-run.out.log` | Vite 标准输出 |
| `ai-skill-app/codex-frontend-run.err.log` | Vite 错误输出 |

## 模型来源

启动脚本不会写死模型名。

优先级：

1. `API_SERVER_MODEL_NAME`
2. `.hermes-runtime/config.yaml` 的 `model.default` 或 `model.name`
3. Hermes 默认行为

如果设置页模型和 Hermes 模型不一致，优先检查：

- 设置页当前活动配置
- `.hermes-runtime/config.yaml`
- 启动脚本输出的 `API_SERVER_MODEL_NAME`
- `/api/hermes/monitor?chat=false` 返回的模型列表

## 502 / 长时间无响应

按顺序检查：

1. `status-ai-skill.ps1` 三项 HTTP 是否为 200
2. 前端是否仍在请求旧 dev server 缓存
3. 后端日志是否出现 `/api/conversations/:id/stream/`
4. 后端是否切换到了 `compat` 或 `fallback`
5. 设置页“测试连接”是否能通过 `/chat/completions`

常见结论：

- `/models` 成功但聊天失败：上游列表接口可用，但聊天接口不可用
- 403：上游权限、IP、Cloudflare 或 required headers 问题
- TLS hostname mismatch：配置的域名和证书不匹配
- Connection error：后端无法与上游聊天 endpoint 建立可用连接
- 5xx：上游服务错误，通常需要换 provider 或稍后重试

## 前端样式边界

当前约定：

- `src/index.css`：全局 token、基础按钮、通用工作台样式
- `src/pages/chat/ChatShell.css`：聊天模块共享壳，含侧边栏、首页、资料页、项目详情页
- `src/pages/chat/ChatView.css`：聊天工作台主界面
- `src/pages/Settings.css`：设置页诊断样式

新增复杂页面时，不要继续把页面级布局写入 `index.css`。

## 验证命令

首选项目级验证：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\verify-ai-skill.ps1
```

需要连同当前服务可访问性一起检查时：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\verify-ai-skill.ps1 -CheckServices
```

可选参数：

- `-SkipBuild`：跳过前端生产构建
- `-SkipBackendTests`：跳过后端聊天流测试
- `-CheckServices`：额外执行 `status-ai-skill.ps1`

前端：

```powershell
cd ai-skill-app
npm.cmd run check:ui
npm.cmd run lint
npm.cmd run build
```

`check:ui` 用于守住前端静态质量底线：聊天页响应式断点、移动端运行状态入口、工作台移动端紧凑导航、设置页模型诊断闭环、总览页任务闭环、侧栏主入口、运行历史搜索筛选、运行详情产物卡片、全局 CSS 边界、中文工作流文案和常见乱码回归。
`lint` 用于检查 React hooks 规则、刷新边界和基础代码质量。

后端聊天流、模型列表诊断和导出链路：

```powershell
cd backend
.\venv\Scripts\python.exe manage.py test apps.projects.tests.ConversationHermesStreamTests --keepdb
.\venv\Scripts\python.exe manage.py test apps.ai_config.tests.AIModelListApiTests --keepdb
.\venv\Scripts\python.exe manage.py test apps.agents.tests.AgentRunApiTests.test_doc_export_persists_generated_markdown_file apps.agents.tests.AgentRunApiTests.test_doc_export_persists_generated_xlsx_file --keepdb
```

脚本语法：

```powershell
$null = [scriptblock]::Create((Get-Content -LiteralPath .\start-ai-skill.ps1 -Raw -Encoding UTF8))
$null = [scriptblock]::Create((Get-Content -LiteralPath .\stop-ai-skill.ps1 -Raw -Encoding UTF8))
$null = [scriptblock]::Create((Get-Content -LiteralPath .\status-ai-skill.ps1 -Raw -Encoding UTF8))
```
