import { resolveFileUrl } from '../../api/files'

export default function ArtifactList({ artifacts = [] }) {
  if (!artifacts.length) {
    return (
      <div className="empty-panel">
        <strong>还没有产物。</strong>
        <p>当运行记录下计划、工具结果或最终回答后，产物会显示在这里。</p>
      </div>
    )
  }

  return (
    <div className="artifact-list">
      {artifacts.map((artifact) => {
        const links = collectArtifactLinks(artifact.payload)
        const summary = summarizeArtifactPayload(artifact.payload, artifact.artifact_type)
        return (
          <article key={artifact.key} className="artifact-card">
            <div className="artifact-card-top">
              <div>
                <strong>{artifact.title || artifact.key}</strong>
                <small>{artifact.key}</small>
              </div>
              <span className={`artifact-type-pill ${artifact.artifact_type || 'json'}`}>
                {formatArtifactType(artifact.artifact_type)}
              </span>
            </div>
            {summary ? <p className="artifact-summary">{summary}</p> : null}
            {links.length ? (
              <div className="artifact-links">
                {links.map((link) => (
                  <article key={`${artifact.key}-${link.url}-${link.label}`} className="artifact-file-card">
                    <span>{formatArtifactFormat(link.format)}</span>
                    <div>
                      <strong>{link.label}</strong>
                      <small>{link.preview || formatArtifactHelper(link.format)}</small>
                    </div>
                    <a
                      className="artifact-link"
                      href={resolveFileUrl(link.url)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      打开
                    </a>
                  </article>
                ))}
              </div>
            ) : null}
            <details className="artifact-raw">
              <summary>查看原始数据</summary>
              <pre>{JSON.stringify(artifact.payload, null, 2)}</pre>
            </details>
          </article>
        )
      })}
    </div>
  )
}

function formatArtifactType(value) {
  switch (value) {
    case 'task':
      return '任务'
    case 'answer':
      return '回答'
    case 'tool_result':
      return '工具结果'
    case 'plan':
      return '计划'
    case 'error':
      return '错误'
    default:
      return value || '产物'
  }
}

function formatArtifactFormat(value) {
  const format = String(value || '').toLowerCase()
  if (format === 'xlsx') return 'Excel'
  if (format === 'docx') return 'Word'
  if (format === 'md' || format === 'markdown') return 'MD'
  if (format === 'pdf') return 'PDF'
  if (format === 'txt') return 'TXT'
  return format ? format.toUpperCase() : 'FILE'
}

function formatArtifactHelper(value) {
  const format = String(value || '').toLowerCase()
  if (format === 'xlsx') return '可下载的表格文件。'
  if (format === 'docx') return '可下载的文档文件。'
  if (format === 'md' || format === 'markdown') return '可继续编辑的 Markdown 文件。'
  return '运行过程中生成的文件产物。'
}

function summarizeArtifactPayload(payload, artifactType) {
  if (typeof payload === 'string') return truncate(payload, 180)
  if (!payload || typeof payload !== 'object') return ''

  if (payload.answer) return truncate(payload.answer, 180)
  if (payload.error) return truncate(payload.error, 180)
  if (payload.summary) return truncate(payload.summary, 180)
  if (payload.text) return truncate(payload.text, 180)
  if (payload.message) return truncate(payload.message, 180)
  if (payload.filename) return `已生成文件：${payload.filename}`
  if (Array.isArray(payload.results)) return `包含 ${payload.results.length} 条结果。`
  if (artifactType === 'tool_result') return '工具执行结果已保存。'
  if (artifactType === 'task') return '任务输入和运行参数已保存。'
  return ''
}

function collectArtifactLinks(payload) {
  const links = []
  const seen = new Set()

  visit(payload)
  return links

  function visit(node) {
    if (!node) return
    if (Array.isArray(node)) {
      node.forEach(visit)
      return
    }
    if (typeof node !== 'object') return

    const rawUrl = node.file_url || node.url
    const isFileLike = Boolean(node.file_url || (node.url && (node.file_id || node.filename || node.original_name)))
    if (isFileLike && typeof rawUrl === 'string' && rawUrl.trim()) {
      const key = `${rawUrl}|${node.file_id || ''}`
      if (!seen.has(key)) {
        seen.add(key)
        links.push({
          label: node.filename || node.original_name || (node.file_id ? `文件 #${node.file_id}` : '打开文件'),
          url: rawUrl,
          format: node.format || node.file_type || inferFormat(node.filename || node.original_name || rawUrl),
          preview: node.preview || node.description || node.text,
        })
      }
    }

    Object.values(node).forEach(visit)
  }
}

function inferFormat(value) {
  const match = String(value || '').match(/\.([a-z0-9]+)(?:$|[?#])/i)
  return match?.[1] || ''
}

function truncate(value, maxLength) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text
}
