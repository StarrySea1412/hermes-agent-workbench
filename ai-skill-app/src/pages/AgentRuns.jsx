import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listAgentMemories, listAgentRuns, listAgentTemplates } from '../api/agents'
import { listFiles } from '../api/files'
import RunComposer from '../components/workbench/RunComposer'
import RunStatusBadge from '../components/workbench/RunStatusBadge'
import Sidebar from '../components/workbench/Sidebar'
import { useAuth } from '../hooks/useAuth'

const RUN_FILTERS = [
  { value: 'all', label: '全部' },
  { value: 'running', label: '运行中' },
  { value: 'done', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]

export default function AgentRuns() {
  const navigate = useNavigate()
  const { user, logout, isLocalMode } = useAuth()
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: templates = [] } = useQuery({ queryKey: ['agentTemplates'], queryFn: listAgentTemplates })
  const { data: memories = [] } = useQuery({ queryKey: ['agentMemories'], queryFn: () => listAgentMemories() })
  const { data: files = [] } = useQuery({ queryKey: ['files'], queryFn: listFiles })
  const [statusFilter, setStatusFilter] = useState('all')
  const [query, setQuery] = useState('')

  const runStats = useMemo(() => {
    const stats = { all: runs.length, running: 0, done: 0, failed: 0, cancelled: 0 }
    runs.forEach((run) => {
      if (run.status === 'pending' || run.status === 'running') {
        stats.running += 1
      } else if (Object.prototype.hasOwnProperty.call(stats, run.status)) {
        stats[run.status] += 1
      }
    })
    return stats
  }, [runs])
  const filteredRuns = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return runs.filter((run) => {
      const statusMatched = statusFilter === 'all'
        || (statusFilter === 'running' && ['pending', 'running'].includes(run.status))
        || run.status === statusFilter
      if (!statusMatched) return false
      if (!keyword) return true
      return [
        run.task,
        run.agent?.name,
        run.status,
        run.answer_preview,
        run.error,
        run.session_id,
      ].some((value) => String(value || '').toLowerCase().includes(keyword))
    })
  }, [query, runs, statusFilter])
  const latestRun = runs[0]

  return (
    <div className="workbench-shell">
      <Sidebar runs={runs} user={user} onLogout={logout} isLocalMode={isLocalMode} />

      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">运行</p>
            <h1>执行历史</h1>
            <p>每一次运行都会保存任务内容、步骤轨迹、工具使用记录和最终回答，方便后续回看。</p>
          </div>
          <div className="header-actions">
            <button type="button" className="secondary-button" onClick={() => navigate('/')}>
              回到聊天
            </button>
            <button type="button" className="primary-button" onClick={() => navigate('/agent')}>
              工作台总览
            </button>
          </div>
        </header>

        <section className="metric-grid">
          <MetricCard label="全部运行" value={String(runStats.all)} helper={latestRun ? `最近更新：${formatShortDate(latestRun.updated_at)}` : '暂无运行记录。'} />
          <MetricCard label="运行中" value={String(runStats.running)} helper="包含 pending 和 running 状态。" />
          <MetricCard label="已完成" value={String(runStats.done)} helper="可以查看回答、产物和记忆保存入口。" />
          <MetricCard label="失败" value={String(runStats.failed)} helper="优先进入详情查看错误和工具轨迹。" />
        </section>

        <div className="content-grid two-column">
          <section className="panel">
            <RunComposer
              templates={templates}
              memories={memories}
              files={files}
              compact
              onCreated={(run) => navigate(`/runs/${run.id}`)}
            />
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">模板</p>
                <h2>可用的智能体定义</h2>
              </div>
            </div>
            <div className="template-list">
              {templates.map((template) => (
                <article key={template.id} className="template-card">
                <div className="template-card-top">
                  <strong>{template.name}</strong>
                  <small>{template.default_max_steps} 步</small>
                </div>
                <p>{template.system_prompt || '未配置额外提示词。'}</p>
                <code>{template.allowed_tools?.length ? template.allowed_tools.join(', ') : '全部工具'}</code>
              </article>
            ))}
            </div>
          </section>
        </div>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">全部运行</p>
              <h2>{filteredRuns.length} / {runs.length} 条运行记录</h2>
            </div>
          </div>

          <div className="run-list-controls">
            <label className="field run-search">
              <span>搜索运行</span>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索任务、模板、会话、错误或回答片段"
              />
            </label>
            <div className="run-status-filters" aria-label="运行状态筛选">
              {RUN_FILTERS.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  className={`run-filter-chip ${statusFilter === filter.value ? 'active' : ''}`}
                  onClick={() => setStatusFilter(filter.value)}
                >
                  <span>{filter.label}</span>
                  <strong>{runStats[filter.value] ?? 0}</strong>
                </button>
              ))}
            </div>
          </div>

          <div className="runs-table">
            {filteredRuns.map((run) => (
              <button
                key={run.id}
                type="button"
                className="runs-row"
                onClick={() => navigate(`/runs/${run.id}`)}
              >
                <div className="runs-row-main">
                  <strong>{run.task}</strong>
                  <small>
                    {run.agent?.name || '默认运行时'} · {formatShortDate(run.updated_at)}
                    {run.session_id ? ` · ${run.session_id}` : ''}
                  </small>
                  {run.answer_preview || run.error ? (
                    <p>{truncate(run.error || run.answer_preview, 140)}</p>
                  ) : null}
                </div>
                <div className="runs-row-meta">
                  <small>{run.step_count} 步</small>
                  <RunStatusBadge status={run.status} />
                </div>
              </button>
            ))}
            {!runs.length ? <div className="empty-inline">还没有运行记录。</div> : null}
            {runs.length && !filteredRuns.length ? <div className="empty-inline">没有匹配当前筛选条件的运行记录。</div> : null}
          </div>
        </section>
      </main>
    </div>
  )
}

function MetricCard({ label, value, helper }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{helper}</small>
    </article>
  )
}

function formatShortDate(value) {
  if (!value) return '暂无'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function truncate(value, maxLength) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text
}
