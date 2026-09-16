import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listAgentRuns, listAgentTemplates, listAgentTools } from '../api/agents'
import { createMcpServer, deleteMcpServer, listMcpServers, probeMcpServer, updateMcpServer } from '../api/mcp'
import ChatFrame from '../components/chat/ChatFrame'

export default function ToolRegistry() {
  const queryClient = useQueryClient()
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: templates = [] } = useQuery({ queryKey: ['agentTemplates'], queryFn: listAgentTemplates })
  const { data: tools = [] } = useQuery({ queryKey: ['agentTools'], queryFn: listAgentTools })
  const { data: mcpServers = [] } = useQuery({ queryKey: ['mcpServers'], queryFn: listMcpServers })

  const [mcpForm, setMcpForm] = useState({ name: '', command: '', args: '', env: '' })
  const [mcpNotice, setMcpNotice] = useState('')
  const [probeResults, setProbeResults] = useState({})

  const createMcpMutation = useMutation({
    mutationFn: createMcpServer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcpServers'] })
      setMcpForm({ name: '', command: '', args: '', env: '' })
      setMcpNotice('MCP 服务器已添加，启用后对话即可调用它的工具。')
    },
    onError: (error) => setMcpNotice(error.response?.data?.message || error.message || '无法添加 MCP 服务器。'),
  })

  const updateMcpMutation = useMutation({
    mutationFn: ({ id, payload }) => updateMcpServer(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mcpServers'] }),
    onError: (error) => setMcpNotice(error.response?.data?.message || error.message || '无法更新 MCP 服务器。'),
  })

  const deleteMcpMutation = useMutation({
    mutationFn: deleteMcpServer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcpServers'] })
      setMcpNotice('MCP 服务器已删除。')
    },
    onError: (error) => setMcpNotice(error.message || '无法删除 MCP 服务器。'),
  })

  const probeMcpMutation = useMutation({
    mutationFn: ({ id }) => probeMcpServer(id),
    onSuccess: (result, variables) => {
      setProbeResults((prev) => ({ ...prev, [variables.id]: result.data }))
    },
    onError: (error, variables) => {
      setProbeResults((prev) => ({
        ...prev,
        [variables.id]: { ok: false, error: error.response?.data?.error || error.message || '探测失败。' },
      }))
    },
  })

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
              <p className="eyebrow">MCP</p>
              <h2>MCP 服务器</h2>
              <p>配置 stdio MCP 服务器后，其工具会动态注入对话（本地执行链路），名称自动加 mcp_ 前缀。</p>
            </div>
          </div>

          <div className="tool-card-grid">
            {mcpServers.map((server) => {
              const probe = probeResults[server.id]
              return (
                <article key={server.id} className="tool-card">
                  <div className="tool-card-top">
                    <div>
                      <strong>{server.name}</strong>
                      <small>{server.enabled ? '已启用' : '已停用'}</small>
                    </div>
                    <span className={`memory-pill ${server.enabled ? '' : 'warning'}`}>
                      {server.enabled ? '注入对话' : '不注入'}
                    </span>
                  </div>
                  <code>{[server.command, ...(server.args || [])].join(' ')}</code>
                  {probe ? (
                    <div className="tool-card-section">
                      <span>探测结果</span>
                      <p>
                        {probe.ok
                          ? `连通，发现 ${probe.tools.length} 个工具：${probe.tools.map((tool) => tool.prefixed).join(', ')}`
                          : `失败：${probe.error}`}
                      </p>
                    </div>
                  ) : null}
                  <div className="tool-card-section">
                    <span>操作</span>
                    <div className="mcp-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => updateMcpMutation.mutate({ id: server.id, payload: { enabled: !server.enabled } })}
                        disabled={updateMcpMutation.isPending}
                      >
                        {server.enabled ? '停用' : '启用'}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => probeMcpMutation.mutate({ id: server.id })}
                        disabled={probeMcpMutation.isPending}
                      >
                        {probeMcpMutation.isPending ? '探测中...' : '探测'}
                      </button>
                      <button
                        type="button"
                        className="secondary-button danger-button"
                        onClick={() => deleteMcpMutation.mutate(server.id)}
                        disabled={deleteMcpMutation.isPending}
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </article>
              )
            })}
            {!mcpServers.length ? <p className="panel-subtext">还没有配置 MCP 服务器。下面填入启动命令即可，例如 <code>npx -y @modelcontextprotocol/server-filesystem D:\docs</code>。</p> : null}
          </div>

          <div className="tool-card-section">
            <span>添加服务器</span>
            <div className="mcp-form">
              <input
                type="text"
                value={mcpForm.name}
                onChange={(event) => setMcpForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="名称，如 filesystem"
              />
              <input
                type="text"
                value={mcpForm.command}
                onChange={(event) => setMcpForm((prev) => ({ ...prev, command: event.target.value }))}
                placeholder="启动命令，如 npx"
              />
              <input
                type="text"
                value={mcpForm.args}
                onChange={(event) => setMcpForm((prev) => ({ ...prev, args: event.target.value }))}
                placeholder='参数 JSON 数组，如 ["-y", "@modelcontextprotocol/server-filesystem", "D:\\docs"]'
              />
              <input
                type="text"
                value={mcpForm.env}
                onChange={(event) => setMcpForm((prev) => ({ ...prev, env: event.target.value }))}
                placeholder='环境变量 JSON 对象（可选），如 {"API_KEY": "..."}'
              />
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  try {
                    createMcpMutation.mutate({
                      name: mcpForm.name,
                      command: mcpForm.command,
                      args: mcpForm.args.trim() ? JSON.parse(mcpForm.args) : [],
                      env: mcpForm.env.trim() ? JSON.parse(mcpForm.env) : {},
                    })
                  } catch (error) {
                    setMcpNotice(`JSON 解析失败：${error.message}`)
                  }
                }}
                disabled={createMcpMutation.isPending || !mcpForm.name.trim() || !mcpForm.command.trim()}
              >
                {createMcpMutation.isPending ? '添加中...' : '添加'}
              </button>
            </div>
            {mcpNotice ? <p className="inline-hint">{mcpNotice}</p> : null}
          </div>
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
