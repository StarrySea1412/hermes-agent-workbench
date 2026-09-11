import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listAgentRuns } from '../api/agents'
import { deleteFile, listFiles, resolveFileUrl, uploadFiles } from '../api/files'
import Sidebar from '../components/workbench/Sidebar'
import { useAuth } from '../hooks/useAuth'

export default function FilesWorkbench() {
  const inputRef = useRef(null)
  const queryClient = useQueryClient()
  const { user, logout, isLocalMode } = useAuth()
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: files = [] } = useQuery({ queryKey: ['files'], queryFn: listFiles })
  const [selectedFiles, setSelectedFiles] = useState([])
  const [description, setDescription] = useState('')
  const [notice, setNotice] = useState('')
  const [deletingId, setDeletingId] = useState(null)

  const uploadMutation = useMutation({
    mutationFn: ({ items, note }) => uploadFiles(items, note),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['files'] })
      setNotice(`已上传 ${result.length} 个文件。`)
      setSelectedFiles([])
      setDescription('')
      if (inputRef.current) inputRef.current.value = ''
    },
    onError: (error) => {
      setNotice(error.message || '无法上传文件。')
    }
  })

  const deleteMutation = useMutation({
    mutationFn: async (fileId) => {
      setDeletingId(fileId)
      return deleteFile(fileId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['files'] })
      setNotice('文件已删除。')
    },
    onError: (error) => {
      setNotice(error.message || '无法删除文件。')
    },
    onSettled: () => {
      setDeletingId(null)
    }
  })

  const totalBytes = files.reduce((sum, file) => sum + (file.file_size || 0), 0)
  const parseReadyCount = files.filter((file) => ['pdf', 'docx', 'doc', 'txt', 'md'].includes(file.file_type)).length
  const latestUpload = files[0]?.created_at ? formatShortDate(files[0].created_at) : '暂无'

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!selectedFiles.length) return
    setNotice('')
    uploadMutation.mutate({ items: selectedFiles, note: description })
  }

  return (
    <div className="workbench-shell">
      <Sidebar runs={runs} user={user} onLogout={logout} isLocalMode={isLocalMode} />

      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">文件</p>
            <h1>参考文件工作区</h1>
            <p>文件上传一次即可反复附加到运行中，用 doc_parse 读取，并直接在工作台中打开导出结果。</p>
          </div>
        </header>

        <section className="metric-grid">
          <MetricCard label="文件数" value={String(files.length)} helper="全部已上传和已生成文件。" />
          <MetricCard label="可解析" value={String(parseReadyCount)} helper="可由 doc_parse 读取的文件数量。" />
          <MetricCard label="存储占用" value={formatBytes(totalBytes)} helper="当前工作区文件体积。" />
          <MetricCard label="最近上传" value={latestUpload} helper="最近加入的参考文件。" />
        </section>

        <div className="content-grid two-column">
          <section className="panel">
            <form className="template-editor" onSubmit={handleSubmit}>
              <div className="panel-header">
                <div>
                  <p className="eyebrow">上传</p>
                  <h2>添加参考资料</h2>
                </div>
              </div>

              <div className="field">
                <span>文件</span>
                <div className="file-picker-row">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => inputRef.current?.click()}
                  >
                    选择文件
                  </button>
                  <input
                    ref={inputRef}
                    type="file"
                    multiple
                    accept=".pdf,.docx,.doc,.txt,.md"
                    className="visually-hidden-input"
                    onChange={(event) => setSelectedFiles(Array.from(event.target.files || []))}
                  />
                  <small className="file-picker-hint">
                    {selectedFiles.length
                      ? `已选择 ${selectedFiles.length} 个文件`
                      : '支持 PDF、Word、文本、Markdown'}
                  </small>
                </div>
              </div>

              {selectedFiles.length ? (
                <div className="chip-list">
                  {selectedFiles.map((file) => (
                    <code key={`${file.name}-${file.size}`}>{file.name}</code>
                  ))}
                </div>
              ) : (
                <div className="empty-inline">请选择一个或多个文件，上传到共享参考工作区。</div>
              )}

              <label className="field">
                <span>说明</span>
                <textarea
                  rows={5}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="可选说明，描述这些文件为什么对后续运行有价值。"
                />
              </label>

              {notice ? <div className={`panel-alert ${uploadMutation.isError || deleteMutation.isError ? 'error' : ''}`}>{notice}</div> : null}

              <div className="editor-actions">
                <button type="submit" className="primary-button" disabled={uploadMutation.isPending || !selectedFiles.length}>
                  {uploadMutation.isPending ? '上传中...' : '上传文件'}
                </button>
              </div>
            </form>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">目录</p>
                <h2>可用文件</h2>
              </div>
            </div>

            <div className="file-catalog">
              {files.map((file) => (
                <article key={file.id} className="file-card">
                  <div className="file-card-top">
                    <div>
                      <strong>{file.original_name}</strong>
                      <small>{formatFileMeta(file)}</small>
                    </div>
                  </div>
                  <p>{file.description || '暂无说明。'}</p>
                  <div className="file-card-footer">
                    <span>{formatDate(file.created_at)}</span>
                    <div className="editor-actions">
                      {file.file_url ? (
                        <a className="artifact-link" href={resolveFileUrl(file.file_url)} target="_blank" rel="noreferrer">
                          打开
                        </a>
                      ) : null}
                      <button
                        type="button"
                        className="secondary-button danger-button"
                        onClick={() => deleteMutation.mutate(file.id)}
                        disabled={deleteMutation.isPending && deletingId === file.id}
                      >
                        {deleteMutation.isPending && deletingId === file.id ? '删除中...' : '删除'}
                      </button>
                    </div>
                  </div>
                </article>
              ))}

              {!files.length ? <div className="empty-inline">还没有文件。先在这里上传资料，再从运行编排器里附加它们。</div> : null}
            </div>
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

function formatBytes(size) {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value) {
  if (!value) return '未知时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function formatShortDate(value) {
  if (!value) return '暂无'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString()
}

function formatFileMeta(file) {
  return [file.file_type?.toUpperCase() || 'FILE', file.file_size_display || formatBytes(file.file_size || 0)]
    .filter(Boolean)
    .join(' | ')
}
