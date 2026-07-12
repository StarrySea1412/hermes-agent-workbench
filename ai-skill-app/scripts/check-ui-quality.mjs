import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

const files = {
  chatView: read('src/pages/chat/ChatView.jsx'),
  chatCss: read('src/pages/chat/ChatView.css'),
  chatShellCss: read('src/pages/chat/ChatShell.css'),
  chatInput: read('src/components/chat/ChatInput.jsx'),
  messageBubble: read('src/components/chat/MessageBubble.jsx'),
  insightPanel: read('src/components/chat/InsightPanel.jsx'),
  artifactList: read('src/components/workbench/ArtifactList.jsx'),
  agentRuns: read('src/pages/AgentRuns.jsx'),
  settings: read('src/pages/Settings.jsx'),
  workbenchHome: read('src/pages/WorkbenchHome.jsx'),
  workbenchSidebar: read('src/components/workbench/Sidebar.jsx'),
  indexCss: read('src/index.css'),
}

const checks = [
  {
    name: 'ChatView imports scoped chat styles',
    ok: files.chatView.includes("import './ChatShell.css'") && files.chatView.includes("import './ChatView.css'"),
    hint: 'ChatView must keep shell styles and page styles scoped to the chat module.',
  },
  {
    name: 'Chat workspace has task overview',
    ok: files.chatView.includes('function TaskOverview') && files.chatView.includes('className="task-overview"'),
    hint: 'The chat page should expose goal, files, tools, artifacts, and phase in one visible workflow.',
  },
  {
    name: 'Mobile runtime state remains available',
    ok: files.chatView.includes('mobile-runtime-panel') && files.chatCss.includes('.chat-app .mobile-runtime-panel'),
    hint: 'When the desktop right rail is hidden, mobile users still need model/session/tool state.',
  },
  {
    name: 'Responsive breakpoints cover tablet and phone widths',
    ok: hasMedia('(max-width: 980px)') && hasMedia('(max-width: 720px)') && hasMedia('(max-width: 640px)'),
    hint: 'ChatView.css should keep explicit tablet, compact tablet, and phone breakpoints.',
  },
  {
    name: 'Phone layout hides desktop rail only after mobile runtime panel exists',
    ok: files.chatCss.includes('@media (max-width: 640px)') &&
      files.chatCss.includes('.chat-app .delivery-rail') &&
      files.chatCss.includes('display: none') &&
      files.chatCss.includes('.chat-app .mobile-runtime-panel') &&
      files.chatCss.includes('display: grid'),
    hint: 'The right rail can be hidden on phones only if the compact runtime panel is visible.',
  },
  {
    name: 'Global CSS no longer owns chat module selectors',
    ok: !/\.chat-app\b|\.message-list\b|\.delivery-rail\b|\.chat-workspace\b/.test(files.indexCss),
    hint: 'Chat module layout selectors belong in ChatShell.css or ChatView.css, not index.css.',
  },
  {
    name: 'Input actions use Chinese workflow labels',
    ok: ['规划任务', '检查问题', '生成产物', '整理资料', '任务上下文', '资料记忆', '工具执行'].every((text) => files.chatInput.includes(text)),
    hint: 'The composer should read like a Chinese task workbench, not developer placeholder tags.',
  },
  {
    name: 'Runtime panel supports compact mode',
    ok: files.insightPanel.includes('compact = false') && files.insightPanel.includes('insight-panel ${compact'),
    hint: 'The same runtime facts should render in desktop rail and mobile compact panel.',
  },
  {
    name: 'Generated artifacts render as delivery cards',
    ok: [
      'message-artifact-card',
      'message-artifact-format',
      'message-artifact-body',
      'message-artifact-action',
      'formatArtifactFormat',
    ].every((text) => files.messageBubble.includes(text)) &&
      ['.chat-app .message-artifact-card', '.chat-app .message-artifact-action'].every((text) => files.chatCss.includes(text)),
    hint: 'Exported files should appear as structured delivery cards with format, preview, and open action.',
  },
  {
    name: 'Settings page protects model diagnostics loop',
    ok: [
      '获取模型',
      '测试连接',
      '复制诊断',
      '运行说明',
      '这份配置会影响什么',
      '基础 URL',
      '接口地址',
      '错误类型',
      'HTTP 状态',
      '建议',
    ].every((text) => files.settings.includes(text)),
    hint: 'Settings should explain model configuration, fetch models, test chat connectivity, and expose copyable diagnostics.',
  },
  {
    name: 'Settings page has no hardcoded runtime model',
    ok: !/\b(glm-5\.2|gpt-5\.5)\b/.test(files.settings),
    hint: 'Runtime model must come from saved settings or Hermes monitor data, not a hardcoded placeholder.',
  },
  {
    name: 'Workbench overview exposes complete task flow',
    ok: [
      'workbench-flow-panel',
      '配置模型',
      '开始聊天',
      '补充资料',
      '交付产物',
      '模型设置',
      '开始对话',
      '文件库',
    ].every((text) => files.workbenchHome.includes(text)) &&
      (files.workbenchHome.includes('运行记录') || files.workbenchHome.includes('任务历史')) &&
      ['.workbench-flow-grid', '.workbench-flow-card', '@media (max-width: 1120px)', '@media (max-width: 840px)']
        .every((text) => files.indexCss.includes(text)),
    hint: 'The overview should connect setup, chat, files, and delivery into one responsive product loop.',
  },
  {
    name: 'Workbench sidebar primary action opens chat',
    ok: files.workbenchSidebar.includes("onClick={() => navigate('/')}") &&
      files.workbenchSidebar.includes('开始对话') &&
      files.workbenchSidebar.includes('聊天、资料、工具与产物'),
    hint: 'The persistent primary action should send users to the chat-first workflow.',
  },
  {
    name: 'Workbench sidebar becomes compact mobile navigation',
    ok: [
      '@media (max-width: 840px)',
      '.workbench-sidebar .sidebar-nav',
      'overflow-x: auto',
      '.workbench-sidebar .sidebar-panel',
      '.workbench-sidebar .sidebar-account',
      'display: none',
      '@media (max-width: 560px)',
      '.workbench-sidebar .sidebar-launch',
    ].every((text) => files.indexCss.includes(text)),
    hint: 'Mobile workbench pages should show a compact top navigation instead of a full desktop sidebar before content.',
  },
  {
    name: 'Run detail artifacts render as delivery cards',
    ok: [
      'artifact-file-card',
      'artifact-type-pill',
      'artifact-summary',
      'artifact-raw',
      'formatArtifactFormat',
      'summarizeArtifactPayload',
    ].every((text) => files.artifactList.includes(text)) &&
      [
        '.artifact-file-card',
        '.artifact-type-pill',
        '.artifact-summary',
        '.artifact-raw',
      ].every((text) => files.indexCss.includes(text)),
    hint: 'Run detail artifacts should show file cards and collapsible raw data instead of defaulting to a JSON dump.',
  },
  {
    name: 'Run history supports search and status filters',
    ok: [
      'RUN_FILTERS',
      'runStats',
      'filteredRuns',
      'run-list-controls',
      'run-status-filters',
      'run-filter-chip',
      '搜索任务、模板、会话、错误或回答片段',
      '没有匹配当前筛选条件的运行记录',
    ].every((text) => files.agentRuns.includes(text)) &&
      [
        '.run-list-controls',
        '.run-status-filters',
        '.run-filter-chip',
        '.runs-row-main p',
        '@media (max-width: 840px)',
      ].every((text) => files.indexCss.includes(text)),
    hint: 'Run history should expose counts, keyword search, status filters, and responsive controls.',
  },
  {
    name: 'No common mojibake markers in frontend source',
    ok: !/[�]|浜ょ粰|姝ｅ湪|鐢熸垚|鍔犺浇|澶辫触|宸ュ叿/.test(frontendSource()),
    hint: 'Frontend source should be UTF-8 Chinese text, not mojibake from a wrong PowerShell encoding read.',
  },
]

const failed = checks.filter((check) => !check.ok)

for (const check of checks) {
  const status = check.ok ? 'OK' : 'FAIL'
  console.log(`${status} ${check.name}`)
  if (!check.ok) console.log(`   ${check.hint}`)
}

if (failed.length) {
  console.error(`\nUI quality check failed: ${failed.length} issue(s).`)
  process.exit(1)
}

console.log('\nUI quality check passed.')

function read(path) {
  return readFileSync(resolve(root, path), 'utf8')
}

function hasMedia(query) {
  return files.chatCss.includes(`@media ${query}`)
}

function frontendSource() {
  return [
    files.chatView,
    files.chatInput,
    files.insightPanel,
    files.messageBubble,
    read('src/components/chat/MessageList.jsx'),
    read('src/components/chat/ChatSidebar.jsx'),
    files.settings,
    files.artifactList,
    files.agentRuns,
    files.workbenchHome,
    files.workbenchSidebar,
  ].join('\n')
}
