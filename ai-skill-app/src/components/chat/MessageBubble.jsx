import { resolveFileUrl } from '../../api/files'

export default function MessageBubble({ message, pending }) {
  const isUser = message.role === 'user'
  const toolEvents = Array.isArray(message.metadata?.tool_events) ? message.metadata.tool_events : []
  const thoughts = Array.isArray(message.metadata?.thoughts) ? message.metadata.thoughts : []
  const { answer, inlineThink } = splitThinkFromContent(message.content)
  const sessionId = message.metadata?.session_id || ''
  const gateway = message.metadata?.gateway || ''
  const statusMessage = message.metadata?.status_message || ''
  const gatewayLabel = formatGateway(gateway)
  const artifactLinks = collectArtifactLinks(toolEvents)

  return (
    <article className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">{isUser ? '你' : 'H'}</div>
      <div className="message-bubble">
        <div className="message-role">{isUser ? '你' : 'Hermes'}</div>

        {!isUser && thoughts.length || inlineThink ? (
          <details className="thought-panel" open={pending || undefined}>
            <summary>
              <span>思考过程</span>
              <small>{pending ? '思考中...' : `${thoughts.length + (inlineThink ? 1 : 0)} 条`}</small>
            </summary>
            <div className="thought-list">
              {inlineThink ? (
                <article className="thought-item model">
                  <strong>模型思考</strong>
                  <p>{inlineThink}</p>
                </article>
              ) : null}
              {thoughts.map((thought, index) => (
                <article key={`${thought.title || 'step'}-${index}`} className={`thought-item ${thought.source === 'model' ? 'model' : ''}`}>
                  <strong>{thought.source === 'model' ? '模型思考' : (thought.title || `第 ${index + 1} 步`)}</strong>
                  {thought.content ? <p>{thought.content}</p> : null}
                </article>
              ))}
            </div>
          </details>
        ) : null}

        {!isUser && (sessionId || gateway || statusMessage) ? (
          <div className="message-runtime">
            {gatewayLabel ? <code>{gatewayLabel}</code> : null}
            {sessionId ? <code>{sessionId}</code> : null}
            {statusMessage ? <small>{statusMessage}</small> : null}
          </div>
        ) : null}

        {!isUser && toolEvents.length > 0 ? (
          <details className="tool-panel">
            <summary>
              <span>工具轨迹</span>
              <small>{pending ? '执行中' : `${toolEvents.length} 次动作`}</small>
            </summary>
            <div className="tool-event-list">
              {toolEvents.map((event) => (
                <article key={event.id || `${event.name}-${JSON.stringify(event.args || {})}`} className="tool-event-card">
                  <div className="tool-event-top">
                    <strong>{event.name || '工具'}</strong>
                    <span className={`tool-event-status ${event.status || 'running'}`}>
                      {formatToolStatus(event.status)}
                    </span>
                  </div>
                  {event.thought ? <p>{event.thought}</p> : null}
                  {event.args && Object.keys(event.args).length ? (
                    <details className="tool-event-args">
                      <summary>参数</summary>
                      <pre>{JSON.stringify(event.args, null, 2)}</pre>
                    </details>
                  ) : null}
                  {event.result_preview ? <small>{event.result_preview}</small> : null}
                  <ToolFileLink event={event} />
                </article>
              ))}
            </div>
          </details>
        ) : null}

        {!isUser && artifactLinks.length ? (
          <section className="message-artifacts" aria-label="交付产物">
            <div className="message-artifacts-head">
              <span>交付产物</span>
              <small>{artifactLinks.length} 个文件</small>
            </div>
            {artifactLinks.map((file) => (
              <article key={`${file.url}-${file.label}`} className="message-artifact-card">
                <div className="message-artifact-format">{formatArtifactFormat(file.format)}</div>
                <div className="message-artifact-body">
                  <strong>{file.label}</strong>
                  <p>{file.preview || formatArtifactHelper(file.format)}</p>
                </div>
                <a className="message-artifact-action" href={resolveFileUrl(file.url)} target="_blank" rel="noreferrer">
                  打开
                </a>
              </article>
            ))}
          </section>
        ) : null}

        <div className="message-content">
          {answer
            ? renderMarkdownLite(answer)
            : <span className="typing-dot">{pending ? '正在生成...' : '没有收到可显示的回复，请重试或检查模型连接。'}</span>}
          {pending ? <span className="cursor-pulse" /> : null}
        </div>
      </div>
    </article>
  )
}

function splitThinkFromContent(content) {
  const text = String(content || '')
  const segments = []
  const closed = /<think(?:ing)?\s*>([\s\S]*?)<\/think(?:ing)?>/gi
  let answer = text.replace(closed, (_m, inner) => {
    const trimmed = inner.trim()
    if (trimmed) segments.push(trimmed)
    return ''
  })
  const unclosed = /<think(?:ing)?\s*>([\s\S]*)$/i.exec(answer)
  if (unclosed) {
    const trimmed = unclosed[1].trim()
    if (trimmed) segments.push(trimmed)
    answer = answer.slice(0, unclosed.index)
  }
  return { answer: answer.trim(), inlineThink: segments.join('\n\n') }
}

function ToolFileLink({ event }) {
  const file = event?.result?.result
  if (!file?.url) return null
  return (
    <a className="artifact-link" href={resolveFileUrl(file.url)} target="_blank" rel="noreferrer">
      {file.filename || '打开文件'}
    </a>
  )
}

function renderMarkdownLite(content) {
  const lines = String(content || '').split('\n')
  const blocks = []
  let index = 0

  while (index < lines.length) {
    const rawLine = lines[index]
    const line = rawLine.trimEnd()

    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.trim().startsWith('```')) {
      const language = line.trim().slice(3).trim()
      const codeLines = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      index += 1
      blocks.push(
        <pre key={`code-${index}`} className="markdown-code">
          <code>{codeLines.join('\n')}</code>
          {language ? <span>{language}</span> : null}
        </pre>
      )
      continue
    }

    if (isTableStart(lines, index)) {
      const tableLines = []
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        tableLines.push(lines[index])
        index += 1
      }
      blocks.push(renderTable(tableLines, `table-${index}`))
      continue
    }

    if (line.startsWith('### ')) {
      blocks.push(<h4 key={`h4-${index}`}>{renderInlineText(line.slice(4))}</h4>)
      index += 1
      continue
    }
    if (line.startsWith('## ')) {
      blocks.push(<h3 key={`h3-${index}`}>{renderInlineText(line.slice(3))}</h3>)
      index += 1
      continue
    }
    if (line.startsWith('# ')) {
      blocks.push(<h2 key={`h2-${index}`}>{renderInlineText(line.slice(2))}</h2>)
      index += 1
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items = []
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ''))
        index += 1
      }
      blocks.push(
        <ul key={`ul-${index}`} className="markdown-list">
          {items.map((item, itemIndex) => <li key={itemIndex}>{renderInlineText(item)}</li>)}
        </ul>
      )
      continue
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = []
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+[.)]\s+/, ''))
        index += 1
      }
      blocks.push(
        <ol key={`ol-${index}`} className="markdown-list">
          {items.map((item, itemIndex) => <li key={itemIndex}>{renderInlineText(item)}</li>)}
        </ol>
      )
      continue
    }

    const paragraph = [line]
    index += 1
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith('```') &&
      !isTableStart(lines, index) &&
      !/^#{1,4}\s+/.test(lines[index]) &&
      !/^\s*[-*]\s+/.test(lines[index]) &&
      !/^\s*\d+[.)]\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index].trimEnd())
      index += 1
    }
    blocks.push(<p key={`p-${index}`}>{renderInlineText(paragraph.join(' '))}</p>)
  }

  return blocks
}

function renderInlineText(text) {
  const parts = []
  const pattern = /(\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*)/g
  let lastIndex = 0
  let match

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    if (match[2] && match[3]) {
      const [, , label, url] = match
      parts.push(
        <a key={`${url}-${match.index}`} className="artifact-link" href={resolveFileUrl(url)} target="_blank" rel="noreferrer">
          {label}
        </a>
      )
    } else if (match[4]) {
      parts.push(<code key={`code-${match.index}`} className="inline-code">{match[4]}</code>)
    } else if (match[5]) {
      parts.push(<strong key={`strong-${match.index}`}>{match[5]}</strong>)
    }
    lastIndex = pattern.lastIndex
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts.length ? parts : text
}

function isTableStart(lines, index) {
  const current = lines[index] || ''
  const next = lines[index + 1] || ''
  return current.includes('|') && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(next)
}

function renderTable(tableLines, key) {
  const rows = tableLines
    .filter((line) => !/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line))
    .map(parseTableRow)
    .filter((row) => row.length)
  const [header = [], ...body] = rows

  return (
    <div key={key} className="markdown-table-scroll">
      <table className="markdown-table">
        <thead>
          <tr>{header.map((cell, index) => <th key={index}>{renderInlineText(cell)}</th>)}</tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => <td key={cellIndex}>{renderInlineText(cell)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function parseTableRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}

function collectArtifactLinks(toolEvents) {
  const links = []
  const seen = new Set()

  toolEvents.forEach((event) => {
    const file = event?.result?.result
    if (!file?.url) return
    const key = `${file.url}-${file.file_id || ''}`
    if (seen.has(key)) return
    seen.add(key)
    links.push({
      label: file.filename || `文件 #${file.file_id || links.length + 1}`,
      url: file.url,
      format: file.format,
      preview: file.preview || event.result_preview || '',
    })
  })

  return links
}

function formatArtifactFormat(format) {
  const normalized = String(format || '').toLowerCase()
  if (normalized === 'xlsx') return 'Excel'
  if (normalized === 'docx') return 'Word'
  if (normalized === 'markdown' || normalized === 'md') return 'MD'
  return normalized ? normalized.toUpperCase() : 'FILE'
}

function formatArtifactHelper(format) {
  const normalized = String(format || '').toLowerCase()
  if (normalized === 'xlsx') return '表格文件已生成。'
  if (normalized === 'docx') return '文档文件已生成。'
  if (normalized === 'markdown' || normalized === 'md') return 'Markdown 文件已生成。'
  return '文件已生成。'
}

function formatToolStatus(status) {
  if (status === 'ok') return '完成'
  if (status === 'error') return '失败'
  return '执行中'
}

function formatGateway(gateway) {
  if (gateway === 'compat') return 'Hermes 兼容链路'
  if (gateway === 'fallback') return '本地保底答复'
  if (gateway === 'hermes') return 'Hermes 网关'
  return ''
}
