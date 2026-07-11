export default function MemoryList({ memories = [] }) {
  if (!memories.length) {
    return (
      <div className="empty-panel">
        <strong>没有附加记忆。</strong>
        <p>你可以把已保存的上下文附加到运行中，或把最终回答沉淀为长期记忆。</p>
      </div>
    )
  }

  return (
    <div className="memory-list">
      {memories.map((memory) => (
        <article key={memory.id} className="memory-card">
          <div className="memory-card-top">
            <div>
              <strong>{memory.title}</strong>
              <small>{formatScope(memory.scope)}</small>
            </div>
            {memory.pinned ? <span className="memory-pill">已置顶</span> : null}
          </div>
          <p>{memory.content}</p>
          <div className="memory-card-footer">
            <span>{(memory.tags || []).length ? memory.tags.join(', ') : '无标签'}</span>
            <small>{formatDate(memory.updated_at || memory.created_at)}</small>
          </div>
        </article>
      ))}
    </div>
  )
}

function formatDate(value) {
  if (!value) return '暂无'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
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
