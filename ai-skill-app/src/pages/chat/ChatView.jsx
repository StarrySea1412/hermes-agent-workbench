import { useRef, useState, useSyncExternalStore } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import Icon from '../../components/Icon'
import { getHermesMonitor } from '../../api/aiConfig'
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  streamMessage,
  updateConversation,
  uploadProjectFiles,
} from '../../api/projects'
import ChatInput from '../../components/chat/ChatInput'
import ChatSidebar from '../../components/chat/ChatSidebar'
import InsightPanel from '../../components/chat/InsightPanel'
import MessageList from '../../components/chat/MessageList'
import { EmptyChatHero } from '../../components/chat/MessageList'
import { useAuth } from '../../hooks/useAuth'
import { useAIConfig } from '../../hooks/useAIConfig'
import {
  clearChatDraft,
  getChatDraftSnapshot,
  getChatNotice,
  setChatDraft,
  setChatNotice,
  setChatPending,
  setChatSending,
  subscribeChatDraft,
} from './chatDraftStore'
import './ChatShell.css'
import './ChatView.css'

function useChatDraft() {
  return useSyncExternalStore(subscribeChatDraft, getChatDraftSnapshot, getChatDraftSnapshot)
}

function useChatNotice() {
  return useSyncExternalStore(subscribeChatDraft, getChatNotice, () => '')
}

export default function ChatView() {
  const { convId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user, logout, isLocalMode } = useAuth()
  const { draft, pendingId, isSending } = useChatDraft()
  const [copyState, setCopyState] = useState('')
  const [runtimeOpen, setRuntimeOpen] = useState(false)
  const notice = useChatNotice()
  const { data: aiConfig } = useAIConfig()
  const abortRef = useRef(null)

  const { data: conversations = [] } = useQuery({
    queryKey: ['conversations'],
    queryFn: listConversations
  })

  // 网关当前的上游模型/渠道：消息元数据缺失时（如未配置用户级模型）由此兜底
  const { data: hermesMonitor } = useQuery({
    queryKey: ['hermesMonitor'],
    queryFn: () => getHermesMonitor(),
    refetchInterval: 60000,
    staleTime: 30000
  })

  const { data: conversation, isLoading } = useQuery({
    queryKey: ['conversation', convId],
    queryFn: () => getConversation(convId),
    enabled: Boolean(convId),
    retry: false
  })

  const messages = draft?.conversationId === String(convId)
    ? draft.messages
    : (conversation?.messages || [])
  const runtime = buildRuntimeSnapshot(conversation, messages, aiConfig)
  if (!runtime.modelName && hermesMonitor?.upstream_model) {
    runtime.modelName = hermesMonitor.upstream_model
    runtime.baseUrl = runtime.baseUrl || hermesMonitor.upstream_base_url || ''
  }

  const createMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      navigate(`/chat/${created.id}`)
    }
  })

  const deleteMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      queryClient.removeQueries({ queryKey: ['conversation', String(deletedId)] })
      if (String(deletedId) === String(convId)) {
        clearChatDraft()
        navigate('/', { replace: true })
      }
    }
  })

  const renameMutation = useMutation({
    mutationFn: ({ conversationId, title }) => renameConversation(conversationId, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (convId) {
        queryClient.invalidateQueries({ queryKey: ['conversation', String(convId)] })
      }
    }
  })

  const handleRenameConversation = (conversationId, title) => {
    const trimmed = String(title || '').trim()
    if (!trimmed || renameMutation.isPending) return
    renameMutation.mutate({ conversationId, title: trimmed })
  }

  const pinMutation = useMutation({
    mutationFn: ({ conversationId, isPinned }) =>
      updateConversation(conversationId, { is_pinned: isPinned }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
    }
  })

  const handlePinChat = (conversationId, isPinned) => {
    pinMutation.mutate({ conversationId, isPinned })
  }

  const handleExportMarkdown = () => {
    if (!messages.length) return
    const lines = [`# ${conversation?.title || '会话'}`, '', `> 导出时间：${new Date().toLocaleString()}`, '']
    for (const message of messages) {
      const role = message.role === 'user' ? '🙋 我' : '🤖 Hermes'
      lines.push(`## ${role}`, '', String(message.content || '').trim() || '（无内容）', '')
      const events = Array.isArray(message.metadata?.tool_events) ? message.metadata.tool_events : []
      if (events.length) {
        lines.push('**工具轨迹**', '')
        for (const event of events) {
          lines.push(`- ${event.name || '工具'}：${event.result_preview || event.status || ''}`)
        }
        lines.push('')
      }
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${(conversation?.title || '会话').slice(0, 40).replace(/[\\/:*?"<>|]/g, '')}.md`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  const createWorkspace = () => {
    createMutation.mutate({
      title: '新对话',
      mode: 'chat'
    })
  }

  const handleSend = async (content) => {
    const startedAt = Date.now()
    const userMessage = { id: `local-user-${Date.now()}`, role: 'user', content }
    const assistantId = `local-assistant-${Date.now()}`
    const initialMessages = [
      ...messages,
      userMessage,
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        metadata: {
          gateway: 'hermes',
          session_id: conversation?.session_id || null,
          model_name: aiConfig?.model_name || '',
          thoughts: [],
          tool_events: [],
          used_tools: [],
        }
      }
    ]

    setChatDraft({ conversationId: String(convId), messages: initialMessages })
    setChatPending(assistantId)
    setChatSending(true)
    setChatNotice('')

    const controller = new AbortController()
    abortRef.current = controller

    try {
      let targetConvId = convId
      if (!targetConvId || !conversation) {
        const created = await createConversation({
          title: content.slice(0, 40) || '新对话',
          mode: 'chat',
          description: content.slice(0, 120)
        })
        targetConvId = created.id
        setChatDraft({ conversationId: String(created.id), messages: initialMessages })
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
        navigate(`/chat/${created.id}`, { replace: true })
      }

      await streamMessage(targetConvId, { content }, {
        onStatus: (status) => {
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((message) => {
                if (message.id !== assistantId) return message
                return {
                  ...message,
                  metadata: {
                    ...(message.metadata || {}),
                    gateway: status.gateway || message.metadata?.gateway || 'hermes',
                    session_id: status.session_id || message.metadata?.session_id || conversation?.session_id || null,
                    mode: status.mode || message.metadata?.mode,
                    file_count: typeof status.file_count === 'number' ? status.file_count : message.metadata?.file_count,
                    tool_names: status.tool_names || message.metadata?.tool_names || [],
                    stage: status.stage || message.metadata?.stage,
                    status_message: status.message || message.metadata?.status_message || '',
                    status_diagnostic: status.diagnostic || message.metadata?.status_diagnostic || null,
                  }
                }
              })
            }
          })
          if (status.message) {
            setChatNotice(buildRuntimeNotice(status))
          }
        },
        onThought: (thought) => {
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((message) => {
                if (message.id !== assistantId) return message
                const previousThoughts = message.metadata?.thoughts || []
                return {
                  ...message,
                  metadata: {
                    ...(message.metadata || {}),
                    thoughts: [...previousThoughts, thought]
                  }
                }
              })
            }
          })
        },
        onThoughtDelta: (payload) => {
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((message) => {
                if (message.id !== assistantId) return message
                const thoughts = message.metadata?.thoughts || []
                const text = payload.text || ''
                const last = thoughts[thoughts.length - 1]
                if (last?.source === 'model') {
                  const merged = { ...last, content: (last.content || '') + text }
                  return {
                    ...message,
                    metadata: { ...(message.metadata || {}), thoughts: [...thoughts.slice(0, -1), merged] }
                  }
                }
                return {
                  ...message,
                  metadata: {
                    ...(message.metadata || {}),
                    thoughts: [...thoughts, { title: '模型思考', content: text, source: 'model' }]
                  }
                }
              })
            }
          })
        },
        onAnswerDelta: (payload) => {
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            const text = payload.text || ''
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((message) => (
                message.id === assistantId ? { ...message, content: (message.content || '') + text } : message
              ))
            }
          })
        },
        onToolCall: (toolCall) => {
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((message) => {
                if (message.id !== assistantId) return message
                const previousEvents = message.metadata?.tool_events || []
                return {
                  ...message,
                  metadata: {
                    ...(message.metadata || {}),
                    used_tools: addUniqueTool(message.metadata?.used_tools || [], toolCall.name),
                    tool_events: [...previousEvents, toolCall],
                  }
                }
              })
            }
          })
        },
        onToolResult: (toolResult) => {
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((message) => {
                if (message.id !== assistantId) return message
                const previousEvents = message.metadata?.tool_events || []
                return {
                  ...message,
                  metadata: {
                    ...(message.metadata || {}),
                    tool_events: previousEvents.map((item) => (
                      item.id === toolResult.id ? toolResult : item
                    )),
                    used_tools: addUniqueTool(message.metadata?.used_tools || [], toolResult.name),
                  }
                }
              })
            }
          })
        },
        onDelta: (delta) => {
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((message) => (
                message.id === assistantId ? { ...message, content: message.content + delta } : message
              ))
            }
          })
        },
        onDone: (payload) => {
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((message) => {
                if (message.id !== assistantId) return message
                const fallbackText = '生成完成，但没有收到可显示内容。请稍后重试或检查模型连接。'
                const elapsed = Math.max(1, Math.round((Date.now() - startedAt) / 1000))
                return {
                  ...message,
                  content: message.content || payload?.reply || fallbackText,
                  metadata: {
                    ...(message.metadata || {}),
                    ...(payload?.metadata || {}),
                    thinking_seconds: elapsed,
                  }
                }
              })
            }
          })
          setChatNotice('')
          queryClient.invalidateQueries({ queryKey: ['conversation', String(targetConvId)] })
          queryClient.invalidateQueries({ queryKey: ['conversations'] })
        },
        onError: (payload) => {
          const errorNotice = buildChatErrorNotice(payload)
          const errorText = formatAssistantError(errorNotice)
          setChatNotice(errorNotice)
          setChatDraft((current) => {
            const currentMessages = current?.messages || initialMessages
            return {
              conversationId: String(targetConvId),
              messages: currentMessages.map((item) => (
                item.id === assistantId
                  ? {
                      ...item,
                      content: errorText,
                      metadata: {
                        ...(item.metadata || {}),
                        status_message: errorNotice.text,
                        status_diagnostic: errorNotice.diagnostic || null,
                      }
                    }
                  : item
              ))
            }
          })
        }
      }, { signal: controller.signal })
    } catch (error) {
      // 用户主动停止：保留已生成的部分内容，不当作错误
      if (error?.name === 'AbortError' || error?.name === 'CanceledError') {
        setChatDraft((current) => {
          const currentMessages = current?.messages || []
          return {
            conversationId: String(convId || ''),
            messages: currentMessages.map((item) => (
              item.id === assistantId && !item.content
                ? { ...item, content: '（已停止生成。）' }
                : item
            ))
          }
        })
        queryClient.invalidateQueries({ queryKey: ['conversation', String(convId)] })
      } else {
        setChatNotice(buildChatErrorNotice(error.payload || error))
      }
    } finally {
      abortRef.current = null
      setChatPending(null)
      setChatSending(false)
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
  }

  const handleRegenerate = () => {
    if (isSending) return
    const items = [...messages]
    while (items.length && items[items.length - 1].role === 'assistant') {
      items.pop()
    }
    const lastUser = items[items.length - 1]
    if (!lastUser || lastUser.role !== 'user') return
    const content = lastUser.content
    if (!content) return
    // 从草稿里去掉最后这组问答，让 handleSend 原样重发
    setChatDraft({ conversationId: String(convId), messages: items.slice(0, -1) })
    handleSend(content)
  }

  const handleFiles = async (files) => {
    const selectedFiles = Array.from(files || [])
    if (!selectedFiles.length) return

    setChatNotice(conversation?.project?.id ? '正在上传资料...' : '正在创建会话并上传资料...')
    try {
      let targetConversation = conversation
      if (!targetConversation?.project?.id) {
        targetConversation = await createConversation({
          title: '资料会话',
          mode: 'chat',
          description: '由资料上传自动创建'
        })
        navigate(`/chat/${targetConversation.id}`, { replace: true })
      }

      await uploadProjectFiles(targetConversation.project.id, selectedFiles)
      setChatNotice('资料已加入当前会话。')
      queryClient.invalidateQueries({ queryKey: ['conversation', String(targetConversation.id)] })
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
    } catch (error) {
      setChatNotice(error.message || '上传失败。')
    }
  }

  const handleDeleteConversation = (conversationId) => {
    if (!conversationId || deleteMutation.isPending) return
    const target = conversations.find((item) => String(item.id) === String(conversationId))
    const label = target?.title || '这个会话'
    if (!window.confirm(`确定删除「${label}」吗？`)) return
    deleteMutation.mutate(conversationId)
  }

  return (
    <div className="chat-app">
      <ChatSidebar
        conversations={conversations}
        activeId={convId}
        onNewChat={createWorkspace}
        onDeleteChat={handleDeleteConversation}
        deletingId={deleteMutation.variables}
        onRenameChat={handleRenameConversation}
        onPinChat={handlePinChat}
        user={user}
        onLogout={logout}
        isLocalMode={isLocalMode}
      />

      <main className="chat-main">
        <header className="chat-header">
          <div className="chat-title-block">
            <h1>{conversation?.title || '新任务'}</h1>
          </div>
          <div className="chat-header-actions">
            {convId && messages.length ? (
              <button
                type="button"
                className="ghost-button"
                title="导出会话为 Markdown"
                aria-label="导出会话"
                onClick={handleExportMarkdown}
              >
                <Icon name="download" size={14} />
              </button>
            ) : null}
            <button
              type="button"
              className="ghost-button"
              title="模型与运行状态"
              onClick={() => setRuntimeOpen((open) => !open)}
            >
              <Icon name="spark" size={14} />
              {runtime.modelName
                ? `${runtime.modelName} · ${channelLabel(runtime.baseUrl)}`
                : '未配置模型'}
            </button>
            {convId ? (
              <button
                type="button"
                className="ghost-button chat-delete-button"
                title="删除会话"
                aria-label="删除会话"
                disabled={deleteMutation.isPending}
                onClick={() => handleDeleteConversation(convId)}
              >
                <Icon name="trash" size={14} />
              </button>
            ) : null}
          </div>
        </header>

        <div className="chat-workspace">
          <section className={`chat-thread ${messages.length ? '' : 'empty'}`}>
            <details className="mobile-runtime-panel">
              <summary>
                <span>{runtime.gatewayLabel}</span>
                <small>
                  {runtime.modelName
                    ? `${runtime.modelName} · ${channelLabel(runtime.baseUrl)}`
                    : '未配置模型'}
                </small>
              </summary>
              <InsightPanel project={conversation?.project} runtime={runtime} compact />
            </details>

            {isLoading ? (
              <div className="loading-state">正在加载对话...</div>
            ) : (
              <MessageList
                messages={messages}
                pendingMessageId={pendingId}
                onRegenerate={handleRegenerate}
              />
            )}

            {!isLoading && !messages.length ? (
              <EmptyChatHero onStarter={handleSend}>
                <ChatInput
                  hero
                  disabled={isSending}
                  running={isSending}
                  onStop={handleStop}
                  onSend={handleSend}
                  onFiles={handleFiles}
                />
              </EmptyChatHero>
            ) : null}

            {notice ? (
              <ChatNotice
                notice={notice}
                copyState={copyState}
                onClose={() => setChatNotice('')}
                onRetry={normalizedNoticeOk(notice) ? undefined : handleRegenerate}
                onCopy={async (text) => {
                  if (!text) return
                  const ok = await copyText(text)
                  setCopyState(ok ? '已复制' : '复制失败')
                  window.setTimeout(() => setCopyState(''), 1600)
                }}
              />
            ) : null}

            {messages.length ? (
              <ChatInput
                disabled={isSending}
                running={isSending}
                onStop={handleStop}
                onSend={handleSend}
                onFiles={handleFiles}
              />
            ) : null}
          </section>
        </div>

        <button
          type="button"
          className={`rail-backdrop ${runtimeOpen ? 'open' : ''}`}
          aria-label="关闭运行设置"
          onClick={() => setRuntimeOpen(false)}
        />
        <aside className={`delivery-rail ${runtimeOpen ? 'open' : ''}`} aria-label="Agent 运行状态" aria-hidden={!runtimeOpen}>
          <div className="rail-head">
            <span>运行状态</span>
            <button type="button" className="rail-close" onClick={() => setRuntimeOpen(false)}>×</button>
          </div>
          <InsightPanel project={conversation?.project} runtime={runtime} />
        </aside>
      </main>
    </div>
  )
}

function normalizedNoticeOk(notice) {
  if (typeof notice === 'string') return true
  return (notice || { ok: true }).ok !== false
}

function ChatNotice({ notice, copyState, onCopy, onClose, onRetry }) {
  const normalized = normalizeNotice(notice)
  return (
    <div className={`chat-notice ${normalized.ok === false ? 'error' : ''} ${normalized.level === 'switch' ? 'switch' : ''}`}>
      <div className="chat-notice-main">
        <strong>{normalized.text}</strong>
        <div className="chat-notice-side">
          {normalized.ok === false && onRetry ? (
            <button type="button" className="ghost-button" onClick={onRetry}>
              重试
            </button>
          ) : null}
          {normalized.diagnosticText ? (
            <button type="button" className="ghost-button" onClick={() => onCopy?.(normalized.diagnosticText)}>
              {copyState || '复制诊断'}
            </button>
          ) : null}
          {onClose ? (
            <button type="button" className="chat-notice-close" title="关闭" aria-label="关闭通知" onClick={onClose}>
              <Icon name="x" size={12} />
            </button>
          ) : null}
        </div>
      </div>
      {normalized.details?.length ? (
        <dl className="chat-diagnostic-list">
          {normalized.details.map(([label, value]) => (
            value ? (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ) : null
          ))}
        </dl>
      ) : null}
    </div>
  )
}

function buildRuntimeNotice(status = {}) {
  if (!status?.diagnostic) {
    return status.message || ''
  }
  const diagnostic = status.diagnostic
  const text = status.message || diagnostic.message || '运行链路发生切换。'
  // 链路切换是运行时降级，不是致命错误：中性提示样式，不渲染成红色错误横幅
  return {
    ok: true,
    level: 'switch',
    text,
    diagnostic,
    details: buildDiagnosticDetails({
      ...diagnostic,
      gateway: status.gateway,
      stage: status.stage,
    }),
    diagnosticText: buildDiagnosticText({
      title: '聊天运行诊断',
      message: text,
      gateway: status.gateway,
      stage: status.stage,
      ...diagnostic,
    }),
  }
}

function buildChatErrorNotice(payload) {
  const data = normalizeErrorPayload(payload)
  const diagnostic = data.diagnostic || data
  const text = `生成失败：${data.message || diagnostic.message || '聊天流式响应失败。'}`
  return {
    ok: false,
    text,
    diagnostic,
    details: buildDiagnosticDetails(diagnostic),
    diagnosticText: buildDiagnosticText({
      title: '聊天失败诊断',
      message: text,
      ...diagnostic,
    }),
  }
}

function normalizeNotice(notice) {
  if (typeof notice === 'string') {
    return { ok: true, text: notice }
  }
  return notice || { ok: true, text: '' }
}

function normalizeErrorPayload(payload) {
  if (!payload) return {}
  if (typeof payload === 'string') return { message: payload }
  if (payload instanceof Error) {
    return {
      message: payload.message,
      status_code: payload.status,
      error_type: payload.name,
    }
  }
  return payload
}

function buildDiagnosticDetails(diagnostic = {}) {
  return [
    ['链路', diagnostic.gateway],
    ['阶段', diagnostic.stage],
    ['错误类型', diagnostic.error_type],
    ['HTTP 状态', diagnostic.status_code],
    ['错误说明', diagnostic.message],
    ['建议', diagnostic.hint],
    ['原始错误', diagnostic.error],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '')
}

function buildDiagnosticText(diagnostic = {}) {
  const lines = [
    diagnostic.title || '聊天诊断',
    `消息：${diagnostic.message || ''}`,
    `链路：${diagnostic.gateway || ''}`,
    `阶段：${diagnostic.stage || ''}`,
    `错误类型：${diagnostic.error_type || ''}`,
    `HTTP 状态：${diagnostic.status_code || ''}`,
    `建议：${diagnostic.hint || ''}`,
    `原始错误：${diagnostic.error || ''}`,
  ]
  return lines.join('\n')
}

function formatAssistantError(notice) {
  const lines = [notice.text]
  const hint = notice.diagnostic?.hint
  const errorType = notice.diagnostic?.error_type
  const statusCode = notice.diagnostic?.status_code
  if (hint) lines.push(`建议：${hint}`)
  if (errorType || statusCode) {
    lines.push(`诊断：${[errorType, statusCode ? `HTTP ${statusCode}` : ''].filter(Boolean).join(' / ')}`)
  }
  return lines.join('\n\n')
}

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    return false
  }
  return false
}

// 渠道标签：从 base_url 提取主机名（如 ai.venlacy.com），本机网关与缺省分别标注
function channelLabel(baseUrl) {
  if (!baseUrl) return '默认渠道'
  try {
    const host = new URL(baseUrl).hostname.replace(/^www\./, '')
    if (!host || host === 'localhost' || host === '127.0.0.1') return '本地网关'
    return host
  } catch {
    return '自定义渠道'
  }
}

function buildRuntimeSnapshot(conversation, messages, aiConfig) {
  const latestAssistant = [...(messages || [])].reverse().find((message) => message.role === 'assistant')
  const metadata = latestAssistant?.metadata || {}
  const toolEvents = metadata.tool_events || []
  const gatewayLabelMap = {
    hermes: 'Hermes 会话',
    compat: 'Hermes 兼容链路',
    fallback: '本地保底答复',
  }
  return {
    gatewayLabel: gatewayLabelMap[metadata.gateway] || 'Hermes 会话',
    sessionId: metadata.session_id || conversation?.session_id || '',
    provider: metadata.provider || aiConfig?.provider || '',
    baseUrl: metadata.base_url || aiConfig?.base_url || '',
    modelName: metadata.model_name || metadata.model || aiConfig?.model_name || '',
    temperature: metadata.temperature ?? aiConfig?.temperature ?? null,
    maxTokens: metadata.max_tokens ?? aiConfig?.max_tokens ?? null,
    fileCount: metadata.file_count ?? conversation?.project?.project_files?.length ?? 0,
    toolCount: toolEvents.length,
    usedTools: metadata.used_tools || [],
    toolEvents,
    statusMessage: metadata.status_message || '',
  }
}

function addUniqueTool(current, toolName) {
  if (!toolName) return current
  return current.includes(toolName) ? current : [...current, toolName]
}
