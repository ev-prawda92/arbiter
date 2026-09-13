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

async function getJson(path, options) {
  const response = await fetch(path, options)
  if (!response.ok) throw new Error(`${path} returned ${response.status}`)
  return response.json()
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
  if ((operations.investigating_cases || []).some(x => x.id === id)) return 'INVESTIGATING'
  return fallback
}

function blockerFor(id, operations, fallback = 'operator_review') {
  const all = [
    ...(operations?.ready_cases || []),
    ...(operations?.investigating_cases || []),
    ...(operations?.waiting_cases || []),
  ]
  return all.find(x => x.id === id)?.blocker_type || fallback
}

function primaryAction(blocker, state) {
  if (state === 'WAITING') return { label: 'Check evidence dependency', detail: 'Confirm what external evidence is still missing and when it is expected.' }
  if (state === 'READY_FOR_REVIEW') return { label: 'Review governed resolution', detail: 'The deterministic checks are complete enough for a human review.' }
  const actions = {
    evidence_conflict: ['Review conflicting evidence', 'Compare the governed evidence records and identify which source controls.'],
    evidence_review: ['Review evidence record', 'Inspect the evidence packet and confirm it satisfies the contract requirements.'],
    evidence_missing: ['Request evidence', 'Identify the missing evidence dependency and keep the case on HOLD until it arrives.'],
    authority_conflict: ['Review authority precedence', 'Determine which governed authority controls under the contract and policy.'],
    timing_revision: ['Review timing / revision', 'Confirm the controlling observation window and whether a revision supersedes earlier evidence.'],
    policy_interpretation: ['Escalate policy judgment', 'Send the irreducible policy interpretation to the appropriate human reviewer.'],
    resolution_hold: ['Investigate HOLD', 'Resolve the blocking authority, evidence, timing, or policy condition before review.'],
    audit_integrity: ['Review audit integrity', 'Stop settlement-sensitive work until the audit issue is explained and repaired.'],
  }
  const [label, detail] = actions[blocker] || ['Review case', 'Inspect the governed record and identify the smallest decision needed to move it forward.']
  return { label, detail }
}

function humanWhy(blocker, state) {
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

export default function CaseWorkspace() {
  const [open, setOpen] = useState(false)
  const [queue, setQueue] = useState(null)
  const [overview, setOverview] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [selectedClusterId, setSelectedClusterId] = useState('')
  const [filter, setFilter] = useState('all')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [owner, setOwner] = useState('')
  const [note, setNote] = useState('')
  const [status, setStatus] = useState('open')
  const [saving, setSaving] = useState(false)
  const [askOpen, setAskOpen] = useState(false)

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

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [nextQueue, nextOverview] = await Promise.all([getJson('/api/work-queue'), getJson('/api/overview')])
      setQueue(nextQueue)
      setOverview(nextOverview)
      const nextOps = nextOverview?.agent_brief?.operations_intelligence
      const firstCluster = nextOps?.clusters?.[0]
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
  }, [selectedCluster?.cluster_id])

  useEffect(() => {
    if (!selected) return
    setOwner(selected.owner || '')
    setNote(selected.note || '')
    setStatus(selected.status || 'open')
    setDetail(null)
    if (!selected.subject || !['resolution_hold', 'monitored_contract'].includes(selected.kind)) return
    let cancelled = false
    getJson(`/api/markets/${encodeURIComponent(selected.subject)}`)
      .then(value => { if (!cancelled) setDetail(value) })
      .catch(() => { if (!cancelled) setDetail(null) })
    return () => { cancelled = true }
  }, [selected?.id])

  async function saveWorkState() {
    if (!selected) return
    setSaving(true)
    setError('')
    try {
      const result = await getJson(`/api/work-queue/${encodeURIComponent(selected.id)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, owner, note, actor: 'operator:resolution-ops' }),
      })
      setQueue(result.queue)
    } catch (e) {
      setError(e.message || 'Unable to update case state')
    } finally {
      setSaving(false)
    }
  }

  const workflowState = workflowFor(selected?.id, operations, selected?.status || 'INVESTIGATING')
  const blocker = blockerFor(selected?.id, operations, selected?.kind)
  const action = primaryAction(blocker, workflowState)
  const report = detail?.report || {}
  const resolution = detail?.resolution || {}
  const packet = detail?.evidence_packet || {}
  const affectedNotional = selectedCluster?.notional || selected?.notional || 0

  return <>
    <button className="cw-launch" onClick={() => setOpen(true)} aria-label="Open case workspace"><span>Case workspace</span><b>{active.length || ''}</b></button>
    {open && <div className="cw-backdrop" onMouseDown={e => e.target === e.currentTarget && setOpen(false)}>
      <div className="cw-shell">
        <header className="cw-header">
          <div><span>Arbiter v0.32 · Resolution operations</span><h2>Clear the decisions that actually need a human</h2><p>Arbiter groups repetitive exceptions into shared root causes, then guides the operator through the smallest safe next decision.</p></div>
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
              <div className="cw-cluster-copy"><strong>{labelize(cluster.blocker_type)}</strong><span>{cluster.count} {cluster.count === 1 ? 'case' : 'cases'} · {cluster.workflow_states?.map(labelize).join(' / ')}</span><small>{cluster.recommended_action || 'Review shared root cause.'}</small></div>
              <div className="cw-cluster-impact"><b>{money(cluster.notional)}</b><em>{cluster.count > 1 ? `${cluster.count}→1` : '1'}</em></div>
            </button>)}
            {!filteredClusters.length && <p className="cw-muted">No work patterns match this view.</p>}
          </aside>

          <main className="cw-main">
            {!selected ? <div className="cw-empty">No active cases require operator attention.</div> : <>
              <section className="cw-focus">
                <div className="cw-focus-copy"><span className="cw-eyebrow">Current decision</span><h2>{labelize(selectedCluster?.blocker_type || blocker)}</h2><p>{selectedCluster?.count > 1 ? `${selectedCluster.count} cases share this root cause. Resolve the pattern once where governance permits, then re-evaluate the affected cases.` : selected.detail}</p></div>
                <div className="cw-focus-metrics"><div><span>Affected</span><strong>{selectedCluster?.count || 1} case{(selectedCluster?.count || 1) === 1 ? '' : 's'}</strong></div><div><span>Notional</span><strong>{money(affectedNotional)}</strong></div><div><span>State</span><StatePill value={workflowState} /></div></div>
              </section>

              {clusterCases.length > 1 && <section className="cw-case-strip"><div><span>Cases in this pattern</span><strong>Select a case only when you need the underlying record.</strong></div><div className="cw-case-chips">{clusterCases.map(item => <button key={item.id} className={item.id === selected.id ? 'selected' : ''} onClick={() => setSelectedId(item.id)}>{item.subject || item.title}</button>)}</div></section>}

              <div className="cw-guided-flow">
                <Step number="1" eyebrow="Understand" title="What happened?">
                  <p className="cw-lead">{selected.detail || selected.title}</p>
                  <div className="cw-inline-meta"><span>{selected.subject || selected.id}</span><span>{labelize(selected.kind)}</span><span>{money(selected.notional)}</span></div>
                </Step>

                <Step number="2" eyebrow="Diagnose" title="Why is it blocked?">
                  <div className="cw-blocker"><StatePill value={blocker} /><p>{humanWhy(blocker, workflowState)}</p></div>
                  <div className="cw-facts"><div><span>Authority</span><strong>{blocker === 'authority_conflict' ? 'Precedence unresolved' : 'Governed boundary intact'}</strong></div><div><span>Evidence</span><strong>{Object.keys(packet).length ? 'Packet available' : blocker.includes('evidence') ? 'Exception requires review' : 'No linked market packet'}</strong></div><div><span>Resolution</span><strong>{resolution.outcome || report?.verdict?.key || 'HOLD / REVIEW'}</strong></div></div>
                </Step>

                <Step number="3" eyebrow="Arbiter intelligence" title="What Arbiter found" action={<button className="cw-text-button" onClick={() => setAskOpen(v => !v)}>{askOpen ? 'Hide' : 'Ask Arbiter'}</button>}>
                  <p className="cw-lead">{selectedCluster?.count > 1 ? `This is a repeated ${labelize(blocker).toLowerCase()} pattern across ${selectedCluster.count} cases. Treat the shared root cause as the primary unit of work rather than re-investigating every case independently.` : `Arbiter classified this as ${labelize(blocker).toLowerCase()} and kept it out of the ready queue because the governed prerequisite is not yet satisfied.`}</p>
                  {askOpen && <div className="cw-ask"><div className="cw-ask-head"><strong>Context prepared</strong><span>Advisory only</span></div><p>Selected case, blocker, workflow state, affected cluster, current evidence posture, and recommended action are in scope. The model-provider hook for work-queue records is the next backend connection; until then this panel shows deterministic governed context only.</p><div className="cw-question-chips"><button>Why does this need a human?</button><button>What would clear this?</button><button>Which fact controls?</button><button>Have we seen this pattern before?</button></div></div>}
                </Step>

                <Step number="4" eyebrow="Act" title="What should you do?">
                  <div className="cw-primary-action"><div><span>Recommended next action</span><h4>{action.label}</h4><p>{selected.recommended_action || action.detail}</p></div><button onClick={() => setStatus('in_progress')}>{status === 'in_progress' ? 'In progress' : 'Start action'}</button></div>
                  <details className="cw-handoff"><summary>Ownership & handoff</summary><div className="cw-edit-grid"><label><span>Status</span><select value={status} onChange={e => setStatus(e.target.value)}><option value="open">Open</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option></select></label><label><span>Owner</span><input value={owner} onChange={e => setOwner(e.target.value)} placeholder="Operator or team" /></label><label className="wide"><span>Handoff note</span><textarea value={note} onChange={e => setNote(e.target.value)} placeholder="What changed, what remains, and what the next reviewer needs to know." /></label><div className="wide cw-action-row"><button className="primary" onClick={saveWorkState} disabled={saving}>{saving ? 'Saving…' : 'Save operator state'}</button><span>Workflow state only — never contract terms or resolution outcomes.</span></div></div></details>
                </Step>

                <Step number="5" eyebrow="Progress" title="What happens next?">
                  <div className="cw-progress"><div className="done"><b>1</b><span>Exception identified</span></div><div className={workflowState === 'INVESTIGATING' ? 'current' : 'done'}><b>2</b><span>Root cause investigated</span></div><div className={workflowState === 'WAITING' ? 'current' : workflowState === 'READY_FOR_REVIEW' ? 'done' : ''}><b>3</b><span>{workflowState === 'WAITING' ? 'Dependency arrives' : 'Governed checks satisfied'}</span></div><div className={workflowState === 'READY_FOR_REVIEW' ? 'current' : ''}><b>4</b><span>Human review</span></div><div><b>5</b><span>Resolution + audit</span></div></div>
                </Step>
              </div>
            </>}
          </main>
        </div>
      </div>
    </div>}
  </>
}
