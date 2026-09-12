import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listAgentTemplates, listAgentRuns } from '../api/agents'
import ChatFrame from '../components/chat/ChatFrame'
import { useHermesSkillDetail, useHermesSkills } from '../hooks/useAIConfig'

export default function SkillsCatalog() {
  const { data: runs = [] } = useQuery({ queryKey: ['agentRuns'], queryFn: listAgentRuns })
  const { data: templates = [] } = useQuery({ queryKey: ['agentTemplates'], queryFn: listAgentTemplates })
  const { data: skills = [] } = useHermesSkills()
  const [requestedSkillPath, setRequestedSkillPath] = useState('')
  const selectedSkillPath = skills.some((skill) => skill.path === requestedSkillPath)
    ? requestedSkillPath
    : skills[0]?.path || ''

  const detailQuery = useHermesSkillDetail(selectedSkillPath)

  const templateBySkill = useMemo(() => {
    const map = new Map()
    templates.forEach((template) => {
      if (!template.skill) return
      const current = map.get(template.skill) || []
      current.push(template.name)
      map.set(template.skill, current)
    })
    return map
  }, [templates])

  const selectedSkill = detailQuery.data || null
  const selectedTemplateNames = selectedSkill ? (templateBySkill.get(selectedSkill.path) || []) : []

  return (
    <ChatFrame>
      <main className="page">
        <header className="page-header">
          <div>
            <p className="eyebrow">技能</p>
            <h1>本地技能清单</h1>
            <p>检查 Hermes 可加载的技能文件，查看哪些模板引用了它们，并直接阅读影响运行行为的提示词正文。</p>
          </div>
        </header>

        <section className="metric-grid">
          <MetricCard label="技能数" value={String(skills.length)} helper="已发现的本地技能文件。" />
          <MetricCard label="模板映射" value={String([...templateBySkill.keys()].length)} helper="被模板引用的技能路径数量。" />
          <MetricCard label="模板数" value={String(templates.length)} helper="目录中的全部智能体定义。" />
          <MetricCard label="运行数" value={String(runs.length)} helper="可使用这些模板执行的现有运行。" />
        </section>

        <div className="content-grid detail-grid">
          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">目录</p>
                <h2>技能文件</h2>
              </div>
            </div>

            <div className="template-list interactive">
              {skills.map((skill) => (
                <button
                  key={skill.path}
                  type="button"
                  className={`template-card selectable ${selectedSkillPath === skill.path ? 'selected' : ''}`}
                  onClick={() => setRequestedSkillPath(skill.path)}
                >
                  <div className="template-card-top">
                    <strong>{skill.title || skill.name}</strong>
                    <small>{skill.source}</small>
                  </div>
                  <p>{skill.description || '技能元数据中没有提供描述。'}</p>
                  <code>{skill.path}</code>
                </button>
              ))}
              {!skills.length ? <div className="empty-inline">Hermes 技能加载器尚未发现技能文件。</div> : null}
            </div>
          </section>

          <aside className="detail-rail">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">详情</p>
                  <h2>技能元数据</h2>
                </div>
              </div>

              {detailQuery.isLoading ? <div className="loading-panel">正在加载技能详情...</div> : null}

              {selectedSkill ? (
                <>
                  <div className="stack-list">
                    <InfoRow label="标题" value={selectedSkill.title || selectedSkill.name} />
                    <InfoRow label="路径" value={selectedSkill.path} />
                    <InfoRow label="分组" value={selectedSkill.group || 'project'} />
                    <InfoRow label="来源" value={selectedSkill.source || 'project'} />
                    <InfoRow label="关联模板" value={selectedTemplateNames.length ? selectedTemplateNames.join(', ') : '还没有模板映射'} />
                    <InfoRow label="描述" value={selectedSkill.description || '技能元数据中没有提供描述。'} />
                  </div>

                  <div className="chip-list">
                    {(selectedSkill.tags || []).length
                      ? selectedSkill.tags.map((tag) => <code key={tag}>{tag}</code>)
                      : <code>无标签</code>}
                  </div>

                  {selectedSkill.metadata && Object.keys(selectedSkill.metadata).length ? (
                    <div className="tool-card-section">
                      <span>Frontmatter</span>
                      <pre className="json-block">{JSON.stringify(selectedSkill.metadata, null, 2)}</pre>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="empty-panel">
                  <strong>尚未选择技能。</strong>
                  <p>请选择一个技能，查看它的运行时提示词正文和元数据。</p>
                </div>
              )}
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">提示词正文</p>
                  <h2>已加载的技能内容</h2>
                </div>
              </div>

              {selectedSkill?.body ? (
                <div className="answer-block">
                  <pre>{selectedSkill.body}</pre>
                </div>
              ) : (
                <div className="empty-panel">
                  <strong>没有可读正文。</strong>
                  <p>当前技能没有暴露可读取的提示词内容。</p>
                </div>
              )}
            </section>
          </aside>
        </div>
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
