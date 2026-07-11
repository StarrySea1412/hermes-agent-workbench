import client from './client'

export function getAIConfig() {
  return client.get('/ai-config')
}

export function createAIConfig(data) {
  return client.post('/ai-config', data)
}

export function updateAIConfig(data) {
  return client.patch('/ai-config', data)
}

export function testAIConfig() {
  return client.post('/ai-config/test')
}

export function fetchAIModels(data) {
  return client.post('/ai-config/models', data)
}

export function getHermesStatus() {
  return client.get('/hermes/status')
}

export function getHermesSkills() {
  return client.get('/hermes/skills')
}

export function getHermesSkillDetail(skillPath) {
  return client.get(`/hermes/skills/${skillPath}`)
}

export function getHermesMonitor({ includeChat = false } = {}) {
  return client.get(`/hermes/monitor?chat=${includeChat ? 'true' : 'false'}`)
}
