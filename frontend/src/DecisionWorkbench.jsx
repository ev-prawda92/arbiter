import React, { useEffect, useMemo, useState } from 'react'

async function json(path, options) {
  const res = await fetch(path, options)
  if (!res.ok) {
    const text = await res.text()
    let body = null
    try { body = JSON.parse(text) } catch { body = null }
    const err = new Error(body?.detail?.message || (typeof body?.detail === 'string' ? body.detail : '') || `${res.status} ${text || path}`)
    err.status = res.status
    err.body = body
    throw err
  }
  return res.json()
}

function post(path, body) {
  return json(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}

const TIER = { same_clause: 'Same clause', same_template: 'Same template', related: 'Related' }
const RELATION = {
  same_event: 'same event', same_series: 'same series, earlier event', cross_event: 'different event',
  cross_venue: 'other venue', decided: 'this contract',
}
const STATUS = {
  novel: ['First ruling', 'No precedent covers these contracts. This decision becomes the precedent.'],
  follows: ['Follows precedent', 'Agrees with the applicable ruling and cites it.'],
  consistent: ['Consistent', 'Agrees with the applicable ruling. It will be cited automatically.'],
  divergent: ['Departs from precedent', 'Explain what distinguishes these contracts, or overrule the precedent.'],
}

function AskArbiter() {
  const [q, setQ] = useState('')
  const [a, setA] = useState(null)
  const [busy, setBusy] = useState(false)
  async function ask(e) {
    e.preventDefault()
    if (!q.trim()) return
    setBusy(true)
    try { setA(await post('/api/ask', { question: q })) } catch (err) { setA({ answer: err.message, citations: [] }) } finally { setBusy(false) }
  }
  return <section className="dw-ask">
    <form onSubmit={ask}>
      <label htmlFor="dw-ask-q">Ask Arbiter</label>
      <input id="dw-ask-q" value={q} onChange={e => setQ(e.target.value)} placeholder="e.g. Do acting or interim leaders count?" />
      <button disabled={busy || !q.trim()}>{busy ? 'Searching…' : 'Ask'}</button>
    </form>
    {a && <div className={`dw-answer ${a.grounded ? '' : 'ungrounded'}`}>
      <p>{a.answer}</p>
      {(a.citations || []).map(c => <div className="dw-cite" key={c.precedent_id}>
        <b className="mono">{c.precedent_id}</b>
        <span>{c.why} · {c.contract_count} decided contract{c.contract_count === 1 ? '' : 's'}{c.matched_contracts ? ` · applied to ${c.matched_contracts} since` : ''}</span>
      </div>)}
      <small>{a.method || ''}</small>
    </div>}
  </section>
}

function PrecedentMatch({ m, onFollow }) {
  const r = m.ruling || {}
  return <div className={`dw-match tier-${m.tier}`}>
    <div className="dw-match-head">
      <span className="dw-tier">{TIER[m.tier] || m.tier}</span>
      <span className="dw-match-meta">{RELATION[m.relation] || m.relation} · score {Number(m.score).toFixed(2)} · <span className="mono">{m.precedent_id}</span> · {(r.decided_at || '').slice(0, 10)}</span>
    </div>
    <strong>“{r.selection}”</strong>
    {r.governing_rule && <p className="dw-match-rule">Rule: {r.governing_rule}</p>}
    {m.matched_clause && <div className="dw-clauses">
      <div><span>Clause ruled on</span><q>{m.matched_clause.precedent_clause}</q></div>
      <div><span>Clause in this contract</span><q>{m.matched_clause.contract_clause}</q></div>
    </div>}
    <div className="dw-match-foot">
      <small>{r.contracts} decided contract{r.contracts === 1 ? '' : 's'}{m.for_contract ? ` · matched on ${m.for_contract}` : ''}</small>
      {m.applies && onFollow && <button className="dw-secondary" onClick={() => onFollow(m)}>Follow this ruling</button>}
    </div>
  </div>
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
  // The outcome of the last recorded decision. Kept separate from the
  // per-pattern form state: a successful decision usually clears its own
  // pattern, which moves the selection on to the next one, and the payoff
  // must stay visible through that.
  const [outcome, setOutcome] = useState(null)
  const [error, setError] = useState('')
  const [cited, setCited] = useState([])
  const [governingRule, setGoverningRule] = useState('')
  const [check, setCheck] = useState(null)
  const [departMode, setDepartMode] = useState('distinguish')
  const [distinguish, setDistinguish] = useState('')

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
    setCited([])
    setGoverningRule('')
    setCheck(null)
    setDistinguish('')
    setDepartMode('distinguish')
    try {
      setContext(await json(`/api/decision-context/${encodeURIComponent(id)}`))
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => { loadOverview().catch(e => setError(e.message)) }, [])
  useEffect(() => { if (selected?.cluster_id) loadContext(selected.cluster_id) }, [selected?.cluster_id])

  // Live precedent check while the operator types the ruling.
  useEffect(() => {
    if (!selected?.cluster_id || !selection.trim()) { setCheck(null); return }
    const t = setTimeout(() => {
      post('/api/decisions/consistency', { cluster_id: selected.cluster_id, selection, precedent_ids: cited })
        .then(setCheck).catch(() => setCheck(null))
    }, 350)
    return () => clearTimeout(t)
  }, [selection, cited, selected?.cluster_id])

  function follow(m) {
    setSelection(m.ruling?.selection || '')
    setGoverningRule(m.ruling?.governing_rule || '')
    setCited(c => Array.from(new Set([...c, m.precedent_id])))
    if (!rationale.trim()) setRationale(`Follows precedent ${m.precedent_id}: the ${TIER[m.tier]?.toLowerCase()} applies to these contracts.`)
  }

  async function recordDecision() {
    if (!selected || !selection.trim() || !rationale.trim()) return
    setSaving(true)
    setError('')
    try {
      const divergent = check?.status === 'divergent'
      const next = await post('/api/decisions', {
        cluster_id: selected.cluster_id,
        selection,
        rationale,
        governing_rule: governingRule,
        precedent_ids: cited,
        distinguish: divergent && departMode === 'distinguish' ? distinguish : '',
        overrules: divergent && departMode === 'overrule' ? check?.precedent?.precedent_id : null,
        owner: 'Resolution Ops',
        actor: 'operator:resolution-ops',
      })
      setResult(next)
      setOutcome(next)
      setOverview(next.reevaluation?.overview || overview)
    } catch (e) {
      if (e.status === 409 && e.body?.detail?.consistency) setCheck(e.body.detail.consistency)
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const prompt = context?.decision_prompt || {}
  const clear = context?.clearability
  const clearable = clear ? clear.clearable : true
  const work = outcome?.reevaluation?.workload
  const before = work?.before
  const after = work?.after
  const decisionId = outcome?.decision?.decision_id
  const matches = context?.precedent_matches || []
  const status = check?.status
  const needsDeparture = status === 'divergent'
  const departureReady = !needsDeparture || departMode === 'overrule' || distinguish.trim()
  const clearedItems = (outcome?.reevaluation?.queue?.items || []).filter(i => i.governed_by?.decision_id === decisionId)

  return <div className="dw-shell">
    <header className="dw-header">
      <div>
        <span>Arbiter · Decision Operations</span>
        <h1>Make the smallest human decision. Clear everything else.</h1>
        <p>One governed judgment can apply to an entire repeated work pattern, then Arbiter re-evaluates the affected queue.</p>
      </div>
      <a href="/console.html">Back to console</a>
    </header>

    <AskArbiter />

    {error && <div className="dw-error">{error}</div>}

    <div className="dw-grid">
      <aside className="dw-patterns">
        <div className="dw-panel-title"><span>Work patterns</span><strong>{clusters.length}</strong></div>
        {clusters.map(c => <button key={c.cluster_id} className={c.cluster_id === selected?.cluster_id ? 'selected' : ''} onClick={() => { setOutcome(null); setClusterId(c.cluster_id) }}>
          <div><strong>{label(c.blocker_type)}</strong><span>{c.count} cases · {money(c.notional)}</span></div>
          <b>{c.count > 1 ? `${c.count}→1` : '1'}</b>
        </button>)}
      </aside>

      <main className="dw-main">
        {outcome && <section className="dw-card dw-result">
          <div className="dw-card-head"><span>Decision recorded · re-evaluated</span><button className="dw-dismiss" onClick={() => setOutcome(null)}>Dismiss</button></div>
          <h3>{work?.cases_cleared ? `One decision cleared ${work.cases_cleared} case${work.cases_cleared === 1 ? '' : 's'}.` : 'Decision recorded. Queue re-evaluated.'}</h3>
          <p className="dw-muted">“{outcome.decision?.selection}” · {decisionId}</p>
          {outcome.consistency && <p className={`dw-status status-${outcome.consistency.status}`}>
            <b>{STATUS[outcome.consistency.status]?.[0]}</b>
            <span>{outcome.consistency.precedent ? `${outcome.consistency.status === 'divergent' ? 'departs from' : 'with'} ${outcome.consistency.precedent.precedent_id}` : ''}
              {outcome.consistency.overruled?.length ? ` · overruled ${outcome.consistency.overruled.join(', ')}` : ''}
              {outcome.precedent ? ` · now precedent for future contracts (${outcome.precedent.clauses} clause${outcome.precedent.clauses === 1 ? '' : 's'}, ${outcome.precedent.contracts} contract${outcome.precedent.contracts === 1 ? '' : 's'})` : ''}</span>
          </p>}
          <div className="dw-compare">
            <div><span>Before</span><strong>{before?.active_cases ?? '—'} cases</strong><small>{before?.human_decisions ?? '—'} human decisions</small></div>
            <div className="arrow">→</div>
            <div><span>After</span><strong>{after?.active_cases ?? '—'} cases</strong><small>{after?.human_decisions ?? '—'} human decisions</small></div>
          </div>
          <div className="dw-result-grid">
            <div><span>Cases cleared</span><strong>{work?.cases_cleared ?? 0}</strong></div>
            <div><span>Human decisions removed</span><strong>{work?.human_decisions_removed ?? 0}</strong></div>
            <div><span>Workflow items updated</span><strong>{outcome.application?.updated_case_ids?.length ?? 0}</strong></div>
            <div><span>Decision hash</span><strong className="mono">{String(outcome.decision?.decision_hash || '').slice(0, 18)}…</strong></div>
          </div>
          {clearedItems.length > 0 && <div className="dw-cleared">
            <span>Cleared by this decision</span>
            <div>{clearedItems.map(i => <b key={i.id}>{i.subject}</b>)}</div>
          </div>}
          <p className="dw-boundary">Cleared work is operator workflow only. YES/NO/HOLD outcomes, settlement and payout are unchanged, and payout holds are never cleared by a decision.</p>
        </section>}

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
            <div className="dw-card-head"><span>2 · Precedent</span><strong>{matches.length ? `${matches.length} appl${matches.length === 1 ? 'ies' : 'y'}` : 'none applies'}</strong></div>
            {matches.length ? matches.map(m => <PrecedentMatch key={m.precedent_id} m={m} onFollow={follow} />)
              : <p className="dw-muted">No earlier ruling covers these contracts{(context?.precedents || []).length ? ` (${context.precedents.length} decision${context.precedents.length === 1 ? '' : 's'} of this type exist, none on this wording)` : ''}. This decision will become precedent for future contracts with the same clause or template.</p>}
          </section>

          <section className="dw-card">
            <div className="dw-card-head"><span>3 · Record decision</span><strong>Audited</strong></div>
            {!clearable && <div className="dw-notice"><strong>This decision won’t clear cases.</strong><span>{clear.reason}</span></div>}
            <label>
              <span>Decision</span>
              <input value={selection} onChange={e => setSelection(e.target.value)} placeholder="e.g. Initial official release controls" />
            </label>
            {status && <div className={`dw-status status-${status}`}>
              <b>{STATUS[status]?.[0]}</b><span>{STATUS[status]?.[1]}</span>
              {check?.conflicting?.length > 0 && <span className="dw-split">Earlier rulings disagree: {check.conflicting.map(c => `“${c.selection}” (${c.precedent_ids.join(', ')})`).join(' vs ')}</span>}
            </div>}
            {needsDeparture && <div className="dw-depart">
              <div className="dw-depart-choice">
                <label><input type="radio" checked={departMode === 'distinguish'} onChange={() => setDepartMode('distinguish')} /> Distinguish: these contracts differ</label>
                <label><input type="radio" checked={departMode === 'overrule'} onChange={() => setDepartMode('overrule')} /> Overrule {check?.precedent?.precedent_id}</label>
              </div>
              {departMode === 'distinguish'
                ? <textarea value={distinguish} onChange={e => setDistinguish(e.target.value)} placeholder="What in these contracts' terms or facts differs from the precedent?" />
                : <p className="dw-muted">Overruling is prospective. {check?.precedent?.precedent_id} and every ruling holding the same keep governing the cases they decided, but stop guiding new contracts.</p>}
            </div>}
            <label>
              <span>Governing rule <small>(optional)</small></span>
              <input value={governingRule} onChange={e => setGoverningRule(e.target.value)} placeholder="The rule future contracts should be read by" />
            </label>
            <label>
              <span>Rationale</span>
              <textarea value={rationale} onChange={e => setRationale(e.target.value)} placeholder="Explain the rule, authority, evidence, or policy basis for this judgment." />
            </label>
            <button className="dw-primary" disabled={saving || !selection.trim() || !rationale.trim() || !departureReady} onClick={recordDecision}>
              {saving ? 'Recording + re-evaluating…' : clearable
                ? `Record once and clear ${selected.count} case${selected.count === 1 ? '' : 's'}`
                : 'Record decision (cases stay open)'}
            </button>
            <p className="dw-boundary">This records operator judgment and requests governed reevaluation. It does not directly mutate YES/NO/HOLD or settlement authorization.</p>
          </section>

        </>}
      </main>
    </div>
  </div>
}
