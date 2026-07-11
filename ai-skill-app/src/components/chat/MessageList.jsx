import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'

const starters = [
  {
    label: '改造成 Hermes 工作台',
    prompt: '把这个项目改成 Hermes 风格的 agent 工程师工作台：聊天优先、工具可见、记忆可追踪、操作尽量少。',
  },
  {
    label: '诊断操作复杂度',
    prompt: '分析当前产品哪里操作复杂，按用户路径给出改造清单，并优先处理聊天入口。',
  },
  {
    label: '读取资料生成路线',
    prompt: '读取我上传的资料，提炼目标、约束、风险和下一步执行路线。',
  },
  {
    label: '整理开源项目文档',
    prompt: '生成适合 agent 开发工程师开源项目的 README、路线图和贡献指南。',
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
        <div className="empty-mark">H</div>
        <p className="eyebrow">Hermes Session</p>
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
