import { useState } from 'react'
import Icon from '../Icon'
import FileUploader from './FileUploader'

export default function ChatInput({ disabled, onSend, onFiles }) {
  const [value, setValue] = useState('')

  const submit = () => {
    const content = value.trim()
    if (!content || disabled) return
    setValue('')
    onSend(content)
  }

  return (
    <div className="chat-input-shell">
      <div className="chat-input-field">
        <textarea
          value={value}
          disabled={disabled}
          placeholder="交给 Hermes 一个任务…"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
        />
      </div>
      <div className="chat-input-footer">
        <div className="composer-left-actions">
          {onFiles ? <FileUploader disabled={disabled} onFiles={onFiles} withIcon /> : null}
          <span className="composer-hint">Enter 发送 / Shift+Enter 换行</span>
        </div>
        <button
          type="button"
          className="send-btn"
          disabled={disabled || !value.trim()}
          onClick={submit}
          title={disabled ? '运行中' : '发送 (Enter)'}
        >
          {disabled ? '运行中' : (
            <>
              发送
              <Icon name="arrowUp" size={13} strokeWidth={2} />
            </>
          )}
        </button>
      </div>
    </div>
  )
}
