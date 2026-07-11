import { useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useHermesMonitor } from '../../hooks/useAIConfig'

export default function ChatSidebar({
  conversations = [],
  activeId,
  onNewChat,
  onDeleteChat,
  deletingId,
  user,
  onLogout,
  isLocalMode = false,
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const [historyOpen, setHistoryOpen] = useState(false)
  const { data: hermesMonitor } = useHermesMonitor()
  const hermesOnline = Boolean(
    hermesMonitor?.connected || (hermesMonitor?.tcp_connected && hermesMonitor?.models_connected)
  )
  const hermesStatusText = hermesOnline
    ? (hermesMonitor?.chat_degraded ? '在线，响应较慢' : '在线')
    : '离线'
  const isChatRoute = location.pathname === '/' || location.pathname.startsWith('/chat/')

  return (
    <aside className={`chat-sidebar ${historyOpen ? 'history-open' : ''}`}>
      <div className="sidebar-mobile-row">
        <button type="button" className="brand-block brand-button" onClick={() => navigate('/')}>
          <div className="brand-mark">H</div>
          <div>
            <strong>Hermes</strong>
            <span>Agent 工作台</span>
          </div>
        </button>

        <button
          className="mobile-history-toggle"
          type="button"
          onClick={() => setHistoryOpen((open) => !open)}
        >
          最近 {conversations.length || 0}
        </button>
      </div>

      <button type="button" className="new-chat-btn" onClick={onNewChat}>
        新任务
      </button>

      <nav className="sidebar-nav">
        <NavLink to="/" end className={() => `sidebar-nav-link ${isChatRoute ? 'active' : ''}`}>
          会话
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => `sidebar-nav-link ${isActive ? 'active' : ''}`}>
          运行
        </NavLink>
      </nav>

      <Link className="sidebar-hermes" to="/settings">
        <span className={`sidebar-hermes-dot ${hermesOnline ? 'online' : 'offline'}`} />
        <div>
          <strong>Hermes {hermesStatusText}</strong>
          <small>
            {hermesMonitor?.gateway_url
              ? `${hermesMonitor.host || 'localhost'}:${hermesMonitor.port || '8642'}`
              : '查看 Agent 状态'}
          </small>
        </div>
      </Link>

      <div className="history-title">历史会话</div>
      <div className="conversation-list">
        {conversations.map((item) => (
          <div
            key={item.id}
            className={`conversation-item-shell ${String(activeId) === String(item.id) ? 'active' : ''}`}
          >
            <Link
              className="conversation-item"
              to={`/chat/${item.id}`}
              onClick={() => setHistoryOpen(false)}
            >
              <span>{item.title}</span>
              <small>{item.last_message?.content || '等待第一条消息'}</small>
            </Link>
            {onDeleteChat ? (
              <button
                type="button"
                className="conversation-delete-btn"
                disabled={String(deletingId || '') === String(item.id)}
                title="删除会话"
                aria-label={`删除 ${item.title}`}
                onClick={() => onDeleteChat(item.id)}
              >
                ×
              </button>
            ) : null}
          </div>
        ))}

        {!conversations.length ? (
          <div className="conversation-empty">直接输入任务，Hermes 会创建会话。</div>
        ) : null}
      </div>

      <nav className="sidebar-mini-nav">
        <NavLink to="/projects" className={({ isActive }) => `sidebar-mini-link ${isActive ? 'active' : ''}`}>
          资料
        </NavLink>
        <NavLink to="/agent" className={({ isActive }) => `sidebar-mini-link ${isActive ? 'active' : ''}`}>
          实验
        </NavLink>
        <NavLink to="/skills" className={({ isActive }) => `sidebar-mini-link ${isActive ? 'active' : ''}`}>
          技能
        </NavLink>
      </nav>

      <div className="sidebar-user">
        <div>
          <strong>{user?.display_name || user?.username || '访客'}</strong>
          <span>{isLocalMode ? '本地模式' : user ? '已登录' : '访客模式'}</span>
        </div>
        {onLogout ? (
          <button
            type="button"
            className="sidebar-logout-btn"
            onClick={() => {
              onLogout()
              navigate('/login')
            }}
          >
            退出登录
          </button>
        ) : null}
      </div>
    </aside>
  )
}
