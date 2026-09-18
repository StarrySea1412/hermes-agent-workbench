import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  decideToolExecution, listToolExecutions, listWorkspaceWrites,
  rollbackWorkspaceWrite, toolExecutionsKey, workspaceWritesKey,
} from '../../api/toolExecutions'

const STATUS_LABELS = {
  pending: '等待审批',
  approved: '已批准 · 等待执行',
  running: '执行中',
  succeeded: '执行成功',
  failed: '执行失败',
  denied: '已拒绝',
  expired: '已过期',
  cancelled: '已取消',
}

const WRITE_STATUS_LABELS = {
  applied: '已应用 · 可回滚',
  rejected: '应用失败',
  rolled_back: '已回滚',
}

function formatTime(value) {
  if (!value) return '未提供'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

function plainText(value) {
  if (typeof value === 'string') return value
  return value == null ? '' : JSON.stringify(value, null, 2)
}

export default function ToolApprovalPanel({ conversationId }) {
  const queryClient = useQueryClient()
  const queryKey = toolExecutionsKey(conversationId)
  const writesKey = workspaceWritesKey(conversationId)
  const { data: records = [], error, isPending, isFetching, refetch } = useQuery({
    queryKey,
    queryFn: ({ signal }) => listToolExecutions(conversationId, { signal }),
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
    staleTime: 0,
    retry: false,
  })
  const { data: writes = [], error: writesError } = useQuery({
    queryKey: writesKey,
    queryFn: ({ signal }) => listWorkspaceWrites(conversationId, { signal }),
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
    staleTime: 0,
    retry: false,
  })
  // This component is keyed by conversationId in ChatView: no local decision state crosses chats.
  const locks = useRef(new Set())
  const [decisions, setDecisions] = useState({})
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const decide = async (record, decision) => {
    // now 由每秒定时器驱动；过期记录直接刷新，让服务端状态生效
    const deadline = record.expires_at ? Date.parse(record.expires_at) : NaN
    if (Number.isFinite(deadline) && deadline <= now) {
      void refetch()
      return
    }
    if (locks.current.has(record.id) || record.status !== 'pending') return
    locks.current.add(record.id)
    setDecisions((current) => ({ ...current, [record.id]: { busy: true } }))
    try {
      const updated = await decideToolExecution(record.id, decision)
      // Cancel a pre-decision poll so it cannot restore stale pending buttons.
      await queryClient.cancelQueries({ queryKey })
      if (updated?.id === record.id && String(updated.conversation_id) === String(conversationId)) {
        queryClient.setQueryData(queryKey, (current = []) => current.map((item) => item.id === record.id ? updated : item))
      }
      setDecisions((current) => ({ ...current, [record.id]: { submitted: true } }))
    } catch (requestError) {
      const text = requestError.payload?.message || requestError.payload?.detail
        || requestError.payload?.error || requestError.message || '审批提交失败，请重试。'
      setDecisions((current) => ({ ...current, [record.id]: { error: text } }))
    } finally {
      // On conflict/expiry, fetch authoritative status as well as showing the request error.
      await queryClient.invalidateQueries({ queryKey })
      locks.current.delete(record.id)
    }
  }
  const sorted = [...records].sort((a, b) => {
    if ((a.status === 'pending') !== (b.status === 'pending')) return a.status === 'pending' ? -1 : 1
    return String(b.created_at).localeCompare(String(a.created_at))
  })
  const pendingCount = records.filter((record) => record.status === 'pending').length
  const writeLocks = useRef(new Set())
  const [writeBusy, setWriteBusy] = useState({})
  const rollback = async (write) => {
    if (writeLocks.current.has(write.id) || write.status !== 'applied') return
    writeLocks.current.add(write.id)
    setWriteBusy((current) => ({ ...current, [write.id]: true }))
    try {
      await rollbackWorkspaceWrite(write.id)
    } catch (requestError) {
      const text = requestError.payload?.message || requestError.payload?.detail
        || requestError.message || '回滚失败，请重试。'
      setWriteBusy((current) => ({ ...current, [write.id]: text }))
    } finally {
      await queryClient.invalidateQueries({ queryKey: writesKey })
      writeLocks.current.delete(write.id)
    }
  }

  // 无记录且无写入时弱化为占位一行，不再占据整块卡片
  const idle = !isPending && !error && !records.length && !writes.length && !writesError

  return (
    <section className={`tool-approval-panel ${idle ? 'idle' : ''}`} aria-label="当前会话工具审批" tabIndex={0}>
      <div className="tool-approval-heading">
        <strong>工具审批 <span role="status">{pendingCount ? `· ${pendingCount} 项待处理` : '· 无待审批'}</span></strong>
        {idle ? null : (
          <button type="button" className="ghost-button" disabled={isFetching} onClick={() => refetch()} aria-label="刷新工具审批记录">
            {isFetching ? '同步中…' : '刷新'}
          </button>
        )}
      </div>
      {error ? <p className="tool-approval-error" role="alert">无法同步审批记录：{error.message}。请刷新重试，当前状态可能已变化。</p> : null}
      {isPending && !error ? <p role="status">正在加载审批记录…</p> : null}
      {!isPending && !error && !records.length ? <p className="tool-approval-empty">暂无工具执行记录；新的审批会显示在这里。</p> : null}
      {writes.length || writesError ? (
        <div className="tool-approval-writes">
          <strong>文件写入记录</strong>
          {writesError ? <p className="tool-approval-error" role="alert">无法同步写入记录：{writesError.message}</p> : null}
          {writes.map((write) => {
            const busyState = writeBusy[write.id]
            const busy = busyState === true
            return (
              <article key={write.id} className="tool-approval-card" aria-label={`文件写入 ${write.path}`}>
                <div className="tool-approval-heading">
                  <h3>{write.path}</h3>
                  <span className={`tool-approval-status status-${write.status}`} role="status">
                    {WRITE_STATUS_LABELS[write.status] || `未知状态：${write.status}`}
                  </span>
                </div>
                <details>
                  <summary>查看改动差异（仅展示文本）</summary>
                  <pre tabIndex={0} aria-label={`${write.path} 的差异`}><code>{write.diff || '（无差异）'}</code></pre>
                </details>
                {write.error ? <p className="tool-approval-error">{write.error}</p> : null}
                {write.status === 'applied' ? (
                  <div className="tool-approval-actions">
                    <button type="button" className="ghost-button" disabled={busy} onClick={() => rollback(write)}>
                      回滚到改动前
                    </button>
                    <span role="status">{busy ? '正在回滚…' : typeof busyState === 'string' ? busyState : '回滚会恢复改动前的文件内容。'}</span>
                  </div>
                ) : null}
              </article>
            )
          })}
        </div>
      ) : null}
      {sorted.map((record) => {
        const state = decisions[record.id] || {}
        const deadline = record.expires_at ? Date.parse(record.expires_at) : NaN
        const elapsed = Number.isFinite(deadline) && deadline <= now
        const disabled = state.busy || state.submitted || elapsed || Boolean(error)
        return (
          <article key={record.id} className="tool-approval-card" aria-labelledby={`tool-approval-${record.id}`} aria-busy={Boolean(state.busy)}>
            <div className="tool-approval-heading">
              <h3 id={`tool-approval-${record.id}`}>{record.tool_name || '未命名工具'}</h3>
              <span className={`tool-approval-status status-${record.status}`} role="status">{STATUS_LABELS[record.status] || `未知状态：${record.status}`}</span>
            </div>
            <div className="tool-approval-times">
              <span>创建：<time dateTime={record.created_at}>{formatTime(record.created_at)}</time></span>
              <span>到期：<time dateTime={record.expires_at || undefined}>{formatTime(record.expires_at)}</time></span>
            </div>
            <details open={record.status === 'pending'}>
              <summary>查看代码 / 参数（仅展示文本）</summary>
              <pre tabIndex={0} aria-label={`${record.tool_name || '工具'}的代码和参数`}><code>{plainText(record.arguments) || '（无参数）'}</code></pre>
            </details>
            {record.error ? <p className="tool-approval-error">{plainText(record.error)}</p> : null}
            {state.error ? <p className="tool-approval-error" role="alert">审批提交失败：{state.error}</p> : null}
            {record.status === 'pending' ? (
              <div className="tool-approval-actions">
                <button type="button" className="ghost-button" disabled={disabled} onClick={() => decide(record, 'allow')}>允许本次</button>
                <button type="button" className="ghost-button" disabled={disabled} onClick={() => decide(record, 'deny')}>拒绝本次</button>
                <span role="status">{state.busy ? '正在提交…' : state.submitted ? '决定已提交，等待状态同步' : elapsed ? '已到截止时间，等待服务端确认' : '请先检查代码；批准不代表执行成功。'}</span>
              </div>
            ) : null}
          </article>
        )
      })}
    </section>
  )
}
