import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Icon from '../Icon'
import MessageBubble from './MessageBubble'

const starters = [
  {
    label: '梳理项目架构',
    prompt: '帮我梳理这个项目的架构，并给出下一步改造建议。',
  },
  {
    label: '总结上传资料',
    prompt: '根据上传资料，总结关键结论、风险点和后续动作。',
  },
  {
    label: '需求变方案',
    prompt: '把这段需求整理成实现方案、接口设计和任务拆分。',
  },
  {
    label: '起草文档',
    prompt: '先给我一版 README 或 PRD 草稿，我来继续补充。',
  },
]

const NODE_PREVIEW_MAX = 42

export function EmptyChatHero({ onStarter, children }) {
  return (
    <div className="chat-hero">
      <div className="chat-hero-inner">
        <span className="chat-hero-mark" aria-hidden="true">
          <Icon name="spark" size={21} strokeWidth={1.8} />
        </span>
        <h1 className="chat-hero-title">今天推进什么？</h1>
        {children}
        <div className="starter-grid compact">
          {starters.map((starter) => (
            <button key={starter.label} type="button" onClick={() => onStarter?.(starter.prompt)}>
              {starter.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function MessageList({ messages = [], pendingMessageId, onRegenerate }) {
  const endRef = useRef(null)
  const listRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  // 有工具调用或回答较多的对话才显示左侧节点刻度轨（Codex 式 tick rail）
  const nodes = useMemo(() => buildTimelineNodes(messages), [messages])
  const showTimeline = nodes.length >= 3

  // 滚动联动：视口上方 1/3 处所在的节点视为当前位置（Codex 式 active 追踪）
  const [activeAnchor, setActiveAnchor] = useState(null)
  useEffect(() => {
    const root = listRef.current
    if (!root || !showTimeline) return undefined
    let raf = 0
    const update = () => {
      raf = 0
      const limit = root.getBoundingClientRect().top + root.clientHeight * 0.35
      let current = null
      for (const node of nodes) {
        const el = document.getElementById(node.anchorId)
        if (el && el.getBoundingClientRect().top <= limit) current = node.anchorId
      }
      setActiveAnchor(current ?? nodes[0]?.anchorId ?? null)
    }
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update)
    }
    root.addEventListener('scroll', onScroll, { passive: true })
    update()
    return () => {
      root.removeEventListener('scroll', onScroll)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [nodes, showTimeline])

  const jumpTo = (node) => {
    const target = document.getElementById(node.anchorId) || document.getElementById(`msg-${node.messageId}`)
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
      const row = target.closest('.message-row') || target
      row.classList.remove('flash')
      // 重新触发高亮动画
      void row.offsetWidth
      row.classList.add('flash')
      setActiveAnchor(node.anchorId)
    }
  }

  // 刻度悬浮提示：portal 到 body 用 fixed 定位，避免被消息列 overflow 裁剪
  const [tickTip, setTickTip] = useState(null)
  const showTickTip = (node, currentTarget) => {
    const rect = currentTarget.getBoundingClientRect()
    const top = Math.min(Math.max(rect.top + rect.height / 2, 90), window.innerHeight - 90)
    setTickTip({ left: rect.right + 10, top, node })
  }
  const hideTickTip = () => setTickTip(null)

  if (!messages.length) {
    return null
  }

  return (
    <div className={`message-list-wrap ${showTimeline ? 'with-timeline' : ''}`}>
      {showTimeline ? (
        <nav className="chat-timeline" aria-label="对话节点">
          {nodes.map((node) => (
            <button
              key={node.anchorId}
              type="button"
              className={`chat-timeline-tick ${node.kind} ${node.failed ? 'failed' : ''} ${activeAnchor === node.anchorId ? 'active' : ''}`}
              aria-label={node.preview}
              aria-current={activeAnchor === node.anchorId ? 'true' : undefined}
              onMouseEnter={(event) => showTickTip(node, event.currentTarget)}
              onMouseLeave={hideTickTip}
              onFocus={(event) => showTickTip(node, event.currentTarget)}
              onBlur={hideTickTip}
              onClick={() => jumpTo(node)}
            />
          ))}
        </nav>
      ) : null}

      <div className="message-list" ref={listRef}>
        {messages.map((message, index) => (
          <MessageBubble
            key={message.id}
            message={message}
            pending={message.id === pendingMessageId}
            isLast={index === messages.length - 1}
            onRegenerate={onRegenerate}
          />
        ))}
        <div ref={endRef} />
      </div>

      {nodes.length >= 2 ? (
        <nav className="chat-timeline-mobile" aria-label="对话节点">
          {nodes.map((node) => (
            <button
              key={`m-${node.anchorId}`}
              type="button"
              className={`chat-timeline-item ${node.kind} ${node.failed ? 'failed' : ''} ${activeAnchor === node.anchorId ? 'active' : ''}`}
              title={node.preview}
              onClick={() => jumpTo(node)}
            >
              <span className="chat-timeline-icon" aria-hidden="true">
                <Icon name={node.icon} size={10} />
              </span>
              <span className="chat-timeline-text">{node.preview}</span>
            </button>
          ))}
        </nav>
      ) : null}

      {tickTip ? (
        createPortal(
          <div
            className={`tick-tip ${tickTip.node.kind} ${tickTip.node.failed ? 'failed' : ''}`}
            style={{ left: tickTip.left, top: tickTip.top }}
            role="tooltip"
          >
            <span className="tick-tip-dot" aria-hidden="true" />
            <div className="tick-tip-body">
              <strong className="tick-tip-kind">{tickTip.node.kindLabel}{tickTip.node.failed ? ' · 失败' : ''}</strong>
              <p className="tick-tip-text">{tickTip.node.detail || tickTip.node.preview}</p>
            </div>
          </div>,
          document.body,
        )
      ) : null}
    </div>
  )
}

function buildTimelineNodes(messages) {
  const nodes = []
  for (const message of messages) {
    if (message.role === 'user') {
      nodes.push({
        messageId: message.id,
        anchorId: `msg-${message.id}`,
        kind: 'user',
        kindLabel: '用户消息',
        icon: 'user',
        preview: truncate(String(message.content || '用户消息'), NODE_PREVIEW_MAX),
        detail: truncate(String(message.content || '用户消息'), 320),
      })
      continue
    }
    const toolEvents = Array.isArray(message.metadata?.tool_events) ? message.metadata.tool_events : []
    toolEvents.forEach((event, toolIndex) => {
      nodes.push({
        messageId: message.id,
        anchorId: `msg-${message.id}-tool-${toolIndex}`,
        kind: 'tool',
        kindLabel: formatToolName(event.name),
        failed: event.status === 'error',
        icon: event.status === 'error' ? 'x' : 'check',
        preview: truncate(`${formatToolName(event.name)}：${event.result_preview || (event.status === 'error' ? '失败' : '完成')}`, NODE_PREVIEW_MAX),
        detail: truncate(String(event.result_preview || '') || (event.status === 'error' ? '执行失败' : '执行完成'), 320),
      })
    })
    const answer = String(message.content || '').trim()
    if (answer) {
      const plain = answer.replace(/[#*`>\-\n]+/g, ' ').trim()
      nodes.push({
        messageId: message.id,
        anchorId: `msg-${message.id}-answer`,
        kind: 'answer',
        kindLabel: '回答',
        icon: 'chat',
        preview: truncate(plain, NODE_PREVIEW_MAX),
        detail: truncate(plain, 400),
      })
    }
  }
  return nodes
}

function truncate(text, max) {
  const clean = text.trim()
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean
}

function formatToolName(tool) {
  const map = {
    doc_parse: '资料解析',
    web_search: '联网搜索',
    doc_export: '文件导出',
    file_write: '文件写入',
  }
  return map[tool] || tool || '工具'
}
