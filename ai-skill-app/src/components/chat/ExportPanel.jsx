import { useState } from 'react'
import { exportProjectDocx, exportProjectMarkdown } from '../../api/projects'

export default function ExportPanel({ project }) {
  const [status, setStatus] = useState('')
  const hasContent = Boolean(project?.final_content || project?.outline?.length)

  const download = async (format) => {
    if (!project?.id || !hasContent) return

    setStatus(format === 'docx' ? '正在生成 Word...' : '正在生成 Markdown...')

    try {
      const exporter = format === 'docx' ? exportProjectDocx : exportProjectMarkdown
      const { blob, filename } = await exporter(project.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
      setStatus('导出已开始，请查看浏览器下载。')
    } catch (error) {
      setStatus(error.message || '导出失败')
    }
  }

  return (
    <section className="export-panel">
      <p className="eyebrow">导出</p>
      <h3>导出成果</h3>
      <p>{hasContent ? '把当前工作空间里的结构和正文导出，继续进入交付或协作环节。' : '先生成内容，再导出可编辑成果。'}</p>
      <div className="export-actions">
        <button type="button" disabled={!project?.id || !hasContent} onClick={() => download('docx')}>
          下载 Word
        </button>
        <button type="button" disabled={!project?.id || !hasContent} onClick={() => download('markdown')}>
          下载 Markdown
        </button>
      </div>
      {status ? <span>{status}</span> : null}
    </section>
  )
}
