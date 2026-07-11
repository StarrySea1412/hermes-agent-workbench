import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listAgentRuns } from '../api/agents'
import {
  cancelBidWorkflow,
  createBid,
  createBidChapter,
  createBidWorkflow,
  deleteBid,
  deleteBidChapter,
  executeBidWorkflow,
  exportBidDocx,
  generateBidOutline,
  getBid,
  getBidWorkflowDetail,
  listBids,
  listBidWorkflows,
  updateBidChapter,
} from '../api/bids'
import ArtifactList from '../components/workbench/ArtifactList'
import RunStatusBadge from '../components/workbench/RunStatusBadge'
import Sidebar from '../components/workbench/Sidebar'
import { useAuth } from '../hooks/useAuth'

const EMPTY_BID_FORM = {
  title: '',
}

const EMPTY_WORKFLOW_FORM = {
  objective: '',
  includeChildChapters: false,
}

const EMPTY_OUTLINE_FORM = {
  title: '',
}

export default function WorkflowLab() {
  const queryClient = useQueryClient()
  const outlineInputRef = useRef(null)
  const { user, logout, isLocalMode } = useAuth()
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: bids = [] } = useQuery({ queryKey: ['bids'], queryFn: listBids })
  const [requestedBidId, setRequestedBidId] = useState(null)
  const [requestedWorkflowId, setRequestedWorkflowId] = useState(null)
  const [requestedChapterId, setRequestedChapterId] = useState(null)
  const [bidForm, setBidForm] = useState(EMPTY_BID_FORM)
  const [workflowForm, setWorkflowForm] = useState(EMPTY_WORKFLOW_FORM)
  const [outlineForm, setOutlineForm] = useState(EMPTY_OUTLINE_FORM)
  const [outlineFile, setOutlineFile] = useState(null)
  const [outlinePreview, setOutlinePreview] = useState(null)
  const [notice, setNotice] = useState('')
  const selectedBidId = bids.some((bid) => bid.id === requestedBidId)
    ? requestedBidId
    : bids[0]?.id || null

  const selectedBidQuery = useQuery({
    queryKey: ['bid', selectedBidId],
    queryFn: () => getBid(selectedBidId),
    enabled: Boolean(selectedBidId),
  })

  const workflowsQuery = useQuery({
    queryKey: ['bidWorkflows', selectedBidId],
    queryFn: () => listBidWorkflows(selectedBidId),
    enabled: Boolean(selectedBidId),
    refetchInterval: (query) => {
      const workflows = query.state.data || []
      return workflows.some((workflow) => workflow.status === 'running') ? 2000 : false
    },
  })
  const workflows = workflowsQuery.data || []
  const selectedWorkflowId = workflows.some((workflow) => workflow.id === requestedWorkflowId)
    ? requestedWorkflowId
    : workflows[0]?.id || null

  const selectedWorkflowQuery = useQuery({
    queryKey: ['bidWorkflow', selectedBidId, selectedWorkflowId],
    queryFn: () => getBidWorkflowDetail(selectedBidId, selectedWorkflowId),
    enabled: Boolean(selectedBidId && selectedWorkflowId),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2000 : false),
  })

  const createBidMutation = useMutation({
    mutationFn: createBid,
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['bids'] })
      queryClient.invalidateQueries({ queryKey: ['bid', created.id] })
      setRequestedBidId(created.id)
      setRequestedWorkflowId(null)
      setBidForm(EMPTY_BID_FORM)
      setNotice('项目蓝图已创建。')
    },
    onError: (error) => {
      setNotice(error.message || '无法创建工作流项目。')
    },
  })

  const deleteBidMutation = useMutation({
    mutationFn: deleteBid,
    onSuccess: (_, deletedBidId) => {
      queryClient.invalidateQueries({ queryKey: ['bids'] })
      queryClient.removeQueries({ queryKey: ['bid', deletedBidId] })
      queryClient.removeQueries({ queryKey: ['bidWorkflows', deletedBidId] })
      setRequestedWorkflowId(null)
      setNotice('项目蓝图已删除。')
    },
    onError: (error) => {
      setNotice(error.message || '无法删除工作流项目。')
    },
  })

  const outlineMutation = useMutation({
    mutationFn: ({ file, title }) => generateBidOutline(file, title),
    onSuccess: (result) => {
      setOutlinePreview(result)
      setNotice('已根据上传的源文件生成大纲。')
    },
    onError: (error) => {
      setNotice(error.message || '无法生成大纲。')
    },
  })

  const createFromOutlineMutation = useMutation({
    mutationFn: async (outline) => {
      const created = await createBid({ title: outline.bid_title || '未命名项目' })
      await syncBidChapters(created.id, created.chapters || [], outline.chapters || [])
      return created.id
    },
    onSuccess: (createdBidId) => {
      queryClient.invalidateQueries({ queryKey: ['bids'] })
      queryClient.invalidateQueries({ queryKey: ['bid', createdBidId] })
      setRequestedBidId(createdBidId)
      setRequestedWorkflowId(null)
      setNotice('已根据生成的大纲创建项目。')
    },
    onError: (error) => {
      setNotice(error.message || '无法根据大纲创建项目。')
    },
  })

  const createWorkflowMutation = useMutation({
    mutationFn: ({ bidId, payload }) => createBidWorkflow(bidId, payload),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['bidWorkflows', selectedBidId] })
      queryClient.invalidateQueries({ queryKey: ['bidWorkflow', selectedBidId, created.id] })
      setRequestedWorkflowId(created.id)
      setWorkflowForm(EMPTY_WORKFLOW_FORM)
      setNotice('工作流蓝图已创建。')
    },
    onError: (error) => {
      setNotice(error.message || '无法创建工作流蓝图。')
    },
  })

  const executeWorkflowMutation = useMutation({
    mutationFn: ({ bidId, workflowId }) => executeBidWorkflow(bidId, workflowId),
    onMutate: ({ workflowId }) => {
      setNotice('')
      queryClient.setQueryData(['bidWorkflow', selectedBidId, workflowId], (current) => (
        current ? { ...current, status: 'running' } : current
      ))
      queryClient.setQueryData(['bidWorkflows', selectedBidId], (current) => (
        Array.isArray(current)
          ? current.map((workflow) => (
              workflow.id === workflowId ? { ...workflow, status: 'running' } : workflow
            ))
          : current
      ))
    },
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: ['bidWorkflows', selectedBidId] })
      queryClient.invalidateQueries({ queryKey: ['bidWorkflow', selectedBidId, detail.id] })
      queryClient.invalidateQueries({ queryKey: ['bid', selectedBidId] })
      queryClient.invalidateQueries({ queryKey: ['agentRuns'] })
      setNotice('工作流执行完成。')
    },
    onError: (error) => {
      setNotice(error.message || '无法执行工作流。')
    },
  })

  const cancelWorkflowMutation = useMutation({
    mutationFn: ({ bidId, workflowId }) => cancelBidWorkflow(bidId, workflowId),
    onMutate: () => {
      setNotice('')
    },
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: ['bidWorkflows', selectedBidId] })
      queryClient.invalidateQueries({ queryKey: ['bidWorkflow', selectedBidId, detail.id] })
      queryClient.invalidateQueries({ queryKey: ['bid', selectedBidId] })
      queryClient.invalidateQueries({ queryKey: ['agentRuns'] })
      setNotice('工作流已取消。')
    },
    onError: (error) => {
      setNotice(error.message || '无法取消工作流。')
    },
  })

  const exportBidMutation = useMutation({
    mutationFn: exportBidDocx,
    onSuccess: ({ blob, filename }) => {
      downloadBlob(blob, filename)
      setNotice('项目已导出。')
    },
    onError: (error) => {
      setNotice(error.message || '无法导出所选项目。')
    },
  })

  const selectedBid = selectedBidQuery.data || null
  const flattenedChapters = useMemo(() => flattenChapters(selectedBid?.chapters || []), [selectedBid?.chapters])
  const selectedChapterId = flattenedChapters.some((chapter) => chapter.id === requestedChapterId)
    ? requestedChapterId
    : flattenedChapters[0]?.id || null
  const selectedChapter = useMemo(
    () => flattenedChapters.find((chapter) => chapter.id === selectedChapterId) || flattenedChapters[0] || null,
    [flattenedChapters, selectedChapterId]
  )
  const selectedWorkflow = selectedWorkflowQuery.data || null
  const totalWorkflowCount = workflows.length
  const totalNodeCount = workflows.reduce((sum, workflow) => sum + (workflow.node_count || 0), 0)
  const chapterCount = countChapters(selectedBid?.chapters || [])
  const completedSteps = (selectedBid?.steps || []).filter((step) => step.status === 'completed').length
  const workflowTemplates = useMemo(
    () => collectWorkflowAgents(selectedWorkflow?.nodes || []),
    [selectedWorkflow?.nodes]
  )
  const canExecuteWorkflow = Boolean(selectedBidId && selectedWorkflowId && selectedWorkflow?.status === 'pending')
  const canCancelWorkflow = selectedWorkflow?.status === 'pending' || selectedWorkflow?.status === 'running'

  const handleBidSubmit = (event) => {
    event.preventDefault()
    setNotice('')
    createBidMutation.mutate({ title: bidForm.title.trim() })
  }

  const handleOutlineSubmit = (event) => {
    event.preventDefault()
    if (!outlineFile) return
    setNotice('')
    outlineMutation.mutate({ file: outlineFile, title: outlineForm.title.trim() })
  }

  const handleWorkflowSubmit = (event) => {
    event.preventDefault()
    if (!selectedBidId) return
    setNotice('')
    createWorkflowMutation.mutate({
      bidId: selectedBidId,
      payload: {
        objective: workflowForm.objective.trim() || undefined,
        include_child_chapters: workflowForm.includeChildChapters,
      },
    })
  }

  return (
    <div className="workbench-shell">
      <Sidebar runs={runs} user={user} onLogout={logout} isLocalMode={isLocalMode} />

      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">工作流实验室</p>
            <h1>设计多智能体蓝图</h1>
            <p>
              这个实验室把仓库里的多智能体流水线模型变成了一个可检查的产品界面。
              它以项目文档为领域样例，用来规划 analyzer、planner、writer、reviewer 等链路。
            </p>
          </div>
        </header>

        <section className="metric-grid">
          <MetricCard label="项目数" value={String(bids.length)} helper="可生成工作流蓝图的领域样例。" />
          <MetricCard label="蓝图数" value={String(totalWorkflowCount)} helper="当前选中项目上的工作流定义数量。" />
          <MetricCard label="节点数" value={String(totalNodeCount)} helper="可见蓝图中的全部节点总数。" />
          <MetricCard label="模板数" value={String(workflowTemplates.length)} helper="当前工作流中使用到的智能体角色数量。" />
        </section>

        <div className="content-grid detail-grid">
          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">项目</p>
                <h2>工作流源项目</h2>
              </div>
            </div>

            <form className="inline-form" onSubmit={handleBidSubmit}>
              <label className="field">
                <span>项目标题</span>
                <input
                  value={bidForm.title}
                  onChange={(event) => setBidForm({ title: event.target.value })}
                  placeholder="例如：地铁运营项目方案"
                  required
                />
              </label>
              <div className="editor-actions inline-actions">
                <button type="submit" className="primary-button" disabled={createBidMutation.isPending || !bidForm.title.trim()}>
                  {createBidMutation.isPending ? '创建中...' : '创建项目'}
                </button>
              </div>
            </form>

            <div className="panel-divider" />

            <form className="inline-form" onSubmit={handleOutlineSubmit}>
              <div className="panel-header">
                <div>
                  <p className="eyebrow">输入</p>
                  <h2>从源文件生成大纲</h2>
                </div>
              </div>

              <label className="field">
                <span>可选项目标题</span>
                <input
                  value={outlineForm.title}
                  onChange={(event) => setOutlineForm({ title: event.target.value })}
                  placeholder="覆盖自动推断的项目标题"
                />
              </label>

              <label className="field">
                <span>源文件</span>
                <input
                  ref={outlineInputRef}
                  type="file"
                  accept=".pdf,.docx,.doc,.txt,.md"
                  onChange={(event) => {
                    setOutlineFile(event.target.files?.[0] || null)
                    setOutlinePreview(null)
                  }}
                />
              </label>

              {outlineFile ? (
                <div className="chip-list">
                  <code>{outlineFile.name}</code>
                </div>
              ) : (
                <div className="empty-inline">先上传参考文档，提取章节大纲后再创建项目。</div>
              )}

              <div className="editor-actions inline-actions">
                <button type="submit" className="primary-button" disabled={outlineMutation.isPending || !outlineFile}>
                  {outlineMutation.isPending ? '生成中...' : '生成大纲'}
                </button>
              </div>
            </form>

            {notice ? <div className={`panel-alert ${hasMutationError(createBidMutation, deleteBidMutation, outlineMutation, createFromOutlineMutation, createWorkflowMutation, executeWorkflowMutation, cancelWorkflowMutation, exportBidMutation) ? 'error' : ''}`}>{notice}</div> : null}

            {outlinePreview ? (
              <div className="tool-card">
                <div className="tool-card-top">
                  <div>
                    <strong>{outlinePreview.bid_title}</strong>
                    <small>{`建议章节 ${outlinePreview.chapters?.length || 0} 个`}</small>
                  </div>
                </div>
                <div className="tool-card-section">
                  <span>建议章节</span>
                  <p>{(outlinePreview.chapters || []).map((chapter) => chapter.title).join(', ')}</p>
                </div>
                <div className="tool-card-section">
                  <span>分析摘要</span>
                  <p>{formatOutlineSummary(outlinePreview.analysis)}</p>
                </div>
                <div className="editor-actions">
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => createFromOutlineMutation.mutate(outlinePreview)}
                    disabled={createFromOutlineMutation.isPending}
                  >
                    {createFromOutlineMutation.isPending ? '创建中...' : '根据大纲创建项目'}
                  </button>
                </div>
              </div>
            ) : null}

            <div className="template-list interactive">
              {bids.map((bid) => (
                <button
                  key={bid.id}
                  type="button"
                  className={`template-card selectable ${selectedBidId === bid.id ? 'selected' : ''}`}
                  onClick={() => {
                    setRequestedBidId(bid.id)
                    setRequestedWorkflowId(null)
                  }}
                >
                  <div className="template-card-top">
                    <strong>{bid.title}</strong>
                    <RunStatusBadge status={mapBidStatusToRunStatus(bid.status)} />
                  </div>
                  <p>{formatBidSummary(bid)}</p>
                  <code>{formatShortDate(bid.created_at)}</code>
                </button>
              ))}
              {!bids.length ? <div className="empty-inline">还没有工作流源项目。先创建一个，才能检查多智能体蓝图模型。</div> : null}
            </div>
          </section>

          <aside className="detail-rail">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">项目</p>
                  <h2>当前选中项目</h2>
                </div>
                {selectedBid ? (
                  <div className="editor-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => exportBidMutation.mutate(selectedBid.id)}
                      disabled={exportBidMutation.isPending}
                    >
                      {exportBidMutation.isPending ? '导出中...' : '导出 docx'}
                    </button>
                    <button
                      type="button"
                      className="secondary-button danger-button"
                      onClick={() => deleteBidMutation.mutate(selectedBid.id)}
                      disabled={deleteBidMutation.isPending}
                    >
                      {deleteBidMutation.isPending ? '删除中...' : '删除'}
                    </button>
                  </div>
                ) : null}
              </div>

              {selectedBid ? (
                <div className="stack-list">
                  <InfoRow label="标题" value={selectedBid.title} />
                  <InfoRow label="章节数" value={String(chapterCount)} />
                  <InfoRow label="已完成步骤" value={`${completedSteps} / ${selectedBid.steps?.length || 0}`} />
                  <InfoRow label="状态" value={formatEntityStatus(selectedBid.status || 'draft')} />
                </div>
              ) : (
                <div className="empty-panel">
                  <strong>尚未选择项目。</strong>
                  <p>请选择一个项目，查看章节结构并创建工作流蓝图。</p>
                </div>
              )}
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">章节</p>
                  <h2>源结构</h2>
                </div>
              </div>
              {selectedBid?.chapters?.length ? (
                <div className="chapter-tree">
                  {selectedBid.chapters.map((chapter) => (
                    <ChapterTree
                      key={chapter.id}
                      chapter={chapter}
                      depth={0}
                      selectedChapterId={selectedChapterId}
                      onSelectChapter={setRequestedChapterId}
                    />
                  ))}
                </div>
              ) : (
                <div className="empty-inline">当前项目还没有章节。</div>
              )}
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">章节内容</p>
                  <h2>内容预览</h2>
                </div>
              </div>
              {selectedChapter ? (
                <div className="stack-list">
                  <InfoRow label="标题" value={selectedChapter.title} />
                  <InfoRow label="顺序" value={String(selectedChapter.order ?? 0)} />
                  <div className="answer-block">
                    <pre>{formatChapterPreview(selectedChapter.content)}</pre>
                  </div>
                </div>
              ) : (
                <div className="empty-panel">
                  <strong>尚未选择章节。</strong>
                  <p>请选择一个章节，查看它当前的内容。</p>
                </div>
              )}
            </section>
          </aside>
        </div>

        <div className="content-grid detail-grid">
          <section className="panel">
            <form className="template-editor" onSubmit={handleWorkflowSubmit}>
              <div className="panel-header">
                <div>
                  <p className="eyebrow">蓝图</p>
                  <h2>创建工作流蓝图</h2>
                </div>
              </div>

              <label className="field">
                <span>目标</span>
                <textarea
                  rows={5}
                  value={workflowForm.objective}
                  onChange={(event) => setWorkflowForm((current) => ({ ...current, objective: event.target.value }))}
                  placeholder="描述 analyzer、planner、writer、reviewer 这条流水线要达成什么结果。"
                />
              </label>

              <div className="field checkbox-field">
                <span>范围</span>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={workflowForm.includeChildChapters}
                    onChange={(event) => setWorkflowForm((current) => ({ ...current, includeChildChapters: event.target.checked }))}
                  />
                  <small>如果存在子章节，将其拆分成独立 writer 节点。</small>
                </label>
              </div>

              <div className="editor-actions">
                <button
                  type="submit"
                  className="primary-button"
                  disabled={createWorkflowMutation.isPending || !selectedBidId}
                >
                  {createWorkflowMutation.isPending ? '创建中...' : '创建工作流'}
                </button>
              </div>
            </form>

            <div className="panel-divider" />

            <div className="panel-header">
              <div>
                <p className="eyebrow">蓝图列表</p>
                <h2>可用工作流</h2>
              </div>
            </div>

            <div className="template-list interactive">
              {workflows.map((workflow) => (
                <button
                  key={workflow.id}
                  type="button"
                  className={`template-card selectable ${selectedWorkflowId === workflow.id ? 'selected' : ''}`}
                  onClick={() => setRequestedWorkflowId(workflow.id)}
                >
                  <div className="template-card-top">
                    <strong>{workflow.title}</strong>
                    <RunStatusBadge status={workflow.status} />
                  </div>
                  <p>{workflow.objective || '默认项目流水线蓝图。'}</p>
                  <code>{`${workflow.node_count} 个节点 / 已完成 ${workflow.completed_nodes}`}</code>
                </button>
              ))}
              {!selectedBidId ? <div className="empty-inline">请先选择项目。</div> : null}
              {selectedBidId && !workflows.length ? <div className="empty-inline">当前项目还没有工作流蓝图。</div> : null}
            </div>
          </section>

          <aside className="detail-rail">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">节点</p>
                  <h2>工作流结构</h2>
                </div>
                {selectedWorkflow ? (
                  <div className="editor-actions">
                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => executeWorkflowMutation.mutate({ bidId: selectedBidId, workflowId: selectedWorkflow.id })}
                      disabled={!canExecuteWorkflow || executeWorkflowMutation.isPending}
                    >
                      {executeWorkflowMutation.isPending ? '运行中...' : '运行工作流'}
                    </button>
                    {canCancelWorkflow ? (
                      <button
                        type="button"
                        className="secondary-button danger-button"
                        onClick={() => cancelWorkflowMutation.mutate({ bidId: selectedBidId, workflowId: selectedWorkflow.id })}
                        disabled={cancelWorkflowMutation.isPending}
                      >
                        {cancelWorkflowMutation.isPending ? '取消中...' : '取消'}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              {selectedWorkflow?.nodes?.length ? (
                <>
                  <div className="stack-list">
                    <InfoRow label="目标" value={selectedWorkflow.objective || '默认项目流水线目标'} />
                    <InfoRow label="状态" value={formatEntityStatus(selectedWorkflow.status)} />
                    <InfoRow label="当前节点" value={selectedWorkflow.current_node_key || '空闲'} />
                    <InfoRow label="进度" value={`${selectedWorkflow.completed_nodes || 0} / ${selectedWorkflow.node_count || 0}`} />
                  </div>
                  <div className="workflow-node-grid">
                    {selectedWorkflow.nodes.map((node) => (
                      <article key={node.id} className="tool-card">
                        <div className="tool-card-top">
                          <div>
                            <strong>{node.label}</strong>
                            <small>{node.agent_slug || node.node_type}</small>
                          </div>
                          <RunStatusBadge status={node.status} />
                        </div>
                        <div className="tool-card-section">
                          <span>依赖</span>
                          <p>{node.depends_on?.length ? node.depends_on.join(', ') : '无'}</p>
                        </div>
                        <div className="tool-card-section">
                          <span>输入</span>
                          <p>{node.input_artifacts?.length ? node.input_artifacts.join(', ') : '无'}</p>
                        </div>
                        <div className="tool-card-section">
                          <span>输出</span>
                          <p>{node.output_artifacts?.length ? node.output_artifacts.join(', ') : '无'}</p>
                        </div>
                        {node.summary ? (
                          <div className="tool-card-section">
                            <span>摘要</span>
                            <p>{node.summary}</p>
                          </div>
                        ) : null}
                        {node.error ? (
                          <div className="tool-card-section">
                            <span>错误</span>
                            <p>{node.error}</p>
                          </div>
                        ) : null}
                        {node.metadata && Object.keys(node.metadata).length ? (
                          <div className="tool-card-section">
                            <span>元数据</span>
                            <p>{formatNodeMetadata(node.metadata)}</p>
                          </div>
                        ) : null}
                        {node.agent_run_id ? (
                          <div className="tool-card-section">
                            <span>关联运行</span>
                            <p>
                              <Link className="artifact-link" to={`/runs/${node.agent_run_id}`}>
                                打开运行 #{node.agent_run_id}
                              </Link>
                            </p>
                          </div>
                        ) : null}
                      </article>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty-panel">
                  <strong>尚未选择工作流。</strong>
                  <p>请选择一个蓝图，查看它的节点顺序和产物。</p>
                </div>
              )}
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">产物</p>
                  <h2>工作流产物</h2>
                </div>
              </div>
              <ArtifactList artifacts={selectedWorkflow?.artifacts || []} />
            </section>
          </aside>
        </div>
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

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <p>{value}</p>
    </div>
  )
}

function ChapterTree({ chapter, depth, selectedChapterId, onSelectChapter }) {
  return (
    <div className="chapter-item" style={{ '--depth': depth }}>
      <button
        type="button"
        className={`chapter-item-row ${selectedChapterId === chapter.id ? 'selected' : ''}`}
        onClick={() => onSelectChapter(chapter.id)}
      >
        <strong>{chapter.title}</strong>
        <small>{`顺序 ${chapter.order}`}</small>
      </button>
      {chapter.children?.length ? (
        <div className="chapter-children">
          {chapter.children.map((child) => (
            <ChapterTree
              key={child.id}
              chapter={child}
              depth={depth + 1}
              selectedChapterId={selectedChapterId}
              onSelectChapter={onSelectChapter}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

async function syncBidChapters(bidId, existingChapters, desiredChapters) {
  const current = [...existingChapters]
    .filter((chapter) => chapter.parent_id === null || chapter.parent_id === undefined)
    .sort((left, right) => left.order - right.order)

  const target = desiredChapters.map((chapter, index) => ({
    title: chapter.title,
    order: index,
  }))

  const sharedCount = Math.min(current.length, target.length)
  for (let index = 0; index < sharedCount; index += 1) {
    await updateBidChapter(bidId, current[index].id, target[index])
  }

  for (let index = current.length - 1; index >= target.length; index -= 1) {
    await deleteBidChapter(bidId, current[index].id)
  }

  for (let index = current.length; index < target.length; index += 1) {
    await createBidChapter(bidId, target[index])
  }
}

function countChapters(chapters) {
  return chapters.reduce((sum, chapter) => sum + 1 + countChapters(chapter.children || []), 0)
}

function collectWorkflowAgents(nodes) {
  return Array.from(new Set(nodes.map((node) => node.agent_slug).filter(Boolean)))
}

function flattenChapters(chapters) {
  return chapters.flatMap((chapter) => [chapter, ...flattenChapters(chapter.children || [])])
}

function hasMutationError(...mutations) {
  return mutations.some((mutation) => mutation.isError)
}

function mapBidStatusToRunStatus(status) {
  if (status === 'completed') return 'done'
  if (status === 'active' || status === 'running') return 'running'
  if (status === 'failed') return 'failed'
  return 'pending'
}

function formatBidSummary(bid) {
  return `已完成 ${bid.completed_chapters || 0} / ${bid.total_chapters || 0} 个章节`
}

function formatShortDate(value) {
  if (!value) return '未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString()
}

function formatNodeMetadata(metadata) {
  return Object.entries(metadata)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(' / ')
}

function formatOutlineSummary(analysis) {
  if (!analysis) return '没有返回分析详情。'

  const parts = [
    analysis.project_name,
    analysis.project_number ? `项目编号 #${analysis.project_number}` : '',
    analysis.purchaser,
    analysis.deadline ? `截止时间 ${analysis.deadline}` : '',
  ].filter(Boolean)

  return parts.length ? parts.join(' / ') : '这份大纲是根据上传的源资料生成的。'
}

function formatEntityStatus(status) {
  switch (status) {
    case 'draft':
      return '草稿'
    case 'pending':
      return '待执行'
    case 'running':
    case 'active':
      return '运行中'
    case 'done':
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'cancelled':
      return '已取消'
    default:
      return status || '未知'
  }
}

function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}

function formatChapterPreview(content) {
  const blocks = normalizeChapterBlocks(content)
  if (!blocks.length) return '还没有内容。'
  return blocks.map((block) => block.text).join('\n\n')
}

function normalizeChapterBlocks(content) {
  if (!content) return []

  if (typeof content === 'string') {
    return content
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((text) => ({ text }))
  }

  if (!Array.isArray(content)) return []

  return content
    .map((block) => {
      if (!block || typeof block !== 'object') return null
      const text = Array.isArray(block.children)
        ? block.children
            .map((child) => (child && typeof child === 'object' ? child.value : ''))
            .join('')
            .trim()
        : ''
      if (!text) return null
      if (block.type === 'list') {
        return { text: `${block.listType === 'number' ? '1.' : '-'} ${text}` }
      }
      return { text }
    })
    .filter(Boolean)
}
