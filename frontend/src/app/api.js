// Shared data helpers for the unified console.

export async function api(path, options) {
  const res = await fetch(path, options)
  if (!res.ok) {
    const text = await res.text()
    let body = null
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
    const detail = body?.detail
    const err = new Error(detail?.message || (typeof detail === 'string' ? detail : '') || `${res.status} ${path}`)
    err.status = res.status
    err.body = body
    throw err
  }
  return res.json()
}

export function post(path, body) {
  return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}

export function money(n) {
  const v = Number(n) || 0
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1)}M`
  if (v >= 1e3) return `$${Math.round(v / 1e3)}K`
  return `$${v}`
}

export function label(v) {
  return String(v || '—')
    .replaceAll('_', ' ')
    .toLowerCase()
    .replace(/^\w/, c => c.toUpperCase())
}

export function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`
}

export function since(iso) {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

// "Will X? (kalshi KXFOO-1)" -> { question: "Will X?", ref: "kalshi KXFOO-1" }
export function splitTitle(title) {
  const m = String(title || '').match(/^(.*?)\s*\(((?:kalshi|polymarket)\s+[^)]+)\)\s*$/i)
  return m ? { question: m[1], ref: m[2] } : { question: String(title || ''), ref: '' }
}

// Blocker families drive color and wording everywhere.
export const BLOCKERS = {
  policy_interpretation: { name: 'Interpretation', tone: 'violet', verb: 'Rule on the wording' },
  authority_conflict: { name: 'Source conflict', tone: 'blue', verb: 'Pick the controlling source' },
  timing_revision: { name: 'Timing & revisions', tone: 'amber', verb: 'Fix the observation window' },
  resolution_hold: { name: 'Payout hold', tone: 'red', verb: 'Clear the prerequisite' },
  evidence_conflict: { name: 'Evidence conflict', tone: 'blue', verb: 'Choose the controlling evidence' },
  evidence_review: { name: 'Evidence review', tone: 'slate', verb: 'Confirm the evidence' },
  evidence_missing: { name: 'Waiting on data', tone: 'slate', verb: 'Wait or act' },
  operator_review: { name: 'Operator review', tone: 'slate', verb: 'Review and advance' },
  audit_integrity: { name: 'Audit integrity', tone: 'red', verb: 'Restore the audit chain' },
}

export function blocker(type) {
  return BLOCKERS[type] || { name: label(type), tone: 'slate', verb: 'Record a judgment' }
}

export const TIER = { same_clause: 'Same clause', same_template: 'Same template', related: 'Related' }
