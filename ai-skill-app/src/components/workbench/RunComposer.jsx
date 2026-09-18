import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createAgentRun } from '../../api/agents'
import GlassSelect from '../GlassSelect'

export default function RunComposer({
  templates = [],
  memories = [],
  files = [],
  onCreated,
  compact = false,
}) {
  const queryClient = useQueryClient()
  const [task, setTask] = useState('')
  const [agentId, setAgentId] = useState('')
  const [maxSteps, setMaxSteps] = useState('')
  const [selectedMemoryIds, setSelectedMemoryIds] = useState([])
  const [selectedFileIds, setSelectedFileIds] = useState([])
  const activeTemplates = templates.filter((template) => template.is_active)
  const visibleMemories = [...memories]
    .sort((left, right) => {
      if (left.pinned === right.pinned) return 0
      return left.pinned ? -1 : 1
    })
    .slice(0, compact ? 4 : 6)
  const visibleFiles = [...files].slice(0, compact ? 4 : 6)

  const createMutation = useMutation({
    mutationFn: createAgentRun,
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ['agentRuns'] })
      onCreated?.(run)
      setTask('')
      setMaxSteps('')
      setSelectedMemoryIds([])
      setSelectedFileIds([])
    }
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    createMutation.mutate({
      task: task.trim(),
      agent_id: agentId ? Number(agentId) : undefined,
      max_steps: maxSteps ? Number(maxSteps) : undefined,
      memory_ids: selectedMemoryIds.length ? selectedMemoryIds : undefined,
      file_ids: selectedFileIds.length ? selectedFileIds : undefined,
    })
  }

  const toggleMemory = (memoryId) => {
    setSelectedMemoryIds((current) => (
      current.includes(memoryId)
        ? current.filter((value) => value !== memoryId)
        : [...current, memoryId]
    ))
  }

  const toggleFile = (fileId) => {
    setSelectedFileIds((current) => (
      current.includes(fileId)
        ? current.filter((value) => value !== fileId)
        : [...current, fileId]
    ))
  }

  return (
    <form className={`run-composer ${compact ? 'compact' : ''}`} onSubmit={handleSubmit}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">新建运行</p>
          <h2>发起任务</h2>
        </div>
        {createMutation.isPending ? <span className="inline-hint">创建中...</span> : null}
      </div>

      <label className="field">
        <span>任务内容</span>
        <textarea
          value={task}
          onChange={(event) => setTask(event.target.value)}
          placeholder="描述目标、预期输出、约束条件，以及希望智能体产出的内容。"
          rows={compact ? 5 : 7}
          required
        />
      </label>

      <div className="field-grid">
        <div className="field">
          <span>智能体模板</span>
          <GlassSelect
            ariaLabel="智能体模板"
            value={agentId}
            onChange={setAgentId}
            options={[
              { value: '', label: '默认运行时' },
              ...activeTemplates.map((template) => ({ value: template.id, label: template.name })),
            ]}
          />
        </div>

        <label className="field">
          <span>最大步数</span>
          <input
            type="number"
            min="1"
            max="24"
            value={maxSteps}
            onChange={(event) => setMaxSteps(event.target.value)}
            placeholder="使用模板默认值"
          />
        </label>
      </div>

      <div className="field">
        <span>附加记忆</span>
        {visibleMemories.length ? (
          <div className="memory-selector">
            {visibleMemories.map((memory) => (
              <label key={memory.id} className={`memory-option ${selectedMemoryIds.includes(memory.id) ? 'selected' : ''}`}>
                <input
                  type="checkbox"
                  checked={selectedMemoryIds.includes(memory.id)}
                  onChange={() => toggleMemory(memory.id)}
                />
                <div>
                  <strong>{memory.title}</strong>
                  <small>{memory.scope}{memory.pinned ? ' | 已置顶' : ''}</small>
                  <p>{truncate(memory.content, compact ? 90 : 140)}</p>
                </div>
              </label>
            ))}
          </div>
        ) : (
          <div className="empty-inline">还没有保存的记忆。你可以在记忆页创建，或从已完成的运行中保存。</div>
        )}
      </div>

      <div className="field">
        <span>参考文件</span>
        {visibleFiles.length ? (
          <div className="file-selector">
            {visibleFiles.map((file) => (
              <label key={file.id} className={`file-option ${selectedFileIds.includes(file.id) ? 'selected' : ''}`}>
                <input
                  type="checkbox"
                  checked={selectedFileIds.includes(file.id)}
                  onChange={() => toggleFile(file.id)}
                />
                <div>
                  <strong>{file.original_name}</strong>
                  <small>{formatFileMeta(file)}</small>
                  <p>{file.description || '附加后，这个文件会在运行期间提供给 doc_parse 使用。'}</p>
                </div>
              </label>
            ))}
          </div>
        ) : (
          <div className="empty-inline">还没有上传文件。可先到文件页添加参考资料。</div>
        )}
      </div>

      {createMutation.isError ? (
        <div className="panel-alert error">{createMutation.error.message || '无法创建运行。'}</div>
      ) : null}

      <div className="composer-actions">
        <button type="submit" className="primary-button" disabled={createMutation.isPending || !task.trim()}>
          创建运行
        </button>
        <p className="inline-hint">
          创建完成后会进入详情页，并自动开始执行和流式展示时间线。
        </p>
      </div>
    </form>
  )
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
