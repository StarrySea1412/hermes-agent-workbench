import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createConversation, listConversations, listProjects } from '../../api/projects'
import ChatSidebar from '../../components/chat/ChatSidebar'
import { useAuth } from '../../hooks/useAuth'
import './ChatShell.css'

export default function Projects() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user, logout, isLocalMode } = useAuth()
  const { data: conversations = [] } = useQuery({ queryKey: ['conversations'], queryFn: listConversations })
  const { data: projects = [], isLoading } = useQuery({ queryKey: ['projects'], queryFn: listProjects })

  const createMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      navigate(`/chat/${conversation.id}`)
    }
  })

  const createWorkspace = () => {
    createMutation.mutate({ title: '新对话', mode: 'chat' })
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

      <main className="projects-main">
        <header className="projects-header">
          <div>
            <p className="eyebrow">资料区</p>
            <h1>工作空间</h1>
            <p>{projects.length} 个可继续复用的项目空间</p>
          </div>
          <button type="button" className="primary-button" onClick={createWorkspace}>新建对话</button>
        </header>

        {isLoading ? (
          <div className="loading-state">正在加载工作空间...</div>
        ) : (
          <div className="project-grid">
            {projects.map((project) => (
              <button
                className="project-card"
                key={project.id}
                type="button"
                onClick={() => navigate(`/projects/${project.id}`)}
              >
                <span>{formatProjectType(project.project_type)}</span>
                <h2>{project.title}</h2>
                <p>{project.description || '还没有描述，打开后可以继续补充目标、材料和交付方向。'}</p>
                <small>{project.outline?.length || 0} 个结构项 / {project.conversation_count || 0} 段对话</small>
              </button>
            ))}
            {!projects.length ? <div className="empty-projects">还没有沉淀下来的工作空间，先开始一段新对话。</div> : null}
          </div>
        )}
      </main>
    </div>
  )
}

function formatProjectType(type) {
  if (type === 'presentation') return '演示导向'
  if (type === 'report') return '文档导向'
  if (type === 'mixed') return '混合交付'
  return '通用工作流'
}
