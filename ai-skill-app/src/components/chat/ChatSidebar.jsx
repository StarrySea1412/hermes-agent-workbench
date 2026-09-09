import { useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import { useHermesMonitor } from '../../hooks/useAIConfig'

export default function ChatSidebar({
  conversations = [],
  activeId,
  onNewChat,
  onDeleteChat,
  onRenameChat,
  deletingId,
  user,
  onLogout,
  isLocalMode = false,
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const { data: hermesMonitor } = useHermesMonitor()
  const hermesOnline = Boolean(
    hermesMonitor?.connected || (hermesMonitor?.tcp_connected && hermesMonitor?.models_connected)
  )
  const hermesStatusText = hermesOnline
    ? (hermesMonitor?.chat_degraded ? '在线 · 响应较慢' : '在线')
    : '离线'
  const isChatRoute = location.pathname === '/' || location.pathname.startsWith('/chat/')

  const startRename = (item) => {
    setRenamingId(item.id)
    setRenameValue(item.title || '')
  }

  const commitRename = () => {
    if (renamingId != null && renameValue.trim()) {
      onRenameChat?.(renamingId, renameValue)
    }
    setRenamingId(null)
    setRenameValue('')
  }

  return (
    <aside className={`chat-sidebar ${historyOpen ? 'history-open' : ''}`}>
      <div className="sidebar-mobile-row">
        <button type="button" className="brand-block brand-button" onClick={() => navigate('/')}>
          <span className="brand-mark" aria-hidden="true">
            <Icon name="spark" size={15} strokeWidth={1.9} />
          </span>
          <span className="brand-text">
            <strong>Hermes</strong>
            <span>Agent 工作台</span>
          </span>
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
        <Icon name="plus" size={14} strokeWidth={2} />
        新任务
      </button>

      <nav className="sidebar-nav">
        <NavLink to="/" end className={() => `sidebar-nav-link ${isChatRoute ? 'active' : ''}`}>
          <Icon name="chat" size={15} />
          会话
        </NavLink>
        <NavLink to="/files" className={({ isActive }) => `sidebar-nav-link ${isActive ? 'active' : ''}`}>
          <Icon name="folder" size={15} />
          资料
        </NavLink>
        <NavLink to="/runs" className={({ isActive }) => `sidebar-nav-link ${isActive ? 'active' : ''}`}>
          <Icon name="task" size={15} />
          任务
        </NavLink>
        <NavLink to="/skills" className={({ isActive }) => `sidebar-nav-link ${isActive ? 'active' : ''}`}>
          <Icon name="book" size={15} />
          技能
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => `sidebar-nav-link ${isActive ? 'active' : ''}`}>
          <Icon name="gear" size={15} />
          设置
        </NavLink>
      </nav>

      <div className="history-title">
        历史会话
        {conversations.length ? <span className="history-count">{conversations.length}</span> : null}
      </div>

      <div className="conversation-list">
        {conversations.map((item) => (
          <div
            key={item.id}
            className={`conversation-item-shell ${String(activeId) === String(item.id) ? 'active' : ''}`}
          >
            {renamingId != null && String(renamingId) === String(item.id) ? (
              <form
                className="conversation-rename"
                onSubmit={(event) => {
                  event.preventDefault()
                  commitRename()
                }}
              >
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(event) => setRenameValue(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') setRenamingId(null)
                  }}
                  onBlur={commitRename}
                  aria-label="会话名称"
                />
              </form>
            ) : (
              <Link
                className="conversation-item"
                to={`/chat/${item.id}`}
                onClick={() => setHistoryOpen(false)}
              >
                <span>{item.title}</span>
                <small>{item.last_message?.content || '等待第一条消息'}</small>
              </Link>
            )}
            <div className="conversation-item-actions">
              {onRenameChat && renamingId == null ? (
                <button
                  type="button"
                  className="conversation-action-btn"
                  disabled={String(deletingId || '') === String(item.id)}
                  title="重命名"
                  aria-label={`重命名 ${item.title}`}
                  onClick={() => startRename(item)}
                >
                  <Icon name="rename" size={13} />
                </button>
              ) : null}
              {onDeleteChat ? (
                <button
                  type="button"
                  className="conversation-action-btn danger"
                  disabled={String(deletingId || '') === String(item.id)}
                  title="删除会话"
                  aria-label={`删除 ${item.title}`}
                  onClick={() => onDeleteChat(item.id)}
                >
                  <Icon name="trash" size={13} />
                </button>
              ) : null}
            </div>
          </div>
        ))}

        {!conversations.length ? (
          <div className="conversation-empty">直接输入任务，Hermes 会创建会话。</div>
        ) : null}
      </div>

      <div className="sidebar-footer">
        <Link className="sidebar-hermes" to="/settings" title="查看 Agent 状态">
          <span className={`sidebar-hermes-dot ${hermesOnline ? 'online' : 'offline'}`} />
          <span className="sidebar-hermes-text">
            <strong>Hermes {hermesStatusText}</strong>
            <small>
              {hermesMonitor?.gateway_url
                ? `${hermesMonitor.host || 'localhost'}:${hermesMonitor.port || '8642'}`
                : '查看 Agent 状态'}
            </small>
          </span>
        </Link>

        <div className="sidebar-user">
          <span className="sidebar-user-avatar" aria-hidden="true">
            <Icon name="user" size={13} />
          </span>
          <span className="sidebar-user-text">
            <strong>{user?.display_name || user?.username || '访客'}</strong>
            <small>{isLocalMode ? '本地模式' : user ? '已登录' : '访客模式'}</small>
          </span>
          {onLogout ? (
            <button
              type="button"
              className="sidebar-logout-btn"
              title="退出登录"
              aria-label="退出登录"
              onClick={() => {
                onLogout()
                navigate('/login')
              }}
            >
              <Icon name="logout" size={14} />
            </button>
          ) : null}
        </div>
      </div>
    </aside>
  )
}
