import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listConversations } from '../../api/projects'
import ChatSidebar from './ChatSidebar'
import { useAuth } from '../../hooks/useAuth'
import '../../pages/chat/ChatShell.css'

// 内页玻璃框架：非聊天路由共用同一侧栏与极光底，页面切换时框架不再跳变
export default function ChatFrame({ children }) {
  const navigate = useNavigate()
  const { user, logout, isLocalMode } = useAuth()
  const { data: conversations = [] } = useQuery({ queryKey: ['conversations'], queryFn: listConversations })

  return (
    <div className="chat-app">
      <ChatSidebar
        conversations={conversations}
        onNewChat={() => navigate('/')}
        user={user}
        onLogout={logout}
        isLocalMode={isLocalMode}
      />
      {children}
    </div>
  )
}
