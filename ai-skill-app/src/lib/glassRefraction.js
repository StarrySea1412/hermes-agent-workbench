// 液态玻璃的指针折射：眩光光斑跟随鼠标在玻璃面板上滑动，
// 移入点亮、移出熄灭。全局一个委托监听，不必给每张卡片挂 handler。
const GLASS_SELECTOR = [
  '.panel',
  '.metric-card',
  '.run-card',
  '.template-card',
  '.timeline-item',
  '.home-highlight',
  '.project-card',
  '.export-panel',
  '.outline-card',
  '.files-panel',
  '.message-artifact-card',
  '.insight-panel',
  '.chat-input-field textarea',
  '[class*="loginCard"]',
].join(', ')

export function initGlassRefraction() {
  const onMove = (event) => {
    if (!(event.target instanceof Element)) return
    const card = event.target.closest(GLASS_SELECTOR)
    if (!card) return
    const rect = card.getBoundingClientRect()
    const x = ((event.clientX - rect.left) / rect.width) * 100
    const y = ((event.clientY - rect.top) / rect.height) * 100
    card.style.setProperty('--mx', `${x.toFixed(1)}%`)
    card.style.setProperty('--my', `${y.toFixed(1)}%`)
    card.classList.add('glass-hover')
  }

  const onOut = (event) => {
    if (!(event.target instanceof Element)) return
    const card = event.target.closest(GLASS_SELECTOR)
    if (!card) return
    if (event.relatedTarget instanceof Element && card.contains(event.relatedTarget)) return
    card.classList.remove('glass-hover')
  }

  document.addEventListener('pointermove', onMove, { passive: true })
  document.addEventListener('pointerout', onOut, true)
  return () => {
    document.removeEventListener('pointermove', onMove)
    document.removeEventListener('pointerout', onOut, true)
  }
}
