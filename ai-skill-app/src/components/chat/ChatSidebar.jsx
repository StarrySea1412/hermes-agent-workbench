import { useMemo, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import Icon from '../Icon'
import { getTheme, toggleTheme } from '../../theme'
import { useHermesMonitor } from '../../hooks/useAIConfig'

const DAY_MS = 24 * 60 * 60 * 1000

function groupConversations(conversations, query) {
  const q = query.trim().toLowerCase()
  const matched = q
    ? conversations.filter((item) => {
        const haystack = `${item.title || ''} ${item.last_message?.content || ''}`.toLowerCase()
        return haystack.includes(q)
      })
    : conversations

  const pinned = matched.filter((item) => item.is_pinned)
  const rest = matched.filter((item) => !item.is_pinned)
  const groups = [
    { key: 'today', label: '今天', items: [] },
    { key: 'week', label: '最近 7 天', items: [] },
    { key: 'older', label: '更早', items: [] },
  ]
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)

  for (const item of rest) {
    const ts = Date.parse(item.updated_at || item.created_at || '') || 0
    if (ts >= startOfToday.getTime()) groups[0].items.push(item)
    else if (ts >= startOfToday.getTime() - 7 * DAY_MS) groups[1].items.push(item)
    else groups[2].items.push(item)
  }
  const timed = groups.filter((group) => group.items.length)
  if (pinned.length) {
    timed.unshift({ key: 'pinned', label: '置顶', items: pinned })
  }
  return timed
}

export default function ChatSidebar({
  conversations = [],
  activeId,
  onNewChat,
  onDeleteChat,
  onRenameChat,
  onPinChat,
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
  const [query, setQuery] = useState('')
  const [theme, setThemeState] = useState(getTheme())

  const handleToggleTheme = () => {
    setThemeState(toggleTheme())
  }
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

  const groups = useMemo(
    () => groupConversations(conversations, query),
    [conversations, query]
  )

  const renderConversation = (item) => (
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
        {onPinChat && renamingId == null ? (
          <button
            type="button"
            className={`conversation-action-btn ${item.is_pinned ? 'pinned' : ''}`}
            disabled={String(deletingId || '') === String(item.id)}
            title={item.is_pinned ? '取消置顶' : '置顶'}
            aria-label={item.is_pinned ? `取消置顶 ${item.title}` : `置顶 ${item.title}`}
            onClick={() => onPinChat(item.id, !item.is_pinned)}
          >
            <Icon name="star" size={13} />
          </button>
        ) : null}
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
  )

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

      <div className="history-search">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索会话…"
          aria-label="搜索会话"
        />
        {query ? (
          <button
            type="button"
            className="history-search-clear"
            title="清空搜索"
            onClick={() => setQuery('')}
          >
            <Icon name="x" size={12} />
          </button>
        ) : null}
      </div>

      <div className="history-title">
        {query ? `搜索结果 · ${groups.reduce((sum, g) => sum + g.items.length, 0)}` : '历史会话'}
        {!query && conversations.length ? <span className="history-count">{conversations.length}</span> : null}
      </div>

      <div className="conversation-list">
        {groups.map((group) => (
          <div key={group.key} className="conversation-group">
            {groups.length > 1 ? <div className="conversation-group-title">{group.label}</div> : null}
            {group.items.map(renderConversation)}
          </div>
        ))}

        {!groups.length ? (
          <div className="conversation-empty">
            {query ? `没有匹配「${query}」的会话。` : '直接输入任务，Hermes 会创建会话。'}
          </div>
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
          <button
            type="button"
            className="sidebar-logout-btn"
            title={theme === 'dark' ? '切换浅色' : '切换深色'}
            aria-label="切换深浅色"
            onClick={handleToggleTheme}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={14} />
          </button>
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
