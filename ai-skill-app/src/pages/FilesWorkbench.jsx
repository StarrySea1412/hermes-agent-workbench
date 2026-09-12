import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteFile, listFiles, resolveFileUrl, uploadFiles } from '../api/files'
import ChatFrame from '../components/chat/ChatFrame'

export default function FilesWorkbench() {
  const inputRef = useRef(null)
  const queryClient = useQueryClient()
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
    <ChatFrame>
      <main className="files-main">
        <header className="projects-header">
          <div>
            <p className="eyebrow">文件</p>
            <h1>参考资料库</h1>
            <p>文件上传一次即可反复附加到会话：doc_parse 负责读取内容，导出结果在工作台直接打开。</p>
          </div>
          <button type="button" className="primary-button" onClick={() => inputRef.current?.click()}>
            上传文件
          </button>
        </header>

        <section className="files-stats" aria-label="文件统计">
          <div className="files-stat"><span>文件数</span><strong>{files.length}</strong></div>
          <div className="files-stat"><span>可解析</span><strong>{parseReadyCount}</strong></div>
          <div className="files-stat"><span>存储占用</span><strong>{formatBytes(totalBytes)}</strong></div>
          <div className="files-stat"><span>最近上传</span><strong>{latestUpload}</strong></div>
        </section>

        <div className="files-grid">
          <section className="files-panel">
            <form className="template-editor" onSubmit={handleSubmit}>
              <div className="panel-header">
                <h2>添加参考资料</h2>
                <small>PDF · Word · 文本 · Markdown</small>
              </div>

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
                    : '上传到共享参考工作区，所有会话可用'}
                </small>
              </div>

              {selectedFiles.length ? (
                <div className="chip-list">
                  {selectedFiles.map((file) => (
                    <code key={`${file.name}-${file.size}`}>{file.name}</code>
                  ))}
                </div>
              ) : null}

              <label className="field">
                <span>说明</span>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="可选说明，描述这些文件对后续运行的价值。"
                />
              </label>

              {notice ? (
                <div className={`panel-notice ${uploadMutation.isError || deleteMutation.isError ? 'error' : ''}`}>
                  {notice}
                </div>
              ) : null}

              <div className="editor-actions">
                <button type="submit" className="primary-button" disabled={uploadMutation.isPending || !selectedFiles.length}>
                  {uploadMutation.isPending ? '上传中...' : '上传文件'}
                </button>
              </div>
            </form>
          </section>

          <section className="files-panel">
            <div className="panel-header">
              <h2>可用文件</h2>
              <small>{files.length ? `${files.length} 个文件` : '暂无'}</small>
            </div>

            <div className="file-list">
              {files.map((file) => (
                <article key={file.id} className="file-item">
                  <div className="files-file-main">
                    <strong>{file.original_name}</strong>
                    <span className="files-file-meta">
                      {[file.file_type?.toUpperCase() || 'FILE', file.file_size_display || formatBytes(file.file_size || 0), formatDate(file.created_at)]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                    <p className="files-file-desc">{file.description || '暂无说明。'}</p>
                  </div>
                  <div className="files-file-actions">
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
                </article>
              ))}

              {!files.length ? (
                <div className="empty-projects">还没有文件。先上传参考资料，再在会话里用“添加资料”引用它们。</div>
              ) : null}
            </div>
          </section>
        </div>
      </main>
    </ChatFrame>
  )
}

function formatBytes(size) {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString()
}

function formatShortDate(value) {
  if (!value) return '暂无'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString()
}
