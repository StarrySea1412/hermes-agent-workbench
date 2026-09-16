import client from './client'

export function listMcpServers() {
  return client.get('/mcp-servers')
}

export function createMcpServer(payload) {
  return client.post('/mcp-servers', payload)
}

export function updateMcpServer(serverId, payload) {
  return client.patch(`/mcp-servers/${serverId}`, payload)
}

export function deleteMcpServer(serverId) {
  return client.delete(`/mcp-servers/${serverId}`)
}

export function probeMcpServer(serverId) {
  return client.post(`/mcp-servers/${serverId}/probe`)
}
