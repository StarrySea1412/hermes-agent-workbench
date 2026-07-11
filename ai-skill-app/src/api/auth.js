import client from './client'

export function login(username, password) {
  return client.post('/auth/login', { username, password })
}

export function register(username, password) {
  return client.post('/auth/register', { username, password })
}

export function getCurrentUser() {
  return client.get('/users/me')
}
