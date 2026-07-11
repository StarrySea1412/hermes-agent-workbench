import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createConversation, listConversations } from '../../api/projects'
import ChatInput from '../../components/chat/ChatInput'
import ChatSidebar from '../../components/chat/ChatSidebar'
import { useAuth } from '../../hooks/useAuth'
import './ChatShell.css'

const starters = [
  '帮我梳理这个项目的架构，并给出下一步改造建议。',
  '根据上传资料，总结关键结论、风险点和后续动作。',
  '把这段需求整理成实现方案、接口设计和任务拆分。',
  '先给我一版 README 或 PRD 草稿，我来继续补充。',
]

const highlights = [
  {
    title: '连续对话',
    description: '不是一次性问答。你可以围绕同一主题持续追问、改写和收敛结果。'
  },
  {
    title: '资料辅助',
    description: '把 PDF、Word 和文本资料拉进当前空间，让回答尽量基于你手上的上下文。'
  },
  {
    title: '结果导出',
    description: '内容成形后，可以继续沉淀结构，并导出 Word 或 Markdown。'
  },
]

export default function ChatHome() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user, logout, isLocalMode } = useAuth()
  const { data: conversations = [] } = useQuery({
    queryKey: ['conversations'],
    queryFn: listConversations
  })

  const createMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      navigate(`/chat/${conversation.id}`)
    }
  })

  const createWorkspace = () => {
    createMutation.mutate({
      title: '新对话',
      mode: 'chat'
    })
  }

  const startChat = (content) => {
    createMutation.mutate({
      title: content.slice(0, 40) || '新对话',
      mode: 'chat',
      description: content
    })
  }

  return (
    <div className="chat-app">
      <ChatSidebar
        conversations={conversations}
        onNewChat={createWorkspace}
        user={user}
        onLogout={logout}
        isLocalMode={isLocalMode}
      />

      <main className="home-stage">
        <div className="home-panel">
          <p className="eyebrow">Hermes Chat</p>
          <h1>直接开始聊天，把问题一路推进到结果</h1>
          <p className="home-summary">
            把目标、上下文和资料交给 Hermes。你可以先聊、再追问、再改写，逐步把结论、
            方案、草稿和交付内容沉淀出来，而不是停在一句回答里。
          </p>

          <div className="home-highlights">
            {highlights.map((item) => (
              <div key={item.title} className="home-highlight">
                <strong>{item.title}</strong>
                <p>{item.description}</p>
              </div>
            ))}
          </div>

          <div className="starter-grid">
            {starters.map((starter) => (
              <button key={starter} type="button" onClick={() => startChat(starter)}>
                {starter}
              </button>
            ))}
          </div>
        </div>

        <div className="home-input">
          <ChatInput disabled={createMutation.isPending} onSend={startChat} />
        </div>
      </main>
    </div>
  )
}
