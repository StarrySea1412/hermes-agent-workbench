import { useEffect, useId, useRef, useState } from 'react'
import Icon from './Icon'

// 液态玻璃风格下拉选择器：替代原生 <select> 的粗糙观感。
// 支持键盘导航（方向键/回车/Escape）、点击外部关闭、空间不足时向上翻转。
export default function GlassSelect({
  value,
  onChange,
  options,
  placeholder = '请选择',
  ariaLabel,
  disabled = false,
  className = '',
}) {
  const normalized = options.map((option) =>
    typeof option === 'string' ? { value: option, label: option } : option,
  )
  const current = normalized.find((option) => option.value === value)

  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [dropUp, setDropUp] = useState(false)
  const rootRef = useRef(null)
  const listRef = useRef(null)
  const listboxId = useId()

  const openMenu = () => {
    if (disabled) return
    const selectedIndex = normalized.findIndex((option) => option.value === value)
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0)
    const rect = rootRef.current?.getBoundingClientRect()
    if (rect) {
      const below = window.innerHeight - rect.bottom
      const above = rect.top
      setDropUp(below < 300 && above > below)
    }
    setOpen(true)
  }

  const select = (option) => {
    onChange?.(option.value)
    setOpen(false)
    rootRef.current?.querySelector('button')?.focus()
  }

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  // 打开后把当前项滚进可视区
  useEffect(() => {
    if (!open || activeIndex < 0) return
    listRef.current?.querySelector(`[data-index="${activeIndex}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [open, activeIndex])

  const onKeyDown = (event) => {
    if (disabled) return
    if (!open) {
      if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) {
        event.preventDefault()
        openMenu()
      }
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      setOpen(false)
      return
    }
    if (event.key === 'Tab') {
      setOpen(false)
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => {
        if (!normalized.length) return -1
        const delta = event.key === 'ArrowDown' ? 1 : -1
        return (index + delta + normalized.length) % normalized.length
      })
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      const option = normalized[activeIndex]
      if (option) select(option)
    }
    if (event.key === 'Home') {
      event.preventDefault()
      setActiveIndex(0)
    }
    if (event.key === 'End') {
      event.preventDefault()
      setActiveIndex(normalized.length - 1)
    }
  }

  return (
    <div
      ref={rootRef}
      className={`glass-select ${open ? 'open' : ''} ${dropUp ? 'drop-up' : ''} ${className}`}
      onKeyDown={onKeyDown}
    >
      <button
        type="button"
        className="glass-select-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-label={ariaLabel}
        onClick={() => (open ? setOpen(false) : openMenu())}
      >
        <span className={`glass-select-value ${current ? '' : 'placeholder'}`}>
          {current?.label || placeholder}
        </span>
        <span className="glass-select-chevron" aria-hidden="true">
          <Icon name="chevron" size={13} />
        </span>
      </button>

      {open ? (
        <ul className="glass-select-pop" role="listbox" id={listboxId} ref={listRef} tabIndex={-1}>
          {normalized.map((option, index) => (
            <li key={option.value}>
              <button
                type="button"
                role="option"
                data-index={index}
                aria-selected={option.value === value}
                className={`glass-select-option ${option.value === value ? 'selected' : ''} ${index === activeIndex ? 'active' : ''}`}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => select(option)}
              >
                <span className="glass-select-option-label">{option.label}</span>
                {option.value === value ? (
                  <span className="glass-select-check" aria-hidden="true">
                    <Icon name="check" size={13} />
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
