import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createAgentTemplate, deleteAgentTemplate, updateAgentTemplate } from '../../api/agents'

const EMPTY_FORM = {
  name: '',
  slug: '',
  skill: '',
  system_prompt: '',
  default_max_steps: 8,
  allowed_tools: [],
  is_active: true,
}

export default function TemplateEditor({ template, tools = [], onSaved, onDeleted }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(() => buildTemplateForm(template))

  const saveMutation = useMutation({
    mutationFn: (payload) => (
      template?.id
        ? updateAgentTemplate(template.id, payload)
        : createAgentTemplate(payload)
    ),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ['agentTemplates'] })
      onSaved?.(saved)
    }
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteAgentTemplate(template.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentTemplates'] })
      onDeleted?.()
    }
  })

  const handleSubmit = (event) => {
    event.preventDefault()
    saveMutation.mutate({
      ...form,
      default_max_steps: Number(form.default_max_steps) || 8,
    })
  }

  const toggleTool = (toolName) => {
    setForm((current) => ({
      ...current,
      allowed_tools: current.allowed_tools.includes(toolName)
        ? current.allowed_tools.filter((value) => value !== toolName)
        : [...current.allowed_tools, toolName],
    }))
  }

  return (
    <form className="template-editor" onSubmit={handleSubmit}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">{template?.id ? '模板编辑' : '新建模板'}</p>
          <h2>{template?.id ? '编辑模板' : '创建模板'}</h2>
        </div>
      </div>

      <div className="field-grid">
        <label className="field">
          <span>名称</span>
          <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required />
        </label>
        <label className="field">
          <span>Slug</span>
          <input value={form.slug} onChange={(event) => setForm((current) => ({ ...current, slug: event.target.value }))} required />
        </label>
      </div>

      <label className="field">
        <span>技能路径</span>
        <input
          value={form.skill}
          onChange={(event) => setForm((current) => ({ ...current, skill: event.target.value }))}
          placeholder="可选的本地技能路径，例如 research/source-review"
        />
      </label>

      <div className="field-grid">
        <label className="field">
          <span>最大步数</span>
          <input
            type="number"
            min="1"
            max="24"
            value={form.default_max_steps}
            onChange={(event) => setForm((current) => ({ ...current, default_max_steps: event.target.value }))}
          />
        </label>
        <div className="field checkbox-field">
          <span>状态</span>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))}
            />
            <small>模板已启用</small>
          </label>
        </div>
      </div>

      <label className="field">
        <span>系统提示词</span>
        <textarea
          rows={8}
          value={form.system_prompt}
          onChange={(event) => setForm((current) => ({ ...current, system_prompt: event.target.value }))}
          placeholder="描述这个智能体应该如何规划、推理，以及在什么情况下调用工具。"
        />
      </label>

      <div className="field">
        <span>工具策略</span>
        <div className="tool-selector">
          {tools.map((tool) => (
            <label key={tool.name} className={`tool-option ${form.allowed_tools.includes(tool.name) ? 'selected' : ''}`}>
              <input
                type="checkbox"
                checked={form.allowed_tools.includes(tool.name)}
                onChange={() => toggleTool(tool.name)}
              />
              <div>
                <strong>{tool.name}</strong>
                <small>{tool.runtime}</small>
                <p>{tool.description}</p>
              </div>
            </label>
          ))}
        </div>
        <small className="inline-hint">
          {form.allowed_tools.length
            ? `已启用工具：${form.allowed_tools.join(', ')}`
            : '未设置显式工具列表，模板可使用所有已注册工具。'}
        </small>
      </div>

      {saveMutation.isError ? <div className="panel-alert error">{saveMutation.error.message || '无法保存模板。'}</div> : null}
      {deleteMutation.isError ? <div className="panel-alert error">{deleteMutation.error.message || '无法删除模板。'}</div> : null}

      <div className="editor-actions">
        <button type="submit" className="primary-button" disabled={saveMutation.isPending}>
          {saveMutation.isPending ? '保存中...' : template?.id ? '保存修改' : '创建模板'}
        </button>
        {template?.id ? (
          <button type="button" className="secondary-button danger-button" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
            {deleteMutation.isPending ? '删除中...' : '删除模板'}
          </button>
        ) : null}
      </div>
    </form>
  )
}

function buildTemplateForm(template) {
  if (!template) return EMPTY_FORM
  return {
    name: template.name || '',
    slug: template.slug || '',
    skill: template.skill || '',
    system_prompt: template.system_prompt || '',
    default_max_steps: template.default_max_steps || 8,
    allowed_tools: template.allowed_tools || [],
    is_active: typeof template.is_active === 'boolean' ? template.is_active : true,
  }
}
