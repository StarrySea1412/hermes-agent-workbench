import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  createConversation,
  getProject,
  uploadProjectFiles,
} from '../../api/projects'
import ChatFrame from '../../components/chat/ChatFrame'
import ExportPanel from '../../components/chat/ExportPanel'
import OutlineCard from '../../components/chat/OutlineCard'
import './ChatShell.css'

export default function ProjectDetail() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [uploadStatus, setUploadStatus] = useState('')

  const { data: project, isLoading } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId)
  })

  const createMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      navigate(`/chat/${conversation.id}`)
    }
  })

  const continueProject = () => {
    if (!project) return
    createMutation.mutate({
      title: project.title,
      mode: 'chat',
      project_id: project.id
    })
  }

  const handleFiles = async (event) => {
    if (!event.target.files?.length) return

    setUploadStatus('正在上传资料...')
    try {
      await uploadProjectFiles(projectId, event.target.files)
      await queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      setUploadStatus('资料已更新。')
    } catch (error) {
      setUploadStatus(error.message || '上传失败')
    } finally {
      event.target.value = ''
    }
  }

  return (
    <ChatFrame>
      <main className="project-detail-main">
        {isLoading ? (
          <div className="loading-state">正在加载工作空间...</div>
        ) : (
          <>
            <header className="projects-header">
              <div>
                <p className="eyebrow">资料区</p>
                <h1>{project.title}</h1>
                <p>{project.description || '这里集中存放当前工作空间的结构、资料和可导出的阶段性成果。'}</p>
              </div>
              <button type="button" className="primary-button" onClick={continueProject}>继续聊天</button>
            </header>

            <div className="project-detail-grid">
              <OutlineCard project={project} />
              <ExportPanel project={project} />

              <section className="files-panel">
                <p className="eyebrow">资料</p>
                <h3>资料库</h3>
                <label className="file-uploader wide">
                  <input type="file" multiple accept=".pdf,.doc,.docx,.txt,.md" onChange={handleFiles} />
                  <span>上传更多资料</span>
                </label>

                {uploadStatus ? <div className="panel-notice">{uploadStatus}</div> : null}

                <div className="file-list">
                  {project.project_files?.map((item) => (
                    <div key={item.id} className="file-item">
                      <strong>{item.file.original_name}</strong>
                      <span>{item.file.file_size_display}</span>
                    </div>
                  ))}

                  {!project.project_files?.length ? <p className="muted">暂无资料。</p> : null}
                </div>
              </section>
            </div>
          </>
        )}
      </main>
    </ChatFrame>
  )
}
