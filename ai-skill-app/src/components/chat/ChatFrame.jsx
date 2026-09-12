import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { deleteConversation, listConversations, renameConversation, updateConversation } from '../../api/projects'
import ChatSidebar from './ChatSidebar'
import { useAuth } from '../../hooks/useAuth'
import '../../pages/chat/ChatShell.css'

// 内页玻璃框架：非聊天路由共用同一侧栏与极光底，页面切换时框架不再跳变；
// 会话的置顶/重命名/删除在所有内页侧栏同样可用
export default function ChatFrame({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const { user, logout, isLocalMode } = useAuth()
  const { data: conversations = [] } = useQuery({ queryKey: ['conversations'], queryFn: listConversations })

  const deleteMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: (_, deletedId) => {
      queryClient.removeQueries({ queryKey: ['conversation', String(deletedId)] })
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (location.pathname === `/chat/${deletedId}`) navigate('/', { replace: true })
    },
  })

  const renameMutation = useMutation({
    mutationFn: ({ conversationId, title }) => renameConversation(conversationId, title),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  })

  const pinMutation = useMutation({
    mutationFn: ({ conversationId, isPinned }) => updateConversation(conversationId, { is_pinned: isPinned }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  })

  const handleDeleteChat = (conversationId) => {
    if (deleteMutation.isPending) return
    const target = conversations.find((item) => String(item.id) === String(conversationId))
    if (!window.confirm(`确定删除「${target?.title || '这个会话'}」吗？`)) return
    deleteMutation.mutate(conversationId)
  }

  const handleRenameChat = (conversationId, title) => {
    const trimmed = String(title || '').trim()
    if (!trimmed || renameMutation.isPending) return
    renameMutation.mutate({ conversationId, title: trimmed })
  }

  const handlePinChat = (conversationId, isPinned) => {
    pinMutation.mutate({ conversationId, isPinned })
  }

  return (
    <div className="chat-app app-frame">
      <ChatSidebar
        conversations={conversations}
        deletingId={deleteMutation.variables}
        onNewChat={() => navigate('/')}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
        onPinChat={handlePinChat}
        user={user}
        onLogout={logout}
        isLocalMode={isLocalMode}
      />
      {children}
    </div>
  )
}
