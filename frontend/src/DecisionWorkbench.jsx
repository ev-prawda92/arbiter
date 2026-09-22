import React, { useEffect, useMemo, useState } from 'react'

async function json(path, options) {
  const res = await fetch(path, options)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${text || path}`)
  }
  return res.json()
}

function money(n) {
  if (!n) return '$0'
  return `$${(Number(n) / 1e6).toFixed(Number(n) >= 1e7 ? 0 : 1)}M`
}

function label(v) {
  return String(v || '—').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export default function DecisionWorkbench() {
  const [overview, setOverview] = useState(null)
  const [clusterId, setClusterId] = useState('')
  const [context, setContext] = useState(null)
  const [selection, setSelection] = useState('')
  const [rationale, setRationale] = useState('')
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const clusters = overview?.agent_brief?.operations_intelligence?.clusters || []
  const selected = useMemo(() => clusters.find(c => c.cluster_id === clusterId) || clusters[0] || null, [clusters, clusterId])

  async function loadOverview() {
    setError('')
    const next = await json('/api/overview')
    setOverview(next)
    const first = next?.agent_brief?.operations_intelligence?.clusters?.[0]
    if (!clusterId && first) setClusterId(first.cluster_id)
  }

  async function loadContext(id) {
    if (!id) return
    setError('')
    setContext(null)
    setResult(null)
    setSelection('')
    setRationale('')
    try {
      setContext(await json(`/api/decision-context/${encodeURIComponent(id)}`))
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => { loadOverview().catch(e => setError(e.message)) }, [])
  useEffect(() => { if (selected?.cluster_id) loadContext(selected.cluster_id) }, [selected?.cluster_id])

  async function recordDecision() {
    if (!selected || !selection.trim() || !rationale.trim()) return
    setSaving(true)
    setError('')
    try {
      const next = await json('/api/decisions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cluster_id: selected.cluster_id,
          selection,
          rationale,
          governing_rule: '',
          owner: 'Resolution Ops',
          actor: 'operator:resolution-ops',
        }),
      })
      setResult(next)
      setOverview(next.reevaluation?.overview || overview)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const prompt = context?.decision_prompt || {}
  const before = result?.reevaluation?.workload?.before
  const after = result?.reevaluation?.workload?.after

  return <div className="dw-shell">
    <header className="dw-header">
      <div>
        <span>Arbiter v0.34 · Decision Operations</span>
        <h1>Make the smallest human decision. Clear everything else.</h1>
        <p>One governed judgment can apply to an entire repeated work pattern, then Arbiter re-evaluates the affected queue.</p>
      </div>
      <a href="/console.html">Back to console</a>
    </header>

    {error && <div className="dw-error">{error}</div>}

    <div className="dw-grid">
      <aside className="dw-patterns">
        <div className="dw-panel-title"><span>Work patterns</span><strong>{clusters.length}</strong></div>
        {clusters.map(c => <button key={c.cluster_id} className={c.cluster_id === selected?.cluster_id ? 'selected' : ''} onClick={() => setClusterId(c.cluster_id)}>
          <div><strong>{label(c.blocker_type)}</strong><span>{c.count} cases · {money(c.notional)}</span></div>
          <b>{c.count > 1 ? `${c.count}→1` : '1'}</b>
        </button>)}
      </aside>

      <main className="dw-main">
        {!selected ? <div className="dw-empty">No active work patterns.</div> : <>
          <section className="dw-hero">
            <span>Current work pattern</span>
            <h2>{label(selected.blocker_type)}</h2>
            <p>{selected.root_cause || selected.recommended_action}</p>
            <div className="dw-stats">
              <div><small>Affected</small><strong>{selected.count}</strong></div>
              <div><small>Notional</small><strong>{money(selected.notional)}</strong></div>
              <div><small>State</small><strong>{label(selected.dominant_state)}</strong></div>
            </div>
          </section>

          <section className="dw-card">
            <div className="dw-card-head"><span>1 · Human judgment</span><strong>{label(prompt.decision_type)}</strong></div>
            <h3>{prompt.question || 'What governed judgment resolves this pattern?'}</h3>
            <p>{prompt.context || selected.root_cause}</p>
            <div className="dw-rule"><span>Clear condition</span><strong>{prompt.clear_condition || selected.clear_condition}</strong></div>
          </section>

          <section className="dw-card">
            <div className="dw-card-head"><span>2 · Record decision</span><strong>Audited</strong></div>
            <label>
              <span>Decision</span>
              <input value={selection} onChange={e => setSelection(e.target.value)} placeholder="e.g. Initial official release controls" />
            </label>
            <label>
              <span>Rationale</span>
              <textarea value={rationale} onChange={e => setRationale(e.target.value)} placeholder="Explain the rule, authority, evidence, or policy basis for this judgment." />
            </label>
            <button className="dw-primary" disabled={saving || !selection.trim() || !rationale.trim()} onClick={recordDecision}>
              {saving ? 'Recording + re-evaluating…' : `Record once and re-evaluate ${selected.count} case${selected.count === 1 ? '' : 's'}`}
            </button>
            <p className="dw-boundary">This records operator judgment and requests governed reevaluation. It does not directly mutate YES/NO/HOLD or settlement authorization.</p>
          </section>

          <section className="dw-card">
            <div className="dw-card-head"><span>3 · Precedent</span><strong>{context?.precedents?.length || 0} related</strong></div>
            {(context?.precedents || []).length ? (context.precedents || []).map(p => <div className="dw-precedent" key={p.decision_id}>
              <div><strong>{p.selection}</strong><span>{p.rationale}</span></div><small>{p.decision_id}</small>
            </div>) : <p className="dw-muted">No prior governed decisions of this type yet. This decision can become future precedent.</p>}
          </section>

          {result && <section className="dw-card dw-result">
            <div className="dw-card-head"><span>4 · Re-evaluation</span><strong>{result.decision?.decision_id}</strong></div>
            <h3>Decision recorded. Queue re-evaluated.</h3>
            <div className="dw-compare">
              <div><span>Before</span><strong>{before?.active_cases ?? '—'} cases</strong><small>{before?.human_decisions ?? '—'} human decisions</small></div>
              <div className="arrow">→</div>
              <div><span>After</span><strong>{after?.active_cases ?? '—'} cases</strong><small>{after?.human_decisions ?? '—'} human decisions</small></div>
            </div>
            <div className="dw-result-grid">
              <div><span>Cases cleared</span><strong>{result.reevaluation?.workload?.cases_cleared ?? 0}</strong></div>
              <div><span>Human decisions removed</span><strong>{result.reevaluation?.workload?.human_decisions_removed ?? 0}</strong></div>
              <div><span>Workflow items updated</span><strong>{result.application?.updated_case_ids?.length ?? 0}</strong></div>
              <div><span>Decision hash</span><strong className="mono">{String(result.decision?.decision_hash || '').slice(0, 18)}…</strong></div>
            </div>
          </section>}
        </>}
      </main>
    </div>
  </div>
}
