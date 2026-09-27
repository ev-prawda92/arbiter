// Console credentials (v0.45).
//
// When the server has API keys configured, every /api/ call needs one. The key
// is kept for this browser tab only (sessionStorage), sent as X-Arbiter-Key on
// same-origin /api/ requests, and never written anywhere else.

const STORE = 'arbiter.key'
export const AUTH_EVENT = 'arbiter:auth-required'

export function getKey() {
  try {
    return window.sessionStorage.getItem(STORE) || ''
  } catch {
    return ''
  }
}

export function setKey(key) {
  try {
    if (key) window.sessionStorage.setItem(STORE, key)
    else window.sessionStorage.removeItem(STORE)
  } catch {
    // storage blocked: the key lives only until reload
  }
  memoryKey = key || ''
}

let memoryKey = ''

function isApi(input) {
  const url = typeof input === 'string' ? input : input?.url || ''
  try {
    const u = new URL(url, window.location.href)
    return u.origin === window.location.origin && u.pathname.startsWith('/api/')
  } catch {
    return false
  }
}

// Wrap window.fetch once so every view (including the legacy ones) sends the key.
export function installFetchAuth() {
  if (window.__arbiterFetchAuth) return
  window.__arbiterFetchAuth = true
  const base = window.fetch.bind(window)
  window.fetch = async (input, init = {}) => {
    if (!isApi(input)) return base(input, init)
    const key = getKey() || memoryKey
    const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined))
    if (key && !headers.has('X-Arbiter-Key')) headers.set('X-Arbiter-Key', key)
    const res = await base(input, { ...init, headers })
    if (res.status === 401) window.dispatchEvent(new CustomEvent(AUTH_EVENT))
    return res
  }
}
