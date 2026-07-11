import { useState } from 'react'
import FileUploader from './FileUploader'

const quickActions = [
  '规划任务',
  '检查问题',
  '生成产物',
  '整理资料',
]

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
      <div className="composer-chips">
        {quickActions.map((action) => (
          <button
            key={action}
            type="button"
            disabled={disabled}
            onClick={() => setValue(buildPrompt(action))}
          >
            {action}
          </button>
        ))}
      </div>
      <div className="chat-input-field">
        <textarea
          value={value}
          disabled={disabled}
          placeholder="交给 Hermes 一个任务，比如：把这个项目改成更像 agent 工程师工作台..."
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
          {onFiles ? <FileUploader disabled={disabled} onFiles={onFiles} /> : null}
          <span>任务上下文</span>
          <span>资料记忆</span>
          <span>工具执行</span>
        </div>
        <button type="button" className="send-btn" disabled={disabled || !value.trim()} onClick={submit}>
          {disabled ? '运行中' : '运行'}
        </button>
      </div>
    </div>
  )
}

function buildPrompt(action) {
  const prompts = {
    规划任务: '请把我的目标拆成一个 agent 可执行计划：目标、上下文、步骤、风险、需要的工具和预期产物。',
    检查问题: '请检查当前项目体验，指出影响 Hermes 聊天、资料处理和工具执行的问题，并按优先级给出修改顺序。',
    生成产物: '请根据当前对话和资料生成可交付产物，并说明产物结构、关键假设和下一步需要确认的内容。',
    整理资料: '请读取我上传的资料，提炼目标、约束、事实依据、风险点和可以直接执行的下一步。',
  }
  return prompts[action] || action
}
