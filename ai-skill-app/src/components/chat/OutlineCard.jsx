export default function OutlineCard({ project }) {
  const outline = Array.isArray(project?.outline) ? project.outline : []

  return (
    <section className="outline-card">
      <div>
        <p className="eyebrow">结构</p>
        <h2>{project?.title || '新的工作空间'}</h2>
        <span>{formatProjectType(project?.project_type)}</span>
      </div>

      <div className="outline-list">
        {outline.length ? outline.slice(0, 8).map((item, index) => (
          <div className="outline-item" key={`${item}-${index}`}>
            <b>{String(index + 1).padStart(2, '0')}</b>
            <span>{item}</span>
          </div>
        )) : (
          <p className="muted">随着对话推进，结构草案会在这里逐步沉淀下来，方便你继续整理和导出。</p>
        )}
      </div>
    </section>
  )
}

function formatProjectType(type) {
  if (type === 'presentation') return '演示导向'
  if (type === 'report') return '文档导向'
  if (type === 'mixed') return '混合交付'
  return '通用工作流'
}
