import { useEffect, useMemo, useRef, useState } from 'react'
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

export default function MessageList({ messages = [], pendingMessageId, onStarter }) {
  const endRef = useRef(null)
  const listRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  // 有工具调用或回答较多的对话才显示节点导航；用户可手动收起
  const nodes = useMemo(() => buildTimelineNodes(messages), [messages])
  const enoughNodes = nodes.length >= 3
  const [collapsed, setCollapsed] = useState(false)
  const showTimeline = enoughNodes && !collapsed

  const jumpTo = (messageId) => {
    const target = document.getElementById(`msg-${messageId}`)
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
      target.classList.remove('flash')
      // 重新触发高亮动画
      void target.offsetWidth
      target.classList.add('flash')
    }
  }

  if (!messages.length) {
    return (
      <div className="empty-chat">
        <span className="empty-mark" aria-hidden="true">
          <Icon name="spark" size={19} strokeWidth={1.8} />
        </span>
        <h1>今天推进什么？</h1>
        <div className="starter-grid compact">
          {starters.map((starter) => (
            <button key={starter.label} type="button" onClick={() => onStarter?.(starter.prompt)}>
              {starter.label}
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className={`message-list-wrap ${showTimeline ? 'with-timeline' : ''}`}>
      <div className="message-list" ref={listRef}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} pending={message.id === pendingMessageId} />
        ))}
        <div ref={endRef} />
      </div>

      {showTimeline ? (
        <nav className="chat-timeline" aria-label="对话节点">
          <div className="chat-timeline-head">
            <span>对话节点</span>
            <button
              type="button"
              className="chat-timeline-toggle"
              title={collapsed ? '展开节点' : '收起节点'}
              onClick={() => setCollapsed((closed) => !closed)}
            >
              <Icon name="chevron" size={13} />
            </button>
          </div>
          <ul className="chat-timeline-list">
            {nodes.map((node) => (
              <li key={node.messageId}>
                <button
                  type="button"
                  className={`chat-timeline-item ${node.kind}`}
                  title={node.preview}
                  onClick={() => jumpTo(node.messageId)}
                >
                  <span className="chat-timeline-icon" aria-hidden="true">
                    <Icon name={node.icon} size={11} />
                  </span>
                  <span className="chat-timeline-text">{node.preview}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
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
        kind: 'user',
        icon: 'user',
        preview: truncate(String(message.content || '用户消息'), NODE_PREVIEW_MAX),
      })
      continue
    }
    const toolEvents = Array.isArray(message.metadata?.tool_events) ? message.metadata.tool_events : []
    for (const event of toolEvents) {
      nodes.push({
        messageId: message.id,
        kind: 'tool',
        icon: event.status === 'error' ? 'x' : 'check',
        preview: truncate(`${formatToolName(event.name)}：${event.result_preview || (event.status === 'error' ? '失败' : '完成')}`, NODE_PREVIEW_MAX),
      })
    }
    const answer = String(message.content || '').trim()
    if (answer) {
      nodes.push({
        messageId: message.id,
        kind: 'answer',
        icon: 'chat',
        preview: truncate(answer.replace(/[#*`>\-\n]+/g, ' ').trim(), NODE_PREVIEW_MAX),
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
