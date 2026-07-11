import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { cancelAgentRun, executeAgentRunStream, getAgentRun, getAgentRunArtifacts, getAgentRunMemories, listAgentRuns, saveRunAsMemory } from '../api/agents'
import { resolveFileUrl } from '../api/files'
import ArtifactList from '../components/workbench/ArtifactList'
import MemoryList from '../components/workbench/MemoryList'
import RunStatusBadge from '../components/workbench/RunStatusBadge'
import Sidebar from '../components/workbench/Sidebar'
import RunTimeline from '../components/workbench/RunTimeline'
import { useAuth } from '../hooks/useAuth'

export default function AgentRunDetail() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const streamStartedRef = useRef(false)
  const streamControllerRef = useRef(null)
  const { user, logout, isLocalMode } = useAuth()
  const [liveSteps, setLiveSteps] = useState([])
  const [liveRun, setLiveRun] = useState(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamError, setStreamError] = useState('')
  const [memoryNotice, setMemoryNotice] = useState('')

  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const runQuery = useQuery({
    queryKey: ['agentRun', runId],
    queryFn: () => getAgentRun(runId),
    enabled: Boolean(runId),
    retry: false,
  })
  const memoriesQuery = useQuery({
    queryKey: ['agentRunMemories', runId],
    queryFn: () => getAgentRunMemories(runId),
    enabled: Boolean(runId),
    retry: false,
  })
  const saveMemoryMutation = useMutation({
    mutationFn: (payload) => saveRunAsMemory(runId, payload),
    onSuccess: () => {
      setMemoryNotice('已保存到记忆。')
      queryClient.invalidateQueries({ queryKey: ['agentMemories'] })
      queryClient.invalidateQueries({ queryKey: ['agentRunMemories', runId] })
      queryClient.invalidateQueries({ queryKey: ['agentRun', runId] })
    },
    onError: (error) => {
      setMemoryNotice(error.message || '无法将这条回答保存为记忆。')
    },
  })
  const cancelMutation = useMutation({
    mutationFn: () => cancelAgentRun(runId),
    onSuccess: (detail) => {
      streamControllerRef.current?.abort()
      setLiveRun(detail)
      setLiveSteps([])
      setIsStreaming(false)
      setStreamError('')
      queryClient.invalidateQueries({ queryKey: ['agentRuns'] })
      queryClient.invalidateQueries({ queryKey: ['agentRun', runId] })
      queryClient.invalidateQueries({ queryKey: ['agentRunArtifacts', runId] })
      queryClient.invalidateQueries({ queryKey: ['agentRunMemories', runId] })
    },
    onError: (error) => {
      setStreamError(error.message || '无法取消运行。')
    },
  })
  const artifactsQuery = useQuery({
    queryKey: ['agentRunArtifacts', runId],
    queryFn: () => getAgentRunArtifacts(runId),
    enabled: Boolean(runId),
    retry: false,
  })

  const run = liveRun || runQuery.data
  const attachedFiles = run?.files || []
  const missingFileIds = (run?.file_ids || []).filter((fileId) => !attachedFiles.some((file) => file.id === fileId))
  const mergedSteps = useMemo(() => mergeSteps(runQuery.data?.steps || [], liveSteps, liveRun?.steps || []), [
    liveRun?.steps,
    liveSteps,
    runQuery.data?.steps,
  ])

  useEffect(() => {
    if (!runId || !runQuery.data || streamStartedRef.current) return undefined
    if (runQuery.data.status !== 'pending') return undefined

    streamStartedRef.current = true
    const controller = new AbortController()
    streamControllerRef.current = controller

    queueMicrotask(() => {
      if (controller.signal.aborted) return
      setIsStreaming(true)
      setStreamError('')
    })

    executeAgentRunStream(
      runId,
      {
        onRun: (snapshot) => {
          setLiveRun((current) => ({ ...(current || runQuery.data), ...snapshot }))
        },
        onStep: (step) => {
          setLiveSteps((current) => mergeSteps(current, [step]))
        },
        onComplete: (detail) => {
          setLiveRun(detail)
          setLiveSteps([])
          setIsStreaming(false)
          queryClient.invalidateQueries({ queryKey: ['agentRuns'] })
          queryClient.invalidateQueries({ queryKey: ['agentRun', runId] })
          queryClient.invalidateQueries({ queryKey: ['agentRunArtifacts', runId] })
        },
        onError: (message) => {
          setStreamError(message)
          setIsStreaming(false)
        }
      },
      controller.signal
    ).catch((error) => {
      if (controller.signal.aborted) return
      setStreamError(error.message || '流式执行失败。')
      setIsStreaming(false)
    })

    return () => {
      streamControllerRef.current = null
      controller.abort()
    }
  }, [queryClient, runId, runQuery.data])

  const canCancel = run?.status === 'pending' || run?.status === 'running'

  return (
    <div className="workbench-shell">
      <Sidebar runs={runs} user={user} onLogout={logout} isLocalMode={isLocalMode} />

      <main className="page">
        <header className="page-header">
          <div>
            <button type="button" className="back-link" onClick={() => navigate('/runs')}>返回运行列表</button>
            <p className="eyebrow">运行详情</p>
            <h1>{run?.task || '智能体运行'}</h1>
            <p>在一个页面中查看时间线、选中的模板、工具活动、最终回答以及派生产物。</p>
          </div>
          <div className="header-actions">
            {canCancel ? (
              <button
                type="button"
                className="secondary-button danger-button"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
              >
                {cancelMutation.isPending ? '取消中...' : '取消运行'}
              </button>
            ) : null}
            {run ? <RunStatusBadge status={run.status} /> : null}
          </div>
        </header>

        {runQuery.isLoading ? <div className="panel loading-panel">正在加载运行详情...</div> : null}

        {run ? (
          <div className="content-grid detail-grid">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">时间线</p>
                  <h2>执行轨迹</h2>
                </div>
              </div>
              {streamError ? <div className="panel-alert error">{streamError}</div> : null}
              <RunTimeline steps={mergedSteps} isStreaming={isStreaming} />
            </section>

            <aside className="detail-rail">
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">元信息</p>
                    <h2>运行元数据</h2>
                  </div>
                </div>
                <div className="stack-list">
                  <InfoRow label="模板" value={run.agent?.name || '默认运行时'} />
                  <InfoRow label="会话" value={run.session_id || '未分配'} />
                  <InfoRow label="已使用工具" value={run.tools_used?.length ? run.tools_used.join(', ') : '暂无'} />
                  <InfoRow label="附加文件" value={attachedFiles.length ? String(attachedFiles.length) : '无'} />
                  <InfoRow label="步骤数" value={String(run.step_count || mergedSteps.length || 0)} />
                  <InfoRow label="更新时间" value={formatDate(run.updated_at)} />
                </div>
              </section>

              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">文件</p>
                    <h2>附加参考资料</h2>
                  </div>
                </div>
                {attachedFiles.length ? (
                  <div className="file-inline-list">
                    {attachedFiles.map((file) => (
                      <article key={file.id} className="file-card">
                        <div className="file-card-top">
                          <div>
                            <strong>{file.original_name}</strong>
                            <small>{formatFileMeta(file)}</small>
                          </div>
                        </div>
                        <p>{file.description || '作为本次运行的参考资料附加。'}</p>
                        <div className="file-card-footer">
                          <span>{formatDate(file.created_at)}</span>
                          {file.file_url ? (
                            <a
                              className="artifact-link"
                              href={resolveFileUrl(file.file_url)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              打开文件
                            </a>
                          ) : null}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-panel">
                    <strong>没有附加文件。</strong>
                    <p>可以从运行编排器或文件页添加参考资料。</p>
                  </div>
                )}
                {missingFileIds.length ? (
                  <div className="panel-alert">以下文件 ID 缺失或已删除：{missingFileIds.map((fileId) => `#${fileId}`).join(', ')}</div>
                ) : null}
              </section>

              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">回答</p>
                    <h2>最终输出</h2>
                  </div>
                  {run.answer ? (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        setMemoryNotice('')
                        saveMemoryMutation.mutate({ title: `运行洞察：${truncate(run.task, 42)}` })
                      }}
                      disabled={saveMemoryMutation.isPending}
                    >
                      {saveMemoryMutation.isPending ? '保存中...' : '保存为记忆'}
                    </button>
                  ) : null}
                </div>
                {run.answer ? (
                  <div className="answer-block">
                    <pre>{run.answer}</pre>
                  </div>
                ) : (
                  <div className="empty-panel">
                    <strong>还没有最终回答。</strong>
                    <p>运行完成后，最终回答会显示在这里。</p>
                  </div>
                )}
                {memoryNotice ? <div className="panel-alert">{memoryNotice}</div> : null}
              </section>

              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">产物</p>
                    <h2>运行派生产物</h2>
                  </div>
                </div>
                <ArtifactList artifacts={artifactsQuery.data || []} />
              </section>

              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">记忆</p>
                    <h2>附加上下文</h2>
                  </div>
                </div>
                <MemoryList memories={memoriesQuery.data || run.memories || []} />
              </section>

              {run.error ? (
                <section className="panel">
                  <div className="panel-alert error">{run.error}</div>
                </section>
              ) : null}
            </aside>
          </div>
        ) : null}
      </main>
    </div>
  )
}

function mergeSteps(...collections) {
  const map = new Map()
  collections
    .flat()
    .filter(Boolean)
    .forEach((step) => {
      const key = step.id || `${step.order}-${step.type}`
      map.set(key, { ...(map.get(key) || {}), ...step })
    })

  return Array.from(map.values()).sort((a, b) => {
    const orderA = typeof a.order === 'number' ? a.order : 0
    const orderB = typeof b.order === 'number' ? b.order : 0
    return orderA - orderB
  })
}

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <p>{value}</p>
    </div>
  )
}

function formatDate(value) {
  if (!value) return '暂无'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function truncate(value, maxLength) {
  const text = String(value || '')
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text
}

function formatFileMeta(file) {
  return [file.file_type?.toUpperCase() || 'FILE', file.file_size_display || '大小未知']
    .filter(Boolean)
    .join(' | ')
}
