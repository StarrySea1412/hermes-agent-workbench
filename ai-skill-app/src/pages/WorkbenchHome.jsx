import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listAgentMemories, listAgentRuns, listAgentTemplates, listAgentTools } from '../api/agents'
import { listFiles } from '../api/files'
import RunComposer from '../components/workbench/RunComposer'
import RunStatusBadge from '../components/workbench/RunStatusBadge'
import ChatFrame from '../components/chat/ChatFrame'
import { useAIConfig, useHermesMonitor, useHermesSkills } from '../hooks/useAIConfig'

export default function WorkbenchHome() {
  const navigate = useNavigate()
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: templates = [] } = useQuery({ queryKey: ['agentTemplates'], queryFn: listAgentTemplates })
  const { data: memories = [] } = useQuery({ queryKey: ['agentMemories'], queryFn: () => listAgentMemories() })
  const { data: files = [] } = useQuery({ queryKey: ['files'], queryFn: listFiles })
  const { data: tools = [] } = useQuery({ queryKey: ['agentTools'], queryFn: listAgentTools })
  const { data: aiConfig } = useAIConfig()
  const { data: hermesMonitor } = useHermesMonitor()
  const { data: hermesSkills = [] } = useHermesSkills()

  const recentRuns = runs.slice(0, 4)
  const finishedRuns = runs.filter((run) => run.status === 'done').length
  const currentModel = aiConfig?.model_name || hermesMonitor?.models?.[0] || ''
  const flowSteps = [
    {
      title: '配置模型',
      state: currentModel || '待配置',
      description: '保存提供方、基础 URL、API Key 和模型名，再用测试连接验证聊天接口。',
      action: '模型设置',
      path: '/settings',
    },
    {
      title: '开始聊天',
      state: hermesMonitor?.connected ? 'Hermes 在线' : '检查连接',
      description: '在主聊天页直接描述任务，上传资料，观察工具调用和运行阶段。',
      action: '开始对话',
      path: '/',
    },
    {
      title: '补充资料',
      state: `${files.length} 个文件`,
      description: '把文档、表格和参考材料放进工作区，作为本轮任务上下文。',
      action: '文件库',
      path: '/files',
    },
    {
      title: '交付产物',
      state: `${finishedRuns} 次完成`,
      description: '查看历史运行、工具轨迹、诊断信息和导出的 Excel、Word、Markdown 文件。',
      action: '任务历史',
      path: '/runs',
    },
  ]

  return (
    <ChatFrame>
      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">Hermes Agent 工作台</p>
            <h1>从模型配置到交付产物的完整工作台</h1>
            <p>
              主路径是配置模型、进入聊天、挂载资料、观察工具执行，最后拿到可下载产物和可复制诊断。
            </p>
          </div>
          <div className="header-actions">
            <button type="button" className="secondary-button" onClick={() => navigate('/settings')}>
              模型设置
            </button>
            <button type="button" className="primary-button" onClick={() => navigate('/')}>
              开始对话
            </button>
          </div>
        </header>

        <section className="panel workbench-flow-panel" aria-label="工作台闭环">
          <div className="panel-header">
            <div>
              <p className="eyebrow">工作流</p>
              <h2>一条主线完成任务</h2>
            </div>
          </div>
          <div className="workbench-flow-grid">
            {flowSteps.map((step, index) => (
              <article key={step.title} className="workbench-flow-card">
                <div className="workbench-flow-index">{index + 1}</div>
                <div>
                  <div className="workbench-flow-title">
                    <strong>{step.title}</strong>
                    <small>{step.state}</small>
                  </div>
                  <p>{step.description}</p>
                  <button type="button" className="secondary-button" onClick={() => navigate(step.path)}>
                    {step.action}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="metric-grid">
          <MetricCard label="运行数" value={String(runs.length)} helper="全部已记录的智能体运行。" />
          <MetricCard label="已完成" value={String(finishedRuns)} helper="已经产出最终回答的运行。" />
          <MetricCard label="当前模型" value={currentModel || '未选择'} helper={aiConfig?.provider || '可在设置页选择模型提供方。'} />
          <MetricCard label="记忆" value={String(memories.length)} helper="可复用的用户和工作台上下文。" />
          <MetricCard label="文件" value={String(files.length)} helper="可附加到运行中的参考资料。" />
          <MetricCard
            label="Hermes"
            value={hermesMonitor?.connected ? '在线' : '离线'}
            helper={hermesMonitor?.gateway_url || '可在设置页检查运行时连通性。'}
          />
        </section>

        <div className="content-grid two-column">
          <section className="panel">
            <RunComposer
              templates={templates}
              memories={memories}
              files={files}
              onCreated={(run) => navigate(`/runs/${run.id}`)}
            />
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">能力面板</p>
                <h2>当前已经接通的能力</h2>
              </div>
            </div>
            <div className="stack-list">
              <InfoRow label="运行编排" value="基于 Hermes 的逐步执行循环，支持工具调用和步骤持久化。" />
              <InfoRow label="工作流实验室" value="提供多智能体蓝图界面，可检查 analyzer、planner、writer、reviewer 等流水线。" />
              <InfoRow label="工具注册表" value={`${tools.length} 个已注册工具，支持模板级白名单控制。`} />
              <InfoRow label="技能清单" value={`已发现 ${hermesSkills.length} 个本地技能文件。`} />
              <InfoRow label="记忆模型" value={`有 ${memories.filter((memory) => memory.pinned).length} 条置顶记忆，可直接附加到新运行。`} />
              <InfoRow label="文件工作区" value={`已上传 ${files.length} 个文件，可附加到运行，也可直接从产物中打开。`} />
              <InfoRow label="API 模型" value="模板、运行、工具、记忆、流式执行和运行详情都已经作为一等接口暴露。" />
            </div>
          </section>
        </div>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">最近</p>
              <h2>最新运行</h2>
            </div>
            <button type="button" className="secondary-button" onClick={() => navigate('/runs')}>
              查看全部
            </button>
          </div>

          <div className="run-card-grid">
            {recentRuns.map((run) => (
              <button
                key={run.id}
                type="button"
                className="run-card"
                onClick={() => navigate(`/runs/${run.id}`)}
              >
                <div className="run-card-top">
                  <RunStatusBadge status={run.status} />
                  <small>{run.agent?.name || '默认运行时'}</small>
                </div>
                <h3>{run.task}</h3>
                <p>{run.answer_preview || run.error || '等待执行。'}</p>
              </button>
            ))}
            {!recentRuns.length ? <EmptyInline text="还没有任务历史。先用上面的编排器创建第一个任务吧。" /> : null}
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

function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <p>{value}</p>
    </div>
  )
}

function EmptyInline({ text }) {
  return <div className="empty-inline">{text}</div>
}
