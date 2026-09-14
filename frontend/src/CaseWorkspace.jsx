import React, { useEffect, useMemo, useState } from 'react'
import './case-workspace.css'

function labelize(value) {
  return String(value || '—').replaceAll('_', ' ').replace(/\b\w/g, m => m.toUpperCase())
}

function money(n) {
  if (n === 0) return '$0'
  if (!n) return '—'
  return `$${(Number(n) / 1e6).toFixed(Number(n) >= 1e7 ? 0 : 1)}M`
}

function shortTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

async function getJson(path, options) {
  const response = await fetch(path, options)
  if (!response.ok) throw new Error(`${path} returned ${response.status}`)
  return response.json()
}

async function optionalJson(path) {
  try { return await getJson(path) } catch { return null }
}

function StatePill({ value }) {
  const raw = String(value || 'review').toLowerCase()
  const tone = raw.includes('resolved') || raw.includes('ready') || raw.includes('yes')
    ? 'good'
    : raw.includes('hold') || raw.includes('investigat') || raw.includes('wait') || raw.includes('review') || raw.includes('policy')
      ? 'warn'
      : 'neutral'
  return <span className={`cw-pill ${tone}`}>{labelize(value)}</span>
}

function Step({ number, eyebrow, title, children, action }) {
  return <section className="cw-step">
    <div className="cw-step-number">{number}</div>
    <div className="cw-step-body">
      <div className="cw-step-head"><div><span>{eyebrow}</span><h3>{title}</h3></div>{action}</div>
      {children}
    </div>
  </section>
}

function workflowFor(id, operations, fallback = 'INVESTIGATING') {
  if (!id || !operations) return fallback
  if ((operations.ready_cases || []).some(x => x.id === id)) return 'READY_FOR_REVIEW'
  if ((operations.waiting_cases || []).some(x => x.id === id)) return 'WAITING'
  if ((operations.policy_cases || []).some(x => x.id === id)) return 'POLICY_REVIEW'
  if ((operations.investigating_cases || []).some(x => x.id === id)) return 'INVESTIGATING'
  return fallback
}

function blockerFor(id, operations, fallback = 'operator_review') {
  const all = [
    ...(operations?.ready_cases || []),
    ...(operations?.investigating_cases || []),
    ...(operations?.waiting_cases || []),
    ...(operations?.policy_cases || []),
  ]
  return all.find(x => x.id === id)?.blocker_type || fallback
}

function fallbackAction(blocker, state) {
  if (state === 'WAITING') return { label: 'Check dependency', detail: 'Confirm what external evidence is still missing and when it is expected.' }
  if (state === 'READY_FOR_REVIEW') return { label: 'Review governed resolution', detail: 'The deterministic checks are complete enough for a human review.' }
  const actions = {
    evidence_conflict: ['Review conflicting evidence', 'Compare governed evidence records and identify which source controls.'],
    evidence_review: ['Review evidence sufficiency', 'Inspect the evidence packet and confirm it satisfies the contract requirements.'],
    evidence_missing: ['Request or await evidence', 'Identify the missing evidence dependency and keep the case on HOLD until it arrives.'],
    authority_conflict: ['Review authority precedence', 'Determine which governed authority controls under the contract and policy.'],
    timing_revision: ['Review timing / revision', 'Confirm the controlling observation window and whether a revision supersedes earlier evidence.'],
    policy_interpretation: ['Escalate policy judgment', 'Send the irreducible policy interpretation to the appropriate human reviewer.'],
    resolution_hold: ['Investigate HOLD', 'Resolve the blocking authority, evidence, timing, or policy condition before review.'],
    audit_integrity: ['Review audit integrity', 'Stop settlement-sensitive work until the audit issue is explained and repaired.'],
  }
  const [label, detail] = actions[blocker] || ['Review case', 'Inspect the governed record and identify the smallest decision needed to move it forward.']
  return { label, detail }
}

function fallbackWhy(blocker, state) {
  if (state === 'WAITING') return 'No human decision can clear this yet; the case is waiting on an external dependency.'
  if (state === 'READY_FOR_REVIEW') return 'Arbiter has reduced the case to a reviewable decision, but a human still owns the governed approval step.'
  const reasons = {
    evidence_conflict: 'Two or more evidence signals disagree, so Arbiter cannot safely choose a controlling fact on its own.',
    evidence_review: 'Evidence exists, but it still needs a governed sufficiency check before the case can advance.',
    evidence_missing: 'A required fact is missing. Arbiter should hold rather than infer it.',
    authority_conflict: 'The controlling source is ambiguous or contested, so source precedence needs governed judgment.',
    timing_revision: 'The outcome depends on timing or revision semantics that still need to be reconciled.',
    policy_interpretation: 'The remaining question is policy judgment rather than data retrieval.',
    resolution_hold: 'A binding prerequisite is unresolved, so the deterministic core correctly keeps the case on HOLD.',
    audit_integrity: 'Audit integrity is part of the control boundary and cannot be bypassed by an operator shortcut.',
  }
  return reasons[blocker] || 'The case still contains an unresolved governed exception that should not be auto-cleared.'
}

function answerQuestion(question, cluster, selected, workflowState, blocker, precedents) {
  if (!cluster) return 'Select a work pattern first.'
  const q = question.toLowerCase()
  if (q.includes('why') && q.includes('human')) return cluster.why_human || fallbackWhy(blocker, workflowState)
  if (q.includes('clear')) return cluster.clear_condition || 'Clear the governed blocker and re-evaluate the affected case.'
  if (q.includes('fact') || q.includes('control')) return `${cluster.authority_summary || 'Review the governed authority.'} ${cluster.evidence_summary || ''}`.trim()
  if (q.includes('seen') || q.includes('pattern')) return precedents.length
    ? `Arbiter found ${precedents.length} related prior record${precedents.length === 1 ? '' : 's'} with similar resolution language or workflow state. Review them as context, not binding precedent.`
    : cluster.count > 1
      ? `Arbiter grouped ${cluster.count} active cases into this same ${labelize(cluster.blocker_type).toLowerCase()} pattern. No prior resolved record is linked yet.`
      : 'No related prior resolved record is linked yet.'
  if (q.includes('next')) return `${cluster.primary_action || selected?.recommended_action || 'Review the case'}. ${cluster.clear_condition || ''}`.trim()
  return `${cluster.root_cause || selected?.detail || 'A governed exception remains unresolved.'} ${cluster.why_human || ''}`.trim()
}

export default function CaseWorkspace() {
  const [open, setOpen] = useState(false)
  const [queue, setQueue] = useState(null)
  const [overview, setOverview] = useState(null)
  const [authorities, setAuthorities] = useState([])
  const [caseHistory, setCaseHistory] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [selectedClusterId, setSelectedClusterId] = useState('')
  const [filter, setFilter] = useState('all')
  const [detail, setDetail] = useState(null)
  const [specDetail, setSpecDetail] = useState(null)
  const [evidenceRecords, setEvidenceRecords] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [owner, setOwner] = useState('')
  const [note, setNote] = useState('')
  const [status, setStatus] = useState('open')
  const [saving, setSaving] = useState(false)
  const [askOpen, setAskOpen] = useState(false)
  const [askQuestion, setAskQuestion] = useState('Why does this need a human?')
  const [askAnswer, setAskAnswer] = useState('')
  const [casesExpanded, setCasesExpanded] = useState(false)
  const [reeval, setReeval] = useState(null)
  const [reevalLoading, setReevalLoading] = useState(false)
  const [clusterActionLoading, setClusterActionLoading] = useState(false)

  const active = useMemo(() => (queue?.items || []).filter(item => item.status !== 'resolved'), [queue])
  const operations = overview?.agent_brief?.operations_intelligence
  const clusters = operations?.clusters || []

  const filteredClusters = useMemo(() => clusters.filter(cluster => {
    const states = cluster.workflow_states || []
    if (filter === 'repeated') return cluster.count >= 2
    if (filter === 'ready') return states.includes('READY_FOR_REVIEW')
    if (filter === 'waiting') return states.includes('WAITING')
    if (filter === 'judgment') return states.includes('INVESTIGATING') || states.includes('POLICY_REVIEW')
    if (filter === 'high') return Number(cluster.notional || 0) >= 1_000_000 || Number(cluster.max_priority_score || 0) >= 100
    return true
  }), [clusters, filter])

  const selectedCluster = useMemo(() => clusters.find(c => c.cluster_id === selectedClusterId) || filteredClusters[0] || clusters[0] || null, [clusters, filteredClusters, selectedClusterId])
  const clusterCases = useMemo(() => selectedCluster ? active.filter(item => (selectedCluster.case_ids || []).includes(item.id)) : [], [active, selectedCluster])
  const selected = useMemo(() => active.find(item => item.id === selectedId) || clusterCases[0] || active[0] || null, [active, clusterCases, selectedId])

  const precedents = useMemo(() => {
    const terms = `${selectedCluster?.blocker_type || ''} ${selected?.kind || ''} ${selected?.recommended_action || ''}`.toLowerCase().split(/\W+/).filter(x => x.length > 4)
    const resolvedQueue = (queue?.items || []).filter(i => i.status === 'resolved')
    const priorCases = caseHistory.map(c => ({ id: c.case_id, title: c.title || c.case_id, detail: c.criteria || '', source: 'saved case', status: c.status || c.compiler_status || 'review' }))
    return [...resolvedQueue.map(i => ({ ...i, source: 'resolved work' })), ...priorCases]
      .map(item => ({ item, score: terms.reduce((n, t) => n + (`${item.title || ''} ${item.detail || ''} ${item.kind || ''}`.toLowerCase().includes(t) ? 1 : 0), 0) }))
      .filter(x => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
      .map(x => x.item)
  }, [queue, caseHistory, selectedCluster?.cluster_id, selected?.id])

  const authorityById = useMemo(() => Object.fromEntries(authorities.map(a => [a.authority_id || a.id, a])), [authorities])

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [nextQueue, nextOverview, authorityData, historyData] = await Promise.all([
        getJson('/api/work-queue'), getJson('/api/overview'), optionalJson('/api/authorities'), optionalJson('/api/cases?limit=50')
      ])
      setQueue(nextQueue)
      setOverview(nextOverview)
      setAuthorities(authorityData?.authorities || [])
      setCaseHistory(historyData?.cases || [])
      const firstCluster = nextOverview?.agent_brief?.operations_intelligence?.clusters?.[0]
      const first = (nextQueue.items || []).find(item => item.status !== 'resolved')
      if (!selectedClusterId && firstCluster) setSelectedClusterId(firstCluster.cluster_id)
      if (!selectedId && first) setSelectedId(first.id)
    } catch (e) {
      setError(e.message || 'Unable to load case workspace')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (open && !queue) load() }, [open])

  useEffect(() => {
    if (!selectedCluster || !clusterCases.length) return
    if (!clusterCases.some(item => item.id === selectedId)) setSelectedId(clusterCases[0].id)
    setAskAnswer('')
    setCasesExpanded(false)
    setReeval(null)
  }, [selectedCluster?.cluster_id])

  useEffect(() => {
    if (!selected) return
    setOwner(selected.owner || '')
    setNote(selected.note || '')
    setStatus(selected.status || 'open')
    setDetail(null)
    setSpecDetail(null)
    setEvidenceRecords([])
    setAskAnswer('')
    if (!selected.subject) return
    let cancelled = false
    Promise.all([
      optionalJson(`/api/markets/${encodeURIComponent(selected.subject)}`),
      optionalJson(`/api/contracts/${encodeURIComponent(selected.subject)}/resolution-spec`),
      optionalJson(`/api/evidence?contract_id=${encodeURIComponent(selected.subject)}&limit=50`),
    ]).then(([market, spec, ev]) => {
      if (cancelled) return
      setDetail(market)
      setSpecDetail(spec)
      setEvidenceRecords(ev?.evidence || [])
    })
    return () => { cancelled = true }
  }, [selected?.id])

  async function saveWorkState(nextStatus = status, nextNote = note) {
    if (!selected) return
    setSaving(true)
    setError('')
    try {
      const result = await getJson(`/api/work-queue/${encodeURIComponent(selected.id)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus, owner, note: nextNote, actor: 'operator:resolution-ops' }),
      })
      setQueue(result.queue)
      setStatus(nextStatus)
      setNote(nextNote)
    } catch (e) {
      setError(e.message || 'Unable to update case state')
    } finally {
      setSaving(false)
    }
  }

  async function reEvaluate() {
    setReevalLoading(true)
    setError('')
    const before = operations?.summary || {}
    try {
      const [nextQueue, nextOverview] = await Promise.all([getJson('/api/work-queue'), getJson('/api/overview')])
      setQueue(nextQueue)
      setOverview(nextOverview)
      const after = nextOverview?.agent_brief?.operations_intelligence?.summary || {}
      setReeval({ before, after, at: new Date().toISOString() })
    } catch (e) {
      setError(e.message || 'Unable to re-evaluate governed work')
    } finally {
      setReevalLoading(false)
    }
  }

  async function startClusterAction() {
    if (!selectedCluster || !clusterCases.length) return
    setClusterActionLoading(true)
    setError('')
    const clusterNote = `Cluster review started: ${selectedCluster.primary_action || 'Review shared root cause'}. Governed resolution unchanged.`
    try {
      for (const item of clusterCases) {
        await getJson(`/api/work-queue/${encodeURIComponent(item.id)}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'in_progress', owner: item.owner || owner || 'Resolution Ops', note: clusterNote, actor: 'operator:resolution-ops' }),
        })
      }
      setStatus('in_progress')
      await reEvaluate()
    } catch (e) {
      setError(e.message || 'Unable to start cluster review')
    } finally {
      setClusterActionLoading(false)
    }
  }

  const workflowState = workflowFor(selected?.id, operations, selectedCluster?.dominant_state || selected?.status || 'INVESTIGATING')
  const blocker = blockerFor(selected?.id, operations, selectedCluster?.blocker_type || selected?.kind)
  const fallback = fallbackAction(blocker, workflowState)
  const action = { label: selectedCluster?.primary_action || fallback.label, detail: selectedCluster?.clear_condition || selected?.recommended_action || fallback.detail }
  const report = detail?.report || {}
  const resolution = detail?.resolution || {}
  const packet = detail?.evidence_packet || {}
  const spec = specDetail?.spec || {}
  const affectedNotional = selectedCluster?.notional || selected?.notional || 0
  const humanWhy = selectedCluster?.why_human || fallbackWhy(blocker, workflowState)
  const externalWait = (selectedCluster?.workflow_states || []).every(s => s === 'WAITING') || workflowState === 'WAITING'
  const actionability = externalWait ? 'Waiting on external world' : 'Human action required'

  function ask(question) {
    setAskQuestion(question)
    setAskAnswer(answerQuestion(question, selectedCluster, selected, workflowState, blocker, precedents))
  }

  return <>
    <button className="cw-launch" onClick={() => setOpen(true)} aria-label="Open case workspace"><span>Case workspace</span><b>{active.length || ''}</b></button>
    {open && <div className="cw-backdrop" onMouseDown={e => e.target === e.currentTarget && setOpen(false)}>
      <div className="cw-shell">
        <header className="cw-header">
          <div><span>Arbiter v0.33 · Operator loop</span><h2>Clear the decisions that actually need a human</h2><p>Investigate the shared root cause, act once where governance permits, then re-evaluate every affected case.</p></div>
          <div className="cw-header-actions"><button onClick={load} disabled={loading}>Refresh</button><button className="cw-close" onClick={() => setOpen(false)}>×</button></div>
        </header>

        {error && <div className="cw-error">{error}</div>}
        <div className="cw-filterbar">
          {[['all','All work'],['repeated','Repeated issues'],['ready','Ready now'],['waiting','Waiting'],['judgment','Human judgment'],['high','High impact']].map(([key,label]) => <button key={key} className={filter === key ? 'selected' : ''} onClick={() => setFilter(key)}>{label}</button>)}
        </div>

        <div className="cw-layout">
          <aside className="cw-queue">
            <div className="cw-queue-head"><div><span>Work patterns</span><small>{active.length} cases compressed into {clusters.length}</small></div><strong>{filteredClusters.length}</strong></div>
            {loading && !queue && <p className="cw-muted">Loading governed work…</p>}
            {filteredClusters.map(cluster => <button key={cluster.cluster_id} className={cluster.cluster_id === selectedCluster?.cluster_id ? 'selected' : ''} onClick={() => { setSelectedClusterId(cluster.cluster_id); setSelectedId('') }}>
              <div className="cw-cluster-copy"><strong>{labelize(cluster.blocker_type)}</strong><span>{cluster.count} {cluster.count === 1 ? 'case' : 'cases'} · {labelize(cluster.dominant_state || cluster.workflow_states?.[0])}</span><small>{cluster.root_cause || cluster.recommended_action || 'Review shared root cause.'}</small></div>
              <div className="cw-cluster-impact"><b>{money(cluster.notional)}</b><em>{cluster.count > 1 ? `${cluster.count}→1` : '1'}</em></div>
            </button>)}
            {!filteredClusters.length && <p className="cw-muted">No work patterns match this view.</p>}
          </aside>

          <main className="cw-main">
            {!selected ? <div className="cw-empty">No active cases require operator attention.</div> : <>
              <section className="cw-focus">
                <div className="cw-focus-copy"><span className="cw-eyebrow">Current decision</span><h2>{labelize(selectedCluster?.blocker_type || blocker)}</h2><p>{selectedCluster?.pattern_summary || selectedCluster?.root_cause || selected.detail}</p><span className={`cw-actionability ${externalWait ? 'waiting' : 'human'}`}>{actionability}</span></div>
                <div className="cw-focus-metrics"><div><span>Affected</span><strong>{selectedCluster?.count || 1} case{(selectedCluster?.count || 1) === 1 ? '' : 's'}</strong></div><div><span>Notional</span><strong>{money(affectedNotional)}</strong></div><div><span>State</span><StatePill value={selectedCluster?.dominant_state || workflowState} /></div></div>
              </section>

              {clusterCases.length > 1 && <section className="cw-case-strip">
                <button className="cw-case-strip-toggle" onClick={() => setCasesExpanded(v => !v)}><div><span>Underlying cases</span><strong>{clusterCases.length} records · open only when needed</strong></div><b>{casesExpanded ? 'Hide' : 'View cases'}</b></button>
                {casesExpanded && <div className="cw-case-chips">{clusterCases.map(item => <button key={item.id} className={item.id === selected.id ? 'selected' : ''} onClick={() => setSelectedId(item.id)}>{item.subject || item.title}</button>)}</div>}
              </section>}

              <div className="cw-guided-flow">
                <Step number="1" eyebrow="Understand" title="What happened?">
                  <p className="cw-lead">{selectedCluster?.root_cause || selected.detail || selected.title}</p>
                  <div className="cw-inline-meta"><span>{selected.subject || selected.id}</span><span>{labelize(selected.kind)}</span><span>{money(selected.notional)}</span></div>
                </Step>

                <Step number="2" eyebrow="Evidence + authority" title="What actually controls?">
                  <div className="cw-facts"><div><span>Authority order</span><strong>{(spec.source_precedence || spec.authority_ids || []).map(id => authorityById[id]?.name || id).join(' → ') || selectedCluster?.authority_summary || 'No contract-level authority order linked'}</strong></div><div><span>Timing</span><strong>{spec.timing ? Object.entries(spec.timing).map(([k,v]) => `${labelize(k)}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ') : 'No resolution timing spec linked'}</strong></div><div><span>Revision policy</span><strong>{spec.revision_policy && Object.keys(spec.revision_policy).length ? JSON.stringify(spec.revision_policy) : blocker === 'timing_revision' ? 'Revision semantics require review' : 'No revision rule linked'}</strong></div></div>
                  <div className="cw-evidence-compare">
                    {evidenceRecords.length ? evidenceRecords.slice(0, 4).map(ev => <article key={ev.evidence_id} className="cw-evidence-card"><div><span>{authorityById[ev.authority_id]?.name || ev.authority_id}</span><StatePill value={ev.revision_number > 1 ? `Revision ${ev.revision_number}` : 'Evidence'} /></div><strong>{typeof ev.normalized_value === 'object' ? JSON.stringify(ev.normalized_value) : String(ev.normalized_value ?? '—')}</strong><dl><dt>Observed</dt><dd>{shortTime(ev.observed_at)}</dd><dt>Effective</dt><dd>{shortTime(ev.effective_at)}</dd><dt>Retrieved</dt><dd>{shortTime(ev.retrieved_at)}</dd><dt>Source</dt><dd>{ev.source_locator || 'Governed record'}</dd></dl></article>) : <div className="cw-evidence-empty"><strong>No governed evidence records linked to this contract yet.</strong><span>That is itself useful: Arbiter should not invent evidence. Link or ingest the authoritative record before this case can clear.</span></div>}
                  </div>
                  <div className="cw-why-human"><span>Why human?</span><strong>{humanWhy}</strong></div>
                </Step>

                <Step number="3" eyebrow="Precedent + intelligence" title="What has Arbiter learned?" action={<button className="cw-text-button" onClick={() => setAskOpen(v => !v)}>{askOpen ? 'Hide' : 'Ask Arbiter'}</button>}>
                  <p className="cw-lead">{selectedCluster?.pattern_summary || `Arbiter classified this as ${labelize(blocker).toLowerCase()} and kept it out of the ready queue.`}</p>
                  <div className="cw-precedents">{precedents.length ? precedents.map(p => <div key={p.id || p.case_id}><span>{labelize(p.source || 'prior record')}</span><strong>{p.title || p.id}</strong><small>{p.detail || p.recommended_action || 'Related prior governed record.'}</small></div>) : <div className="cw-precedent-empty">No related resolved precedent is linked yet. Arbiter will surface prior governed decisions here as the resolution history grows.</div>}</div>
                  {askOpen && <div className="cw-ask"><div className="cw-ask-head"><strong>Ask about this decision</strong><span>Governed context · advisory only</span></div><div className="cw-question-chips">{['Why does this need a human?','What would clear this?','Which fact controls?','Have we seen this pattern before?','What should I do next?'].map(q => <button key={q} className={askQuestion === q && askAnswer ? 'selected' : ''} onClick={() => ask(q)}>{q}</button>)}</div>{askAnswer ? <div className="cw-answer"><span>Arbiter</span><p>{askAnswer}</p></div> : <p className="cw-ask-hint">Choose a question. Answers use the selected governed context; no resolution state is changed.</p>}</div>}
                </Step>

                <Step number="4" eyebrow="Act once" title="Apply the workflow action to the pattern">
                  <div className="cw-primary-action"><div><span>Recommended next action</span><h4>{action.label}</h4><p>{action.detail}</p></div><button onClick={startClusterAction} disabled={clusterActionLoading || externalWait}>{clusterActionLoading ? 'Starting…' : externalWait ? 'Waiting externally' : selectedCluster?.count > 1 ? `Start for ${selectedCluster.count} cases` : 'Start governed review'}</button></div>
                  <p className="cw-boundary-note">This applies workflow state and ownership across the pattern. It never changes contract terms, evidence, or a binding YES/NO/HOLD outcome.</p>
                  <details className="cw-handoff"><summary>Ownership & handoff</summary><div className="cw-edit-grid"><label><span>Status</span><select value={status} onChange={e => setStatus(e.target.value)}><option value="open">Open</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option></select></label><label><span>Owner</span><input value={owner} onChange={e => setOwner(e.target.value)} placeholder="Operator or team" /></label><label className="wide"><span>Handoff note</span><textarea value={note} onChange={e => setNote(e.target.value)} placeholder="What changed, what remains, and what the next reviewer needs to know." /></label><div className="wide cw-action-row"><button className="primary" onClick={() => saveWorkState()} disabled={saving}>{saving ? 'Saving…' : 'Save operator state'}</button><span>Workflow state only — never contract terms or resolution outcomes.</span></div></div></details>
                </Step>

                <Step number="5" eyebrow="Re-evaluate" title="What cleared after the action?" action={<button className="cw-text-button" onClick={reEvaluate} disabled={reevalLoading}>{reevalLoading ? 'Checking…' : 'Re-evaluate now'}</button>}>
                  <p className="cw-clear-condition"><span>Clear condition</span><strong>{selectedCluster?.clear_condition || action.detail}</strong></p>
                  <div className="cw-workload-delta"><div><span>Current queue</span><strong>{operations?.summary?.active_cases ?? active.length}</strong><small>active cases</small></div><div><span>Human decisions</span><strong>{operations?.summary?.estimated_human_decisions ?? clusters.length}</strong><small>patterns requiring action</small></div><div><span>External waits</span><strong>{operations?.summary?.waiting_on_external_data ?? 0}</strong><small>do not spend operator time</small></div><div><span>Touches avoided</span><strong>{operations?.summary?.human_decisions_avoided ?? 0}</strong><small>through compression</small></div></div>
                  {reeval && <div className="cw-reeval-result"><strong>Re-evaluated {shortTime(reeval.at)}</strong><span>{(reeval.before.active_cases || 0) - (reeval.after.active_cases || 0)} cases cleared · {(reeval.before.estimated_human_decisions || 0) - (reeval.after.estimated_human_decisions || 0)} human decisions removed. If nothing changed, the governed blocker is still live.</span></div>}
                  <div className="cw-progress"><div className="done"><b>1</b><span>Exception identified</span></div><div className={workflowState === 'INVESTIGATING' || workflowState === 'POLICY_REVIEW' ? 'current' : 'done'}><b>2</b><span>Root cause investigated</span></div><div className={workflowState === 'WAITING' ? 'current' : workflowState === 'READY_FOR_REVIEW' ? 'done' : ''}><b>3</b><span>{workflowState === 'WAITING' ? 'Dependency arrives' : 'Governed checks satisfied'}</span></div><div className={workflowState === 'READY_FOR_REVIEW' ? 'current' : ''}><b>4</b><span>Human review</span></div><div><b>5</b><span>Resolution + audit</span></div></div>
                </Step>
              </div>
            </>}
          </main>
        </div>
      </div>
    </div>}
  </>
}
