import { NavLink, useNavigate } from 'react-router-dom'
import RunStatusBadge from './RunStatusBadge'
import { useHermesMonitor } from '../../hooks/useAIConfig'
import { ENABLE_LEGACY_BIDS } from '../../config/features'

export default function Sidebar({ runs = [], user, onLogout, isLocalMode = false }) {
  const navigate = useNavigate()
  const { data: hermesMonitor } = useHermesMonitor()
  const recentRuns = runs.slice(0, 6)
  const hermesOnline = Boolean(hermesMonitor?.connected)

  return (
    <aside className="workbench-sidebar">
      <button type="button" className="sidebar-brand" onClick={() => navigate('/')}>
        <div className="brand-badge">H</div>
        <div>
          <strong>Hermes 工作台</strong>
          <span>聊天、资料、工具与产物</span>
        </div>
      </button>

      <button type="button" className="primary-button sidebar-launch" onClick={() => navigate('/')}>
        开始对话
      </button>

      <nav className="sidebar-nav">
        <NavLink to="/" end className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          聊天
        </NavLink>
        <NavLink to="/files" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          资料
        </NavLink>
        <NavLink to="/runs" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          任务历史
        </NavLink>
        <NavLink to="/skills" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          技能
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          设置
        </NavLink>
        <NavLink to="/agent" end className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          总览
        </NavLink>
        <NavLink to="/templates" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          模板
        </NavLink>
        <NavLink to="/tools" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          工具
        </NavLink>
        <NavLink to="/memories" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
          记忆
        </NavLink>
        {ENABLE_LEGACY_BIDS ? (
          <NavLink to="/workflows" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            工作流（旧）
          </NavLink>
        ) : null}
      </nav>

      <section className="sidebar-panel">
        <div className="sidebar-panel-header">
          <span>Hermes</span>
          <RunStatusBadge status={hermesOnline ? 'done' : 'failed'} />
        </div>
        <small>
          {hermesMonitor?.gateway_url
            ? `${hermesMonitor.host || 'localhost'}:${hermesMonitor.port || '8642'}`
            : '可在设置页查看网关状态。'}
        </small>
      </section>

      <section className="sidebar-panel">
        <div className="sidebar-panel-header">
          <span>最近运行</span>
          <small>{runs.length}</small>
        </div>
        <div className="sidebar-run-list">
          {recentRuns.map((run) => (
            <NavLink key={run.id} to={`/runs/${run.id}`} className="sidebar-run-link">
              <div>
                <strong>{truncate(run.task, 54)}</strong>
                <small>{run.agent?.name || '默认运行时'}</small>
              </div>
              <RunStatusBadge status={run.status} />
            </NavLink>
          ))}
          {!recentRuns.length ? <p className="sidebar-empty">还没有运行记录。</p> : null}
        </div>
      </section>

      <div className="sidebar-account">
        <div>
          <strong>{user?.display_name || user?.username || '访客'}</strong>
          <span>{isLocalMode ? '本地模式' : user ? '已登录' : '访客模式'}</span>
        </div>
        {onLogout ? (
          <button
            type="button"
            className="secondary-button"
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

function truncate(value, maxLength) {
  const text = String(value || '')
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text
}
