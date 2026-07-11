import axios from 'axios'
import { getStoredToken } from '../auth/storage'

const apiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || ''

const client = axios.create({
  baseURL: `${apiBase}/api`,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

client.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.message || error.response?.data?.detail || error.message || 'Request failed'
    const wrappedError = new Error(message)
    wrappedError.status = error.response?.status
    wrappedError.payload = error.response?.data
    console.error('API Error:', message)
    return Promise.reject(wrappedError)
  }
)

export default client
