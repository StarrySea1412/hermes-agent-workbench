import { useMemo } from 'react'

export default function InsightPanel({ project, runtime, compact = false }) {
  const insights = useMemo(() => buildInsights(project), [project])
  const toolEvents = Array.isArray(runtime?.toolEvents) ? runtime.toolEvents.slice(-4).reverse() : []
  const usedTools = runtime?.usedTools?.length ? runtime.usedTools : []
  const modelName = runtime?.modelName || '未配置'
  const providerName = formatProvider(runtime?.provider)
  const temperature = runtime?.temperature ?? '未设置'
  const maxTokens = runtime?.maxTokens ?? '未设置'

  return (
    <section className={`insight-panel ${compact ? 'compact' : ''}`}>
      <div className="insight-header">
        <div>
          <p className="eyebrow">运行设置</p>
          <h2>{modelName}</h2>
          <p className="insight-subtitle">按设置页保存的模型配置执行。</p>
        </div>
        <span className="runtime-pill">{runtime?.gatewayLabel || 'Hermes'}</span>
      </div>

      <div className="studio-setting-list">
        <SettingRow label="模型" value={modelName} />
        <SettingRow
          label="提供方"
          value={providerName}
          helper={runtime?.baseUrl ? `请求地址：${runtime.baseUrl}` : '来自设置页的活动配置。'}
        />
        <SettingRow label="生成参数" value={`温度 ${temperature} / 上限 ${maxTokens}`} />
      </div>

      <div className="insight-section">
        <h3>本轮状态</h3>
        {runtime?.statusMessage ? <p className="runtime-status">{runtime.statusMessage}</p> : null}
        <div className="runtime-summary-grid">
          <Metric label="会话" value={runtime?.sessionId ? runtime.sessionId : '新会话'} />
          <Metric label="资料" value={`${runtime?.fileCount || 0} 份`} />
          <Metric label="工具" value={`${runtime?.toolCount || 0} 次`} />
        </div>
      </div>

      <div className="insight-section">
        <h3>已使用工具</h3>
        {usedTools.length ? (
          <div className="runtime-tool-chips">
            {usedTools.map((tool) => (
              <code key={tool}>{formatToolName(tool)}</code>
            ))}
          </div>
        ) : (
          <p className="muted">本轮还没有调用工具。</p>
        )}
      </div>

      {toolEvents.length ? (
        <div className="insight-section">
          <h3>最近活动</h3>
          <div className="runtime-event-list">
            {toolEvents.map((event) => (
              <div key={event.id || `${event.name}-${event.status}`} className="runtime-event">
                <strong>{formatToolName(event.name || 'tool')}</strong>
                <span>{formatToolStatus(event.status)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {insights.signals.length ? (
        <div className="insight-section">
          <h3>对话线索</h3>
          <ul>{insights.signals.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
        </div>
      ) : null}

      {insights.structure.length ? (
        <div className="insight-section">
          <h3>产物结构</h3>
          <ol>{insights.structure.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ol>
        </div>
      ) : null}
    </section>
  )
}

function Metric({ label, value }) {
  return (
    <div className="runtime-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function SettingRow({ label, value, helper }) {
  return (
    <div className="studio-setting-row">
      <div>
        <span>{label}</span>
        <small>{value}</small>
      </div>
      {helper ? <p>{helper}</p> : null}
    </div>
  )
}

function formatProvider(provider) {
  const map = {
    openai: 'OpenAI 兼容接口',
    deepseek: 'DeepSeek',
    qwen: 'Qwen',
    anthropic: 'Anthropic Claude',
    custom: '自定义端点',
  }
  return map[provider] || provider || '未配置'
}

function formatToolName(tool) {
  const map = {
    doc_parse: '资料解析',
    web_search: '联网搜索',
    doc_export: '文件导出',
    file_write: '文件写入',
  }
  return map[tool] || tool
}

function buildInsights(project) {
  const outline = Array.isArray(project?.outline)
    ? project.outline.map(cleanLine).filter(Boolean).slice(0, 6)
    : []

  const contentLines = String(project?.final_content || '')
    .split('\n')
    .map(cleanLine)
    .filter((line) => line.length > 10)

  const signals = contentLines
    .filter((line) => !/^(section|chapter|part)\b/i.test(line))
    .slice(0, 4)

  return {
    signals,
    structure: outline,
  }
}

function cleanLine(value = '') {
  return String(value)
    .replace(/^#+\s*/, '')
    .replace(/^[-*]\s*/, '')
    .replace(/^\d+\s*[.)]\s*/, '')
    .replace(/\*\*/g, '')
    .trim()
}

function formatToolStatus(status) {
  if (status === 'ok') return '完成'
  if (status === 'error') return '失败'
  return '执行中'
}
