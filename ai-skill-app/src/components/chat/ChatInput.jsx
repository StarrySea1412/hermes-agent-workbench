import { useState } from 'react'
import Icon from '../Icon'
import FileUploader from './FileUploader'

export default function ChatInput({ disabled, running, onStop, onSend, onFiles, hero = false }) {
  const [value, setValue] = useState('')

  const submit = () => {
    const content = value.trim()
    if (!content || disabled) return
    setValue('')
    onSend(content)
  }

  return (
    <div className={`chat-input-shell ${hero ? 'hero' : ''}`}>
      <div className="chat-input-field">
        <textarea
          value={value}
          disabled={disabled}
          placeholder="交给 Hermes 一个任务…"
          rows={hero ? 2 : undefined}
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
        {running ? (
          <button
            type="button"
            className="send-btn stop"
            onClick={onStop}
            title="停止生成"
          >
            <Icon name="stop" size={13} strokeWidth={2} />
            停止
          </button>
        ) : (
          <button
            type="button"
            className="send-btn"
            disabled={disabled || !value.trim()}
            onClick={submit}
            title="发送 (Enter)"
          >
            发送
            <Icon name="arrowUp" size={13} strokeWidth={2} />
          </button>
        )}
      </div>
    </div>
  )
}
