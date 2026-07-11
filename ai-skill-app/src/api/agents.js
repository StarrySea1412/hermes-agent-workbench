import { getStoredToken } from '../auth/storage'
import client from './client'

const apiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || ''
const API_BASE = `${apiBase}/api`

export function listAgentTemplates() {
  return client.get('/agent-templates')
}

export function createAgentTemplate(data) {
  return client.post('/agent-templates/create', data)
}

export function getAgentTemplate(agentId) {
  return client.get(`/agent-templates/${agentId}`)
}

export function updateAgentTemplate(agentId, data) {
  return client.patch(`/agent-templates/${agentId}`, data)
}

export function deleteAgentTemplate(agentId) {
  return client.delete(`/agent-templates/${agentId}`)
}

export function listAgentRuns() {
  return client.get('/agent-runs')
}

export function createAgentRun(data) {
  return client.post('/agent-runs', data)
}

export function getAgentRun(runId) {
  return client.get(`/agent-runs/${runId}`)
}

export function getAgentRunArtifacts(runId) {
  return client.get(`/agent-runs/${runId}/artifacts`)
}

export function getAgentRunMemories(runId) {
  return client.get(`/agent-runs/${runId}/memories`)
}

export function saveRunAsMemory(runId, data) {
  return client.post(`/agent-runs/${runId}/save-memory`, data)
}

export function cancelAgentRun(runId) {
  return client.post(`/agent-runs/${runId}/cancel`)
}

export function listAgentTools() {
  return client.get('/tools')
}

export function listAgentMemories(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    query.set(key, String(value))
  })
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return client.get(`/memories${suffix}`)
}

export function createAgentMemory(data) {
  return client.post('/memories', data)
}

export function updateAgentMemory(memoryId, data) {
  return client.patch(`/memories/${memoryId}`, data)
}

export function deleteAgentMemory(memoryId) {
  return client.delete(`/memories/${memoryId}`)
}

export async function executeAgentRunStream(runId, handlers = {}, signal) {
  const response = await fetch(`${API_BASE}/agent-runs/${runId}/execute-stream`, {
    method: 'POST',
    headers: buildAuthHeaders(),
    signal,
  })

  if (!response.ok || !response.body) {
    let message = 'Unable to start the agent run.'
    try {
      const errorData = await response.json()
      message = errorData.message || errorData.detail || message
    } catch {
      message = response.statusText || message
    }
    throw new Error(message)
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
      if (parsed.event === 'run') handlers.onRun?.(parsed.data)
      if (parsed.event === 'step') handlers.onStep?.(parsed.data)
      if (parsed.event === 'complete') handlers.onComplete?.(parsed.data)
      if (parsed.event === 'error') handlers.onError?.(parsed.data.message || 'Agent run failed.')
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
