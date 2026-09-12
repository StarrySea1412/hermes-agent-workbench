import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listAgentRuns, listAgentTemplates, listAgentTools } from '../api/agents'
import ChatFrame from '../components/chat/ChatFrame'

export default function ToolRegistry() {
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: templates = [] } = useQuery({ queryKey: ['agentTemplates'], queryFn: listAgentTemplates })
  const { data: tools = [] } = useQuery({ queryKey: ['agentTools'], queryFn: listAgentTools })

  const templateUsage = useMemo(() => {
    const map = new Map()
    tools.forEach((tool) => map.set(tool.name, []))
    templates.forEach((template) => {
      const allowedTools = template.allowed_tools || []
      if (!allowedTools.length) return
      allowedTools.forEach((toolName) => {
        const current = map.get(toolName) || []
        current.push(template.name)
        map.set(toolName, current)
      })
    })
    return map
  }, [templates, tools])

  const runUsage = useMemo(() => {
    const map = new Map()
    tools.forEach((tool) => map.set(tool.name, 0))
    runs.forEach((run) => {
      ;(run.tools_used || []).forEach((toolName) => {
        map.set(toolName, (map.get(toolName) || 0) + 1)
      })
    })
    return map
  }, [runs, tools])

  const stubCount = tools.filter((tool) => tool.runtime === 'stub').length
  const templatedTools = [...templateUsage.values()].filter((items) => items.length).length

  return (
    <ChatFrame>
      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">工具</p>
            <h1>工具注册表</h1>
            <p>检查内置运行时工具，查看哪些模板暴露了它们，以及哪些执行轨迹已经实际使用过它们。</p>
          </div>
        </header>

        <section className="metric-grid">
          <MetricCard label="已注册" value={String(tools.length)} helper="编排器可用的工具数量。" />
          <MetricCard label="占位实现" value={String(stubCount)} helper="仍为占位实现的工具数量。" />
          <MetricCard label="模板映射" value={String(templatedTools)} helper="被模板白名单引用的工具数量。" />
          <MetricCard label="实际使用" value={String(runs.filter((run) => (run.tools_used || []).length).length)} helper="至少调用过一个工具的运行数量。" />
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">注册表</p>
              <h2>内置工具</h2>
            </div>
          </div>

          <div className="tool-card-grid">
            {tools.map((tool) => (
              <article key={tool.name} className="tool-card">
                <div className="tool-card-top">
                  <div>
                    <strong>{tool.name}</strong>
                    <small>{tool.runtime}</small>
                  </div>
                  <span className={`memory-pill ${tool.runtime === 'stub' ? 'warning' : ''}`}>
                    {tool.registered ? '已注册' : '缺失'}
                  </span>
                </div>
                <p>{tool.description}</p>
                <code>{Object.keys(tool.parameters?.properties || {}).join(', ') || '无参数'}</code>
                <div className="tool-card-section">
                  <span>模板</span>
                  <p>{templateUsage.get(tool.name)?.length ? templateUsage.get(tool.name).join(', ') : '还没有模板显式引用这个工具。'}</p>
                </div>
                <div className="tool-card-section">
                  <span>运行使用情况</span>
                  <p>{String(runUsage.get(tool.name) || 0)} 次运行</p>
                </div>
                {tool.notes ? (
                  <div className="tool-card-section">
                    <span>备注</span>
                    <p>{tool.notes}</p>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>
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
