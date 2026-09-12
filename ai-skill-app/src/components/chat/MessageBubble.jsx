import { useEffect, useRef, useState } from 'react'
import Icon from '../Icon'
import { resolveFileUrl } from '../../api/files'

export default function MessageBubble({ message, pending, isLast = false, onRegenerate }) {
  const isUser = message.role === 'user'
  const toolEvents = Array.isArray(message.metadata?.tool_events) ? message.metadata.tool_events : []
  const thoughts = Array.isArray(message.metadata?.thoughts) ? message.metadata.thoughts : []
  const { answer, inlineThink } = splitThinkFromContent(message.content)
  const statusMessage = message.metadata?.status_message || ''
  const artifactLinks = collectArtifactLinks(toolEvents)
  const thinkingSeconds = message.metadata?.thinking_seconds
  const thinkBodyRef = useRef(null)
  const thinkingActive = pending && !answer
  const thoughtCount = thoughts.length + (inlineThink ? 1 : 0)
  const checklist = isUser ? null : buildTaskChecklist({ pending, thoughts, toolEvents, answer })
  const [copyState, setCopyState] = useState('')

  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(answer)
      setCopyState('已复制')
    } catch {
      setCopyState('复制失败')
    }
    window.setTimeout(() => setCopyState(''), 1600)
  }

  useEffect(() => {
    if (pending && thinkBodyRef.current) {
      thinkBodyRef.current.scrollTop = thinkBodyRef.current.scrollHeight
    }
  }, [thoughts.length, pending])

  return (
    <article className={`message-row ${isUser ? 'user' : 'assistant'}`} id={`msg-${message.id}`}>
      <div className="message-avatar" aria-hidden="true">
        {isUser ? <Icon name="user" size={13} /> : <Icon name="spark" size={14} strokeWidth={1.8} />}
      </div>
      <div className="message-bubble">
        <div className="message-role">{isUser ? '你' : 'Hermes'}</div>

        {checklist ? <TaskChecklist steps={checklist} /> : null}

        {!isUser && thoughtCount || thinkingActive ? (
          <section className={`thought-panel ${thinkingActive ? 'thinking' : ''}`} aria-live="polite">
            <button
              type="button"
              className="thought-head"
              onClick={(event) => {
                const body = event.currentTarget.nextElementSibling
                if (body) body.classList.toggle('collapsed')
              }}
            >
              <span className={`thought-label ${thinkingActive ? 'shimmer' : ''}`}>
                {thinkingActive ? '思考中' : `已思考 ${typeof thinkingSeconds === 'number' ? `${thinkingSeconds} 秒` : '完成'}`}
              </span>
              <small>{thinkingActive ? '流式输出中' : `${thoughtCount} 条`}</small>
            </button>
            {/* Codex 式：思考中流式展开，完成后自动收起为一行摘要 */}
            <div className={`thought-body ${thinkingActive ? '' : 'collapsed'}`} ref={thinkBodyRef}>
              {thoughts.map((thought, index) => (
                <article key={`${thought.title || 'step'}-${index}`} className={`thought-item ${thought.source === 'model' ? 'model' : ''}`}>
                  <strong>{thought.source === 'model' ? '模型思考' : (thought.title || `第 ${index + 1} 步`)}</strong>
                  <p>
                    {thought.content}
                    {pending && index === thoughts.length - 1 && thought.source === 'model' ? <span className="type-caret" /> : null}
                  </p>
                </article>
              ))}
              {thinkingActive && !thoughts.length && !inlineThink ? (
                <div className="thought-waiting"><span /><span /><span /></div>
              ) : null}
            </div>
          </section>
        ) : null}

        {!isUser && statusMessage ? (
          <div className="message-runtime">
            <small>{statusMessage}</small>
          </div>
        ) : null}

        {!isUser && toolEvents.length > 0 ? (
          <div className={`tool-trace ${pending ? 'running' : ''}`}>
            {toolEvents.map((event, toolIndex) => {
              const running = pending && event.status === 'running'
              return (
                <details
                  key={event.id || `${event.name}-${JSON.stringify(event.args || {})}`}
                  className="tool-trace-row"
                  id={`msg-${message.id}-tool-${toolIndex}`}
                >
                  <summary>
                    {running ? (
                      <span className="tool-trace-spinner" aria-hidden="true" />
                    ) : (
                      <span className={`tool-trace-check ${event.status === 'error' ? 'failed' : ''}`} aria-hidden="true">
                        {event.status === 'error' ? '×' : '✓'}
                      </span>
                    )}
                    <span className="tool-trace-name">
                      {running ? `正在调用 ${formatToolName(event.name || '工具')}...` : formatToolName(event.name || '工具')}
                    </span>
                    <small className="tool-trace-summary">
                      {running ? (event.result_preview || '等待结果...') : (event.result_preview || formatToolStatus(event.status))}
                    </small>
                  </summary>
                  <div className="tool-trace-detail">
                    {event.thought ? <p>{event.thought}</p> : null}
                    {event.args && Object.keys(event.args).length ? (
                      <pre>{JSON.stringify(event.args, null, 2)}</pre>
                    ) : null}
                    {event.result_preview ? <small>{event.result_preview}</small> : null}
                    <ToolFileLink event={event} />
                  </div>
                </details>
              )
            })}
          </div>
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

        <div className="message-content" id={isUser ? undefined : `msg-${message.id}-answer`}>
          {answer
            ? renderMarkdownLite(answer)
            : <span className="typing-dot">{pending ? '正在生成...' : '没有收到可显示的回复，请重试或检查模型连接。'}</span>}
          {pending && answer ? <span className="type-caret" /> : null}
        </div>

        {!isUser && !pending && answer ? (
          <div className="message-actions">
            <button type="button" className="message-action-btn" onClick={copyAnswer}>
              <Icon name="copy" size={12} />
              {copyState || '复制'}
            </button>
            {isLast && onRegenerate ? (
              <button type="button" className="message-action-btn" onClick={onRegenerate}>
                <Icon name="refresh" size={12} />
                重新生成
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  )
}

function buildTaskChecklist({ pending, thoughts, toolEvents, answer }) {
  // Codex 风格任务清单：从本轮运行事实推导（理解任务 → 收集上下文 → 工具执行 → 生成回答）
  const hasToolDone = toolEvents.some((event) => event.status === 'ok' || event.status === 'error')
  const hasToolRunning = pending && toolEvents.some((event) => !event.status || event.status === 'running')

  const steps = [
    { key: 'understand', label: '理解任务', done: thoughts.length > 0 },
    { key: 'context', label: '准备上下文', done: thoughts.length > 1 || hasToolDone },
    { key: 'tools', label: toolEvents.length ? `执行工具（${toolEvents.length}）` : '执行工具', done: hasToolDone, active: hasToolRunning, skip: !toolEvents.length && !pending },
    { key: 'answer', label: '生成回答', done: Boolean(answer) && !pending, active: pending && Boolean(answer) },
  ]

  if (!steps.some((step) => step.done || step.active)) return null
  return steps
}

function TaskChecklist({ steps }) {
  const visible = steps.filter((step) => !step.skip)
  const allDone = visible.every((step) => step.done)
  const doneCount = visible.filter((step) => step.done).length

  return (
    <section className={`task-checklist ${pendingClass(allDone)}`} aria-label="任务清单">
      <div className="task-checklist-head">
        <span className={`task-checklist-label ${allDone ? '' : 'shimmer'}`}>
          {allDone ? '任务完成' : '正在执行'}
        </span>
        <small>{doneCount}/{visible.length}</small>
      </div>
      <ol className="task-checklist-body">
        {visible.map((step) => (
          <li key={step.key} className={step.done ? 'done' : (step.active ? 'active' : '')}>
            <span className="task-checklist-mark" aria-hidden="true">
              {step.done ? <Icon name="check" size={10} strokeWidth={2.4} /> : <span className="task-checklist-dot" />}
            </span>
            <span className="task-checklist-text">{step.label}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function pendingClass(allDone) {
  return allDone ? 'done' : 'running'
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
  // 空行打断的列表要合并回同一个列表（助手常在编号项之间留空行）
  let pendingList = null

  const flushList = () => {
    if (!pendingList) return
    const { ordered, items, start, key } = pendingList
    const Tag = ordered ? 'ol' : 'ul'
    blocks.push(
      <Tag key={key} className="markdown-list" start={ordered ? start : undefined}>
        {items.map((item, itemIndex) => <li key={itemIndex}>{renderInlineText(item)}</li>)}
      </Tag>
    )
    pendingList = null
  }

  while (index < lines.length) {
    const rawLine = lines[index]
    const line = rawLine.trimEnd()

    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.trim().startsWith('```')) {
      flushList()
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
      flushList()
      const tableLines = []
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        tableLines.push(lines[index])
        index += 1
      }
      blocks.push(renderTable(tableLines, `table-${index}`))
      continue
    }

    if (line.startsWith('### ')) {
      flushList()
      blocks.push(<h4 key={`h4-${index}`}>{renderInlineText(line.slice(4))}</h4>)
      index += 1
      continue
    }
    if (line.startsWith('## ')) {
      flushList()
      blocks.push(<h3 key={`h3-${index}`}>{renderInlineText(line.slice(3))}</h3>)
      index += 1
      continue
    }
    if (line.startsWith('# ')) {
      flushList()
      blocks.push(<h2 key={`h2-${index}`}>{renderInlineText(line.slice(2))}</h2>)
      index += 1
      continue
    }

    const bulletMatch = /^\s*[-*]\s+/.test(line)
    const numberMatch = /^\s*(\d+)[.)]\s+/.exec(line)
    if (bulletMatch || numberMatch) {
      const ordered = Boolean(numberMatch)
      const item = ordered
        ? line.replace(/^\s*\d+[.)]\s+/, '')
        : line.replace(/^\s*[-*]\s+/, '')
      if (pendingList && pendingList.ordered === ordered) {
        pendingList.items.push(item)
      } else {
        flushList()
        pendingList = {
          ordered,
          items: [item],
          start: ordered ? Number(numberMatch[1]) : undefined,
          key: `${ordered ? 'ol' : 'ul'}-${index}`,
        }
      }
      index += 1
      continue
    }

    flushList()
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

  flushList()
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

function formatToolName(tool) {
  const map = {
    doc_parse: '资料解析',
    web_search: '联网搜索',
    doc_export: '文件导出',
    file_write: '文件写入',
    web_extract: '网页提取',
    terminal: '终端命令',
    process: '进程管理',
    read_terminal: '读取终端',
    read_file: '读取文件',
    write_file: '写入文件',
    patch: '修改文件',
    search_files: '搜索文件',
    vision_analyze: '图像分析',
    image_generate: '图像生成',
    skills_list: '技能列表',
    skill_view: '查看技能',
    skill_manage: '技能管理',
    text_to_speech: '语音合成',
    todo: '任务计划',
    memory: '记忆存取',
    session_search: '会话检索',
  }
  if (map[tool]) return map[tool]
  if (tool?.startsWith('browser_')) {
    const browserMap = {
      navigate: '打开网页',
      snapshot: '读取页面',
      click: '点击',
      type: '输入',
      scroll: '滚动',
      back: '后退',
      press: '按键',
      get_images: '获取图片',
      vision: '看图',
      console: '控制台',
      cdp: '调试协议',
      dialog: '对话框',
    }
    const action = browserMap[tool.slice('browser_'.length)]
    if (action) return `浏览器${action}`
  }
  return tool || '工具'
}

function formatToolStatus(status) {
  if (status === 'ok') return '完成'
  if (status === 'error') return '失败'
  return '执行中'
}
