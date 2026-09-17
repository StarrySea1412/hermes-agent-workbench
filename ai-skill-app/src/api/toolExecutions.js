import client from './client'

export const toolExecutionsKey = (conversationId) => ['tool-executions', String(conversationId)]

export async function listToolExecutions(conversationId, { signal } = {}) {
  const payload = await client.get('/tool-executions/', {
    params: { conversation_id: conversationId },
    signal,
  })
  const records = Array.isArray(payload) ? payload
    : Array.isArray(payload?.results) ? payload.results
      : Array.isArray(payload?.data) ? payload.data
        : payload?.data?.results
  if (!Array.isArray(records)) throw new Error('工具审批记录响应格式异常，请稍后刷新。')
  // Never display another conversation's approvals, even if a response is stale or misfiltered.
  return records.filter((record) => String(record.conversation_id) === String(conversationId))
}

export function decideToolExecution(id, decision) {
  return client.post(`/tool-executions/${encodeURIComponent(id)}/decision/`, { decision })
}
