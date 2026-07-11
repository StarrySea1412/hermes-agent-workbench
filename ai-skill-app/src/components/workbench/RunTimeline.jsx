import RunStatusBadge from './RunStatusBadge'

export default function RunTimeline({ steps = [], isStreaming = false }) {
  if (!steps.length) {
    return (
      <div className="empty-panel">
        <strong>还没有步骤。</strong>
        <p>当运行开始规划和调用工具后，时间线会显示在这里。</p>
      </div>
    )
  }

  return (
    <div className="timeline-list">
      {steps.map((step) => (
        <article key={step.id || `${step.order}-${step.type}`} className="timeline-item">
          <div className="timeline-index">{String(step.order).padStart(2, '0')}</div>
          <div className="timeline-body">
            <div className="timeline-header">
              <div>
                <strong>{formatStepType(step.type)}</strong>
                {step.tool_name ? <span className="timeline-meta">{step.tool_name}</span> : null}
              </div>
              <RunStatusBadge status={step.status === 'error' ? 'failed' : step.status === 'ok' ? 'done' : step.status} />
            </div>

            {step.thought ? <p className="timeline-thought">{step.thought}</p> : null}
            {step.tool_args && Object.keys(step.tool_args).length ? <JsonBlock title="参数" value={step.tool_args} /> : null}
            {step.tool_result ? <JsonBlock title="结果" value={step.tool_result} /> : null}
            {step.content?.answer ? <TextBlock title="回答" value={step.content.answer} /> : null}
            {step.content?.message ? <TextBlock title="消息" value={step.content.message} /> : null}
            {step.content?.task ? <TextBlock title="任务" value={step.content.task} /> : null}
          </div>
        </article>
      ))}

      {isStreaming ? (
        <div className="timeline-streaming">
          <span className="stream-dot" />
          <small>正在持续接收执行事件...</small>
        </div>
      ) : null}
    </div>
  )
}

function JsonBlock({ title, value }) {
  return (
    <div className="timeline-block">
      <span>{title}</span>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  )
}

function TextBlock({ title, value }) {
  return (
    <div className="timeline-block">
      <span>{title}</span>
      <p>{value}</p>
    </div>
  )
}

function formatStepType(type) {
  switch (type) {
    case 'plan':
      return '计划'
    case 'tool_call':
      return '工具调用'
    case 'tool_result':
      return '工具结果'
    case 'answer':
      return '最终回答'
    case 'error':
      return '错误'
    default:
      return type || '步骤'
  }
}
