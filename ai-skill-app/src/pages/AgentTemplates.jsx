import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getAgentTemplate, listAgentRuns, listAgentTemplates, listAgentTools } from '../api/agents'
import Sidebar from '../components/workbench/Sidebar'
import TemplateEditor from '../components/workbench/TemplateEditor'
import { useAuth } from '../hooks/useAuth'

export default function AgentTemplates() {
  const { user, logout, isLocalMode } = useAuth()
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: templates = [] } = useQuery({ queryKey: ['agentTemplates'], queryFn: listAgentTemplates })
  const { data: tools = [] } = useQuery({ queryKey: ['agentTools'], queryFn: listAgentTools })
  const [selectedId, setSelectedId] = useState(null)

  const selectedTemplateQuery = useQuery({
    queryKey: ['agentTemplate', selectedId],
    queryFn: () => getAgentTemplate(selectedId),
    enabled: Boolean(selectedId),
    retry: false,
  })

  const selectedTemplate = selectedTemplateQuery.data || null
  const activeCount = useMemo(() => templates.filter((template) => template.is_active).length, [templates])
  const restrictedCount = useMemo(() => templates.filter((template) => template.allowed_tools?.length).length, [templates])

  return (
    <div className="workbench-shell">
      <Sidebar runs={runs} user={user} onLogout={logout} isLocalMode={isLocalMode} />

      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">模板</p>
            <h1>智能体模板目录</h1>
            <p>管理可复用的智能体定义，将它们连接到本地技能，并调整默认运行预算。</p>
          </div>
        </header>

        <section className="metric-grid">
          <MetricCard label="模板数" value={String(templates.length)} helper="全部已保存的智能体定义。" />
          <MetricCard label="已启用" value={String(activeCount)} helper="会出现在运行编排器中的模板。" />
          <MetricCard label="已绑定技能" value={String(templates.filter((template) => template.skill).length)} helper="指向本地技能文件的模板数量。" />
          <MetricCard label="受限工具" value={String(restrictedCount)} helper="设置了显式工具白名单的模板数量。" />
          <MetricCard label="运行数" value={String(runs.length)} helper="可使用这些模板的现有运行。" />
        </section>

        <div className="content-grid detail-grid">
          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">目录</p>
                <h2>可用模板</h2>
              </div>
            </div>

            <div className="template-list interactive">
              <button type="button" className={`template-card selectable ${selectedId ? '' : 'selected'}`} onClick={() => setSelectedId(null)}>
                <div className="template-card-top">
                  <strong>创建新模板</strong>
                  <small>空白表单</small>
                </div>
                <p>从一份全新的定义开始，并绑定技能或提示词策略。</p>
                <code>new-template</code>
              </button>

              {templates.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  className={`template-card selectable ${selectedId === template.id ? 'selected' : ''}`}
                  onClick={() => setSelectedId(template.id)}
                >
                  <div className="template-card-top">
                    <strong>{template.name}</strong>
                    <small>{template.default_max_steps} 步</small>
                  </div>
                  <p>{template.system_prompt || '未配置额外系统提示词。'}</p>
                  <code>{template.allowed_tools?.length ? template.allowed_tools.join(', ') : template.skill || template.slug}</code>
                </button>
              ))}
            </div>
          </section>

          <section className="panel">
            <TemplateEditor
              key={selectedTemplate?.id || 'new-template'}
              tools={tools}
              template={selectedTemplate}
              onSaved={(saved) => setSelectedId(saved.id)}
              onDeleted={() => setSelectedId(null)}
            />
          </section>
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
