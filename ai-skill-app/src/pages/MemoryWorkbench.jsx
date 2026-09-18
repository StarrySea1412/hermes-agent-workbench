import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createAgentMemory, deleteAgentMemory, listAgentMemories, listAgentRuns, updateAgentMemory } from '../api/agents'
import ChatFrame from '../components/chat/ChatFrame'
import GlassSelect from '../components/GlassSelect'

const EMPTY_FORM = {
  title: '',
  content: '',
  scope: 'workspace',
  tags: '',
  pinned: false,
  run_id: '',
}

export default function MemoryWorkbench() {
  const queryClient = useQueryClient()
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: memories = [] } = useQuery({ queryKey: ['agentMemories'], queryFn: () => listAgentMemories() })
  const [selectedId, setSelectedId] = useState(null)

  const selectedMemory = useMemo(
    () => memories.find((memory) => memory.id === selectedId) || null,
    [memories, selectedId]
  )

  const pinnedCount = memories.filter((memory) => memory.pinned).length
  const runLinkedCount = memories.filter((memory) => memory.run_id).length
  const scopeBreakdown = summarizeScopes(memories)

  return (
    <ChatFrame>
      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">记忆</p>
            <h1>记忆工作台</h1>
            <p>创建长期保存的用户或工作台记忆，将它们关联到历史运行，并把最相关的记录附加到后续任务中。</p>
          </div>
        </header>

        <section className="metric-grid">
          <MetricCard label="记忆数" value={String(memories.length)} helper="全部已保存的上下文记录。" />
          <MetricCard label="已置顶" value={String(pinnedCount)} helper="会优先显示在运行编排器里的记录。" />
          <MetricCard label="关联运行" value={String(runLinkedCount)} helper="带有来源运行的记忆数量。" />
          <MetricCard label="作用域" value={scopeBreakdown} helper="用户、工作台和运行级作用域覆盖情况。" />
        </section>

        <div className="content-grid detail-grid">
          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">目录</p>
                <h2>已保存的记忆记录</h2>
              </div>
            </div>

            <div className="memory-catalog">
              <button
                type="button"
                className={`memory-card selectable ${selectedId ? '' : 'selected'}`}
                onClick={() => setSelectedId(null)}
              >
                <div className="memory-card-top">
                  <div>
                    <strong>创建新记忆</strong>
                    <small>空白表单</small>
                  </div>
                </div>
                <p>新建一条长期记录，用来保存用户习惯、工作台默认规则或运行特定上下文。</p>
                <div className="memory-card-footer">
                  <span>未设作用域草稿</span>
                  <small>新建</small>
                </div>
              </button>

              {memories.map((memory) => (
                <button
                  key={memory.id}
                  type="button"
                  className={`memory-card selectable ${selectedId === memory.id ? 'selected' : ''}`}
                  onClick={() => setSelectedId(memory.id)}
                >
                  <div className="memory-card-top">
                    <div>
                      <strong>{memory.title}</strong>
                      <small>{formatScope(memory.scope)}{memory.pinned ? ' / 已置顶' : ''}</small>
                    </div>
                    {memory.pinned ? <span className="memory-pill">已置顶</span> : null}
                  </div>
                  <p>{memory.content}</p>
                  <div className="memory-card-footer">
                    <span>{(memory.tags || []).length ? memory.tags.join(', ') : '无标签'}</span>
                    <small>{memory.metadata?.source === 'auto' ? '对话自动沉淀' : (memory.run_id ? `运行 #${memory.run_id}` : '手动创建')}</small>
                  </div>
                </button>
              ))}

              {!memories.length ? <div className="empty-inline">还没有记忆。你可以从运行中保存最终回答，或在这里手动创建。</div> : null}
            </div>
          </section>

          <section className="panel">
            <MemoryEditor
              key={selectedMemory?.id || 'new-memory'}
              selectedMemory={selectedMemory}
              runs={runs}
              queryClient={queryClient}
              onSelectedId={setSelectedId}
            />
          </section>
        </div>
      </main>
    </ChatFrame>
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

function MemoryEditor({ selectedMemory, runs, queryClient, onSelectedId }) {
  const [form, setForm] = useState(() => buildMemoryForm(selectedMemory))

  const saveMutation = useMutation({
    mutationFn: (payload) => (
      selectedMemory
        ? updateAgentMemory(selectedMemory.id, payload)
        : createAgentMemory(payload)
    ),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ['agentMemories'] })
      onSelectedId(saved.id)
    }
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteAgentMemory(selectedMemory.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentMemories'] })
      onSelectedId(null)
    }
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    saveMutation.mutate({
      title: form.title.trim(),
      content: form.content.trim(),
      scope: form.scope,
      tags: form.tags
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean),
      pinned: form.pinned,
      run_id: form.run_id ? Number(form.run_id) : null,
    })
  }

  return (
    <form className="template-editor" onSubmit={handleSubmit}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">{selectedMemory ? '记忆编辑' : '新建记忆'}</p>
          <h2>{selectedMemory ? '编辑记忆' : '创建记忆'}</h2>
        </div>
      </div>

      <div className="field-grid">
        <label className="field">
          <span>标题</span>
          <input
            value={form.title}
            onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
            required
          />
        </label>
        <div className="field">
          <span>作用域</span>
          <GlassSelect
            ariaLabel="作用域"
            value={form.scope}
            onChange={(scope) => setForm((current) => ({ ...current, scope }))}
            options={[
              { value: 'user', label: '用户' },
              { value: 'workspace', label: '工作台' },
              { value: 'run', label: '运行' },
            ]}
          />
        </div>
      </div>

      <label className="field">
        <span>内容</span>
        <textarea
          rows={9}
          value={form.content}
          onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))}
          placeholder="记录行为偏好、约束规则、团队约定或长期有效的结论。"
          required
        />
      </label>

      <div className="field-grid">
        <label className="field">
          <span>标签</span>
          <input
            value={form.tags}
            onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))}
            placeholder="使用逗号分隔标签"
          />
        </label>
        <div className="field">
          <span>来源运行</span>
          <GlassSelect
            ariaLabel="来源运行"
            value={form.run_id}
            onChange={(run_id) => setForm((current) => ({ ...current, run_id }))}
            options={[
              { value: '', label: '不关联运行' },
              ...runs.map((run) => ({ value: String(run.id), label: `#${run.id} ${truncate(run.task, 56)}` })),
            ]}
          />
        </div>
      </div>

      <div className="field checkbox-field">
        <span>优先级</span>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.pinned}
            onChange={(event) => setForm((current) => ({ ...current, pinned: event.target.checked }))}
          />
          <small>将这条记忆置顶，使其在新运行中优先显示。</small>
        </label>
      </div>

      {saveMutation.isError ? <div className="panel-alert error">{saveMutation.error.message || '无法保存这条记忆。'}</div> : null}
      {deleteMutation.isError ? <div className="panel-alert error">{deleteMutation.error.message || '无法删除这条记忆。'}</div> : null}

      <div className="editor-actions">
        <button type="submit" className="primary-button" disabled={saveMutation.isPending}>
          {saveMutation.isPending ? '保存中...' : selectedMemory ? '保存修改' : '创建记忆'}
        </button>
        {selectedMemory ? (
          <button
            type="button"
            className="secondary-button danger-button"
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? '删除中...' : '删除记忆'}
          </button>
        ) : null}
      </div>
    </form>
  )
}

function buildMemoryForm(selectedMemory) {
  if (!selectedMemory) return EMPTY_FORM
  return {
    title: selectedMemory.title || '',
    content: selectedMemory.content || '',
    scope: selectedMemory.scope || 'workspace',
    tags: (selectedMemory.tags || []).join(', '),
    pinned: Boolean(selectedMemory.pinned),
    run_id: selectedMemory.run_id || '',
  }
}

function summarizeScopes(memories) {
  const counts = memories.reduce((accumulator, memory) => {
    accumulator[memory.scope] = (accumulator[memory.scope] || 0) + 1
    return accumulator
  }, {})
  return ['user', 'workspace', 'run']
    .filter((scope) => counts[scope])
    .map((scope) => `${formatScope(scope)}:${counts[scope]}`)
    .join(' / ') || '暂无'
}

function truncate(value, maxLength) {
  const text = String(value || '')
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text
}

function formatScope(scope) {
  switch (scope) {
    case 'user':
      return '用户'
    case 'workspace':
      return '工作台'
    case 'run':
      return '运行'
    default:
      return scope || '未分类'
  }
}
