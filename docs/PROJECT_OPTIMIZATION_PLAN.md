# AI-skill 项目优化规划

## 当前定位

AI-skill 应优先成为一个“打开聊天就能推进任务”的 Hermes Agent 工作台，而不是传统后台管理系统。核心路径是：

1. 配置模型与 Hermes 网关
2. 进入聊天会话
3. 上传资料或直接下达任务
4. 观察工具调用与运行状态
5. 产出可下载文件、计划、文档或代码检查结果

## 主要问题

### 1. 前端样式缺少边界

`src/index.css` 已经超过 80KB，并且聊天页样式重复出现多次。多个断点反复覆盖 `.chat-workspace`、`.delivery-rail`、`.insight-panel`，导致响应式布局不稳定。

处理原则：

- 页面级复杂布局不要继续写进 `index.css`
- 聊天页使用 `pages/chat/ChatView.css` 作为最终样式边界
- 后续逐步把 Settings、Workbench、Memory 等页面样式拆出

### 2. 聊天工作台信息层次不清

之前“运行设置”面板同时承担模型配置、工具状态、记忆、产物等信息，但很多区域为空或弱信息，导致看起来像半成品。

优化方向：

- 运行设置只展示当前真正生效的信息
- 工具、活动、产物只在有数据时展示
- 输入框保持稳定位置，消息区保留主要空间
- 中等屏幕保持右侧状态栏，小屏幕才折叠

### 3. AI 配置诊断需要闭环

当前已经补了模型列表拉取和测试连接诊断，但还需要形成用户可理解的闭环：

- 获取模型成功不等于聊天可用
- 测试连接必须验证 `/chat/completions`
- 失败信息要明确区分 403、TLS、Cloudflare、连接失败、限流
- 聊天失败时要复用同一套诊断文案

### 4. Hermes 与兼容链路需要更清楚

Hermes 本地网关、Settings 模型配置、上游 OpenAI-compatible provider 三者容易混淆。

后续应在 UI 中明确：

- Hermes 网关是否在线
- 当前 Settings 模型是什么
- 聊天实际走 Hermes 还是兼容回退链路
- 上游 provider 的 chat endpoint 是否可用

### 5. 启动与运行状态需要稳定

当前脚本能启动服务，但在受限执行环境中后台进程可能被回收。对真实用户环境需要：

- 保留 `start-ai-skill.ps1` / `stop-ai-skill.ps1`
- 增加状态检查脚本，例如 `status-ai-skill.ps1`
- 日志路径固定，并在 README 中说明
- 前端页面提供“复制诊断信息”能力

## 优先级路线

### P0：稳定聊天主路径

- 独立 `ChatView.css`，收敛聊天页响应式布局
- 精简运行设置面板，只保留有用状态
- 保证 1280、1024、900、720、390 宽度下不横向错位
- 构建验证通过

### P1：设置页与模型诊断闭环

- 设置页展示模型测试详情
- 明确“模型列表成功”和“聊天测试成功”的区别
- 增加可复制诊断信息
- 减少默认写死项，全部从当前配置或用户输入派生

### P2：CSS 架构治理

- 保留 `index.css` 作为全局 token、基础组件和通用布局
- 每个复杂页面建立自己的 CSS 文件
- 删除 `index.css` 中重复的历史聊天样式
- 建立 CSS 命名边界，避免跨页面覆盖

### P3：后端可观测性

- AI 测试接口返回结构化错误
- 聊天流记录 gateway、model、provider、endpoint、tool events
- Hermes monitor 默认轻量检查，按需执行 chat probe
- 日志中统一 request id / user id / conversation id

### P4：交付体验

- 对 Excel、文档、资料解析任务，优先产出可下载 artifact
- 消息中展示 artifact 卡片，而不是纯文本链接
- 工具调用过程可折叠，默认不占主聊天空间

## 已完成的本轮优化

- 聊天页新增 `src/pages/chat/ChatView.css`
- `ChatView.jsx` 导入页面级样式，避免继续依赖全局 CSS 顺序
- 运行设置面板改为只显示有效信息
- 本轮状态改为紧凑指标：会话、资料、工具
- 聊天页新增“任务总览”，把目标、资料、工具、产物和阶段进度放在同一工作流里
- 移动端新增可展开运行状态，避免小屏隐藏右侧栏后丢失模型、会话、工具状态
- 输入区快捷动作和状态标签改为中文任务语义：规划任务、检查问题、生成产物、整理资料
- 工具活动、对话线索、产物结构改为有数据才展示
- 新增 `ai-skill-app/scripts/check-ui-quality.mjs` 和 `npm run check:ui`，用于静态检查聊天页响应式断点、移动端运行状态入口、全局 CSS 边界、中文工作流文案和常见乱码回归
- 聊天消息中的导出结果从普通链接升级为“交付产物”卡片，展示文件格式、文件名、预览和打开动作，提升 Excel/Word/Markdown 产物可发现性
- `check:ui` 增加 artifact 卡片结构检查，防止导出结果展示退回普通链接
- `doc_export` 的 Excel 交付增加后端测试覆盖，验证 xlsx 文件持久化、文件类型识别、OpenXML 包结构和工作表内容
- `detect_file_type()` 增加 `xlsx` 识别，生成的 Excel 文件不再被标记为 `other`
- 删除 `index.css` 中两段临时聊天布局覆盖块，降低重复覆盖风险
- 新增 `status-ai-skill.ps1`，用于检查 5173、8000、8642 服务状态和关键日志
- `start-ai-skill.ps1` / `stop-ai-skill.ps1` / `status-ai-skill.ps1` 的端口监听检测增加 `netstat -ano` 回退，避免 `Get-NetTCPConnection` 在部分环境下漏报
- `status-ai-skill.ps1` 仍以 HTTP 探测作为最终可访问性判断
- 设置页模型连接测试支持中文诊断详情和“一键复制诊断”
- 设置页模型列表获取成功/失败支持中文诊断详情和“一键复制诊断”
- 模型列表 API 增加失败诊断测试，覆盖上游连接失败返回 502、客户端配置错误返回 400，以及 `hint` / `endpoint` / `error_type` 结构化字段
- 设置页新增 `src/pages/Settings.css`，诊断 UI 样式从全局 `index.css` 拆出
- 启动脚本不再写死 `glm-5.2` / `gpt-5.5`，优先使用环境变量或 `.hermes-runtime/config.yaml` 中的模型
- 聊天页 `ChatView.css` 改为 `.chat-app` 页面作用域样式，降低全局历史 CSS 对响应式布局的干扰
- 聊天消息中的工具轨迹默认折叠，避免生成过程占用主聊天空间
- 聊天流式错误事件返回结构化诊断，前端聊天页展示错误类型、HTTP 状态、建议和原始错误，并支持复制诊断
- 修复兼容链路读取模型名时对不完整配置对象的脆弱假设，避免成功回答被 `AttributeError` 中断
- 新增 `src/pages/chat/ChatShell.css`，把聊天模块侧边栏、首页、资料页、项目详情页的共享壳样式从全局样式中迁出
- 删除 `index.css` 中未使用的 `thought-panel` 样式和一整段旧聊天视觉方案，降低历史样式覆盖响应式布局的风险
- 继续删除 `index.css` 中 `Gemini AI Studio reference pass` 与 `Hermes chat workbench refresh` 两段旧聊天覆盖块，`index.css` 降至 2359 行
- 补齐 `ChatShell.css` / `ChatView.css` 中的资料上传、导出、结构列表、聊天按钮和输入区标签样式，并移除 `index.css` 最后一段聊天模块样式；`index.css` 降至 1130 行
- 总览页新增“配置模型、开始聊天、补充资料、交付产物”四步工作流，把设置页、聊天页、文件库和运行记录串成一条主线
- 工作台侧栏主按钮改为“开始对话”，品牌入口回到聊天主路径，减少旧 Agent 编排页面和新聊天工作台之间的割裂
- `check:ui` 增加设置页模型诊断、总览页工作流和侧栏主入口检查，防止前端再次退回半成品状态
- 工作台通用侧栏在 840px 以下改为 sticky 顶部紧凑导航，隐藏桌面辅助块，避免移动端正文被完整桌面侧栏挤到首屏之后
- `check:ui` 增加工作台移动端侧栏检查，确保紧凑导航、横向滚动和桌面辅助块隐藏不会回退
- 运行详情页的产物列表从默认展示原始 JSON 升级为交付卡片：文件格式、名称、预览、打开入口优先展示，原始 payload 放入折叠区
- `check:ui` 增加运行详情产物卡片检查，防止运行链路和聊天链路的产物展示质量再次分裂
- 运行历史页新增状态统计、关键词搜索、状态筛选和回答/错误预览，便于快速定位失败、运行中和已完成任务
- `check:ui` 增加运行历史搜索筛选检查，确保历史任务入口不退回为不可检索的简单列表
- README 改为当前项目状态的中文快速启动说明，明确聊天入口、模型来源、状态脚本和常见 502/Connection error 排查
- 新增 `docs/RUNBOOK.md`，沉淀本地启动、状态检查、日志路径、模型来源、错误诊断和验证命令
- `start-ai-skill.ps1` / `start-hermes.bat` 不再绑定固定 Windows 用户目录或 Python313，改为优先 PATH 并扫描常见 Python Scripts 目录查找 Hermes CLI
- 新增 `verify-ai-skill.ps1`，统一执行脚本语法、前端 UI 质量门、ESLint、前端构建、后端聊天流测试、模型列表诊断测试和导出产物测试，并可选检查运行中服务状态
- 修复前端 React hooks lint 债务：模板、技能、记忆、工作流、运行详情页不再用 effect 同步派生本地状态
- 前端 `npm run check:ui`、`npm run lint` 和构建已通过

## 下一步建议

1. 用浏览器实际检查聊天页在 1280、1024、900、720、390 宽度下的布局
2. 在本地可用浏览器或 Playwright 后，为聊天页补一组截图级响应式检查
3. 为 Workbench、Workflow 等复杂页面继续拆出页面级 CSS
4. 继续优化 Excel、文档导出任务的 artifact 卡片和下载入口
