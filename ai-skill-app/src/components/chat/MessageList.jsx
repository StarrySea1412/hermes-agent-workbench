import { useEffect, useRef } from 'react'
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

export default function MessageList({ messages = [], pendingMessageId, onStarter }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

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
    <div className="message-list">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} pending={message.id === pendingMessageId} />
      ))}
      <div ref={endRef} />
    </div>
  )
}
