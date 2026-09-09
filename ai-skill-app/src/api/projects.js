import { getStoredToken } from '../auth/storage'
import client from './client'

const apiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || ''
const API_BASE = `${apiBase}/api`

export function listProjects() {
  return client.get('/projects/')
}

export function getProject(projectId) {
  return client.get(`/projects/${projectId}/`)
}

export function createProject(data) {
  return client.post('/projects/', data)
}

export function uploadProjectFiles(projectId, files) {
  const formData = new FormData()
  Array.from(files).forEach((file) => formData.append('files', file))
  return client.post(`/projects/${projectId}/files/`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export async function exportProjectMarkdown(projectId) {
  return exportProjectFile(projectId, 'markdown', 'workspace-output.md')
}

export async function exportProjectDocx(projectId) {
  return exportProjectFile(projectId, 'docx', 'workspace-output.docx')
}

async function exportProjectFile(projectId, format, fallbackFilename) {
  const response = await fetch(`${API_BASE}/projects/${projectId}/export/${format}/`, {
    method: 'POST',
    headers: buildAuthHeaders()
  })

  if (!response.ok) {
    throw new Error('导出失败')
  }

  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  return { blob, filename: match?.[1] || fallbackFilename }
}

export function listConversations() {
  return client.get('/conversations/')
}

export function createConversation(data) {
  return client.post('/conversations/', data)
}

export function getConversation(conversationId) {
  return client.get(`/conversations/${conversationId}/`)
}

export function deleteConversation(conversationId) {
  return client.delete(`/conversations/${conversationId}/`)
}

export function renameConversation(conversationId, title) {
  return client.patch(`/conversations/${conversationId}/`, { title })
}

export async function streamMessage(conversationId, data, handlers = {}, options = {}) {
  const response = await fetch(`${API_BASE}/conversations/${conversationId}/stream/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...buildAuthHeaders()
    },
    body: JSON.stringify(data),
    signal: options.signal
  })

  if (!response.ok || !response.body) {
    let message = '消息发送失败'
    let payload = null
    try {
      const errorData = await response.json()
      payload = errorData
      message = errorData.message || errorData.detail || message
    } catch {
      message = response.statusText || message
    }
    const error = new Error(message)
    error.payload = payload
    error.status = response.status
    throw error
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    events.forEach((raw) => {
      const parsed = parseSseEvent(raw)
      if (!parsed) return
      if (parsed.event === 'status') handlers.onStatus?.(parsed.data)
      if (parsed.event === 'thought') handlers.onThought?.(parsed.data)
      if (parsed.event === 'thought_delta') handlers.onThoughtDelta?.(parsed.data)
      if (parsed.event === 'answer_delta') handlers.onAnswerDelta?.(parsed.data)
      if (parsed.event === 'tool_call') handlers.onToolCall?.(parsed.data)
      if (parsed.event === 'tool_result') handlers.onToolResult?.(parsed.data)
      if (parsed.event === 'delta') handlers.onDelta?.(parsed.data.content || '')
      if (parsed.event === 'done') handlers.onDone?.(parsed.data)
      if (parsed.event === 'error') handlers.onError?.(parsed.data)
    })
  }
}

function buildAuthHeaders() {
  const token = getStoredToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function parseSseEvent(raw) {
  const lines = raw.split('\n')
  const event = lines.find((line) => line.startsWith('event:'))?.replace('event:', '').trim()
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.replace('data:', '').trim())
    .join('\n')

  if (!event || !data) return null

  try {
    return { event, data: JSON.parse(data) }
  } catch {
    return null
  }
}
