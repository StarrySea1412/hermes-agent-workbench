import { useMemo, useState } from 'react'

export default function DeckPreview({ project }) {
  const slides = useMemo(() => buildSlides(project), [project])
  const [activeIndex, setActiveIndex] = useState(0)
  const activeSlide = slides[activeIndex] || slides[0]

  if (!project?.id) {
    return (
      <section className="deck-preview">
        <p className="eyebrow">Preview</p>
        <h2>等待生成内容</h2>
        <p className="muted">发送需求后，这里会展示 PPT 页面预览。</p>
      </section>
    )
  }

  if (!slides.length) {
    return (
      <section className="deck-preview">
        <p className="eyebrow">Preview</p>
        <h2>{project.title || 'PPT 预览'}</h2>
        <p className="muted">当前项目还没有可预览内容。请先让 AI 生成 PPT 大纲或正文。</p>
      </section>
    )
  }

  return (
    <section className="deck-preview">
      <div className="preview-header">
        <div>
          <p className="eyebrow">Preview</p>
          <h2>{project.title || 'PPT 预览'}</h2>
        </div>
        <span>{activeIndex + 1}/{slides.length}</span>
      </div>

      <div className="slide-canvas">
        <div className="slide-kicker">Slide {String(activeIndex + 1).padStart(2, '0')}</div>
        <h3>{activeSlide.title}</h3>
        {activeSlide.subtitle && <p className="slide-subtitle">{activeSlide.subtitle}</p>}
        <ul>
          {activeSlide.bullets.slice(0, 5).map((bullet, index) => (
            <li key={`${bullet}-${index}`}>{bullet}</li>
          ))}
        </ul>
      </div>

      <div className="slide-controls">
        <button type="button" disabled={activeIndex === 0} onClick={() => setActiveIndex((index) => Math.max(0, index - 1))}>
          上一页
        </button>
        <button type="button" disabled={activeIndex >= slides.length - 1} onClick={() => setActiveIndex((index) => Math.min(slides.length - 1, index + 1))}>
          下一页
        </button>
      </div>

      <div className="slide-strip">
        {slides.map((slide, index) => (
          <button
            type="button"
            key={`${slide.title}-${index}`}
            className={index === activeIndex ? 'active' : ''}
            onClick={() => setActiveIndex(index)}
          >
            <b>{String(index + 1).padStart(2, '0')}</b>
            <span>{slide.title}</span>
          </button>
        ))}
      </div>
    </section>
  )
}

function buildSlides(project) {
  if (!project) return []
  const slides = []
  const title = project.title || '未命名 PPT'
  const description = project.description || ''

  slides.push({
    title,
    subtitle: description || 'AI 生成演示文稿',
    bullets: ['主题确认', '结构梳理', '内容生成', '导出交付'],
  })

  const outline = Array.isArray(project.outline) ? project.outline.filter(Boolean) : []
  if (outline.length) {
    slides.push({
      title: '目录',
      subtitle: '',
      bullets: outline.slice(0, 8).map(cleanLine),
    })
  }

  const sections = splitSections(project.final_content)
  if (sections.length) {
    sections.slice(0, 18).forEach((section) => slides.push(section))
  } else {
    outline.slice(0, 12).forEach((item, index) => {
      slides.push({
        title: cleanLine(item) || `第 ${index + 1} 页`,
        subtitle: '',
        bullets: ['补充页面观点', '补充关键素材', '补充演讲备注'],
      })
    })
  }

  return dedupeSlides(slides).slice(0, 20)
}

function splitSections(text = '') {
  const sections = []
  let current = null

  text.split('\n').forEach((line) => {
    const cleaned = cleanLine(line)
    if (!cleaned) return
    const isHeading = line.trim().startsWith('#') || /^第?\d+\s*[页章节、.]/.test(cleaned)

    if (isHeading) {
      if (current) sections.push(current)
      current = { title: cleaned, subtitle: '', bullets: [] }
      return
    }

    if (!current) current = { title: '核心内容', subtitle: '', bullets: [] }
    if (current.bullets.length < 6) current.bullets.push(cleaned)
  })

  if (current) sections.push(current)
  return sections.filter((section) => section.title || section.bullets.length)
}

function cleanLine(value = '') {
  return String(value)
    .replace(/^#+\s*/, '')
    .replace(/^[-*•]\s*/, '')
    .replace(/^\d+\s*[.)、]\s*/, '')
    .replace(/\*\*/g, '')
    .trim()
}

function dedupeSlides(slides) {
  const seen = new Set()
  return slides.filter((slide) => {
    const key = slide.title.toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}
