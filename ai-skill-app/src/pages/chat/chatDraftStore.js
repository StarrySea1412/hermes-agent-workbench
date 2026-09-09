// 模块级流式草稿存储：让正在生成的消息跨路由跳转存活。
// ChatView 组件卸载（导航去设置页/别的会话）时流仍在后台跑，回到会话页能接上。
let draftState = null
let pendingIdState = null
let sendingState = false
let noticeState = ''
let version = 0
let valueCache = { version: -1, value: null }
const listeners = new Set()

function notify() {
  version += 1
  listeners.forEach((fn) => fn())
}

export function subscribeChatDraft(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getChatDraftSnapshot() {
  if (valueCache.version !== version) {
    valueCache = {
      version,
      value: { draft: draftState, pendingId: pendingIdState, isSending: sendingState },
    }
  }
  return valueCache.value
}

export function getChatNotice() {
  return noticeState
}

export function setChatDraft(updater) {
  draftState = typeof updater === 'function' ? updater(draftState) : updater
  notify()
}

export function setChatPending(id) {
  pendingIdState = id
  notify()
}

export function setChatSending(flag) {
  sendingState = flag
  notify()
}

export function setChatNotice(value) {
  noticeState = value
  notify()
}

export function clearChatDraft() {
  draftState = null
  pendingIdState = null
  sendingState = false
  notify()
}
