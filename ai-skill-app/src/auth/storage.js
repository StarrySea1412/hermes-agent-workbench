import { useSyncExternalStore } from 'react'

const TOKEN_KEY = 'token'
const LOCAL_MODE_BYPASS_KEY = 'deckpilot:skip-local-mode'
const AUTH_CHANGE_EVENT = 'deckpilot:auth-change'
const EMPTY_SNAPSHOT = Object.freeze({ token: '', skipLocalMode: false })

let cachedSnapshot = EMPTY_SNAPSHOT

function canUseBrowserStorage() {
  return typeof window !== 'undefined'
}

function emitAuthChange() {
  if (!canUseBrowserStorage()) {
    return
  }
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT))
}

function getSnapshot() {
  if (!canUseBrowserStorage()) {
    return EMPTY_SNAPSHOT
  }

  const token = window.localStorage.getItem(TOKEN_KEY) || ''
  const skipLocalMode = window.localStorage.getItem(LOCAL_MODE_BYPASS_KEY) === '1'

  if (
    cachedSnapshot.token === token &&
    cachedSnapshot.skipLocalMode === skipLocalMode
  ) {
    return cachedSnapshot
  }

  cachedSnapshot = { token, skipLocalMode }
  return cachedSnapshot
}

function subscribe(callback) {
  if (!canUseBrowserStorage()) {
    return () => {}
  }

  window.addEventListener('storage', callback)
  window.addEventListener(AUTH_CHANGE_EVENT, callback)
  return () => {
    window.removeEventListener('storage', callback)
    window.removeEventListener(AUTH_CHANGE_EVENT, callback)
  }
}

export function useAuthSnapshot() {
  return useSyncExternalStore(subscribe, getSnapshot, () => EMPTY_SNAPSHOT)
}

export function getStoredToken() {
  return getSnapshot().token
}

export function setStoredToken(token) {
  if (!canUseBrowserStorage()) {
    return
  }
  window.localStorage.setItem(TOKEN_KEY, token)
  window.localStorage.removeItem(LOCAL_MODE_BYPASS_KEY)
  emitAuthChange()
}

export function clearStoredToken() {
  if (!canUseBrowserStorage()) {
    return
  }
  window.localStorage.removeItem(TOKEN_KEY)
  emitAuthChange()
}

export function setLocalModeBypass(enabled) {
  if (!canUseBrowserStorage()) {
    return
  }

  if (enabled) {
    window.localStorage.setItem(LOCAL_MODE_BYPASS_KEY, '1')
  } else {
    window.localStorage.removeItem(LOCAL_MODE_BYPASS_KEY)
  }
  emitAuthChange()
}
