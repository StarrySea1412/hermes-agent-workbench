import client from './client'
import { getStoredToken } from '../auth/storage'

const apiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || ''
const API_BASE = `${apiBase}/api`

export function listBids() {
  return client.get('/bids')
}

export function createBid(data) {
  return client.post('/bids', data)
}

export function getBid(bidId) {
  return client.get(`/bids/${bidId}`)
}

export function deleteBid(bidId) {
  return client.delete(`/bids/${bidId}`)
}

export function createBidChapter(bidId, data) {
  return client.post(`/bids/${bidId}/chapters`, data)
}

export function updateBidChapter(bidId, chapterId, data) {
  return client.patch(`/bids/${bidId}/chapters/${chapterId}`, data)
}

export function deleteBidChapter(bidId, chapterId) {
  return client.delete(`/bids/${bidId}/chapters/${chapterId}`)
}

export function listBidWorkflows(bidId) {
  return client.get(`/bids/${bidId}/multi-agent/workflows`)
}

export function createBidWorkflow(bidId, data) {
  return client.post(`/bids/${bidId}/multi-agent/workflows`, data)
}

export function getBidWorkflowDetail(bidId, workflowId) {
  return client.get(`/bids/${bidId}/multi-agent/workflows/${workflowId}`)
}

export function executeBidWorkflow(bidId, workflowId) {
  return client.post(`/bids/${bidId}/multi-agent/workflows/${workflowId}/execute`)
}

export function cancelBidWorkflow(bidId, workflowId) {
  return client.post(`/bids/${bidId}/multi-agent/workflows/${workflowId}/cancel`)
}

export function generateBidOutline(file, bidTitle = '') {
  const formData = new FormData()
  formData.append('file', file)
  const query = bidTitle.trim() ? `?bid_title=${encodeURIComponent(bidTitle.trim())}` : ''
  return client.post(`/bid-analyzer/generate-outline${query}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export async function exportBidDocx(bidId) {
  const response = await fetch(`${API_BASE}/bids/${bidId}/export`, {
    method: 'POST',
    headers: buildAuthHeaders(),
  })

  if (!response.ok) {
    let message = 'Unable to export the project.'
    try {
      const errorData = await response.json()
      message = errorData.message || errorData.detail || message
    } catch {
      message = response.statusText || message
    }
    throw new Error(message)
  }

  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  return { blob, filename: match?.[1] || 'workflow-project.docx' }
}

function buildAuthHeaders() {
  const token = getStoredToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
