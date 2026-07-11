import client from './client'

const apiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || ''

export function listFiles() {
  return client.get('/files')
}

export function uploadFile(file, description = '') {
  const formData = new FormData()
  formData.append('file', file)
  if (description.trim()) {
    formData.append('description', description.trim())
  }
  return client.post('/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export function uploadFiles(files, description = '') {
  return Promise.all(Array.from(files || []).map((file) => uploadFile(file, description)))
}

export function deleteFile(fileId) {
  return client.delete(`/files/${fileId}`)
}

export function resolveFileUrl(url) {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url

  const backendBase = apiBase || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
  return new URL(url, backendBase).toString()
}
