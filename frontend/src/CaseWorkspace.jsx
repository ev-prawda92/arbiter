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
    : raw.includes('hold') || raw.includes('investigat') || raw.includes('wait') || raw.includes('review')
      ? 'warn'
      : 'neutral'
  return <span className={`cw-pill ${tone}`}>{labelize(value)}</span>
}

function Field({ label, children }) {
  return <div className="cw-field"><span>{label}</span><strong>{children ?? '—'}</strong></div>
}

function Section({ title, kicker, children }) {
  return <section className="cw-section"><div className="cw-section-head"><div><span>{kicker}</span><h3>{title}</h3></div></div>{children}</section>
}

export default function CaseWorkspace() {
  const [open, setOpen] = useState(false)
  const [queue, setQueue] = useState(null)
  const [overview, setOverview] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [owner, setOwner] = useState('')
  const [note, setNote] = useState('')
  const [status, setStatus] = useState('open')
  const [saving, setSaving] = useState(false)

  const active = useMemo(() => (queue?.items || []).filter(item => item.status !== 'resolved'), [queue])
  const selected = useMemo(() => active.find(item => item.id === selectedId) || active[0] || null, [active, selectedId])
  const operations = overview?.agent_brief?.operations_intelligence
  const opsCase = useMemo(() => {
    if (!selected || !operations) return null
    return [
      ...(operations.ready_cases || []),
      ...(operations.investigating_cases || []),
      ...(operations.waiting_cases || []),
    ].find(item => item.id === selected.id) || null
  }, [operations, selected])

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [nextQueue, nextOverview] = await Promise.all([
        getJson('/api/work-queue'),
        getJson('/api/overview'),
      ])
      setQueue(nextQueue)
      setOverview(nextOverview)
      const first = (nextQueue.items || []).find(item => item.status !== 'resolved')
      if (!selectedId && first) setSelectedId(first.id)
    } catch (e) {
      setError(e.message || 'Unable to load case workspace')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open && !queue) load()
  }, [open])

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
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, owner, note, actor: 'operator:resolution-ops' }),
      })
      setQueue(result.queue)
    } catch (e) {
      setError(e.message || 'Unable to update case state')
    } finally {
      setSaving(false)
    }
  }

  const workflowState = opsCase
    ? (operations?.ready_cases || []).some(x => x.id === selected?.id)
      ? 'READY_FOR_REVIEW'
      : (operations?.waiting_cases || []).some(x => x.id === selected?.id)
        ? 'WAITING'
        : 'INVESTIGATING'
    : selected?.status || 'open'

  const report = detail?.report || {}
  const resolution = detail?.resolution || {}
  const packet = detail?.evidence_packet || {}

  return <>
    <button className="cw-launch" onClick={() => setOpen(true)} aria-label="Open case workspace">
      <span>Case workspace</span><b>{active.length || ''}</b>
    </button>
    {open && <div className="cw-backdrop" onMouseDown={e => e.target === e.currentTarget && setOpen(false)}>
      <div className="cw-shell">
        <header className="cw-header">
          <div><span>Arbiter v0.32</span><h2>Operator case workspace</h2><p>Understand, act, and hand off a governed resolution case without leaving the queue.</p></div>
          <div className="cw-header-actions"><button onClick={load} disabled={loading}>Refresh</button><button className="cw-close" onClick={() => setOpen(false)}>×</button></div>
        </header>

        {error && <div className="cw-error">{error}</div>}
        <div className="cw-layout">
          <aside className="cw-queue">
            <div className="cw-queue-head"><span>Active queue</span><strong>{active.length}</strong></div>
            {loading && !queue && <p className="cw-muted">Loading governed work…</p>}
            {active.map(item => <button key={item.id} className={item.id === selected?.id ? 'selected' : ''} onClick={() => setSelectedId(item.id)}>
              <div><strong>{item.title}</strong><span>{labelize(item.kind)}</span></div>
              <small>{money(item.notional)}</small>
            </button>)}
          </aside>

          <main className="cw-main">
            {!selected ? <div className="cw-empty">No active cases require operator attention.</div> : <>
              <section className="cw-hero">
                <div><div className="cw-eyebrow">{selected.subject || selected.id}</div><h2>{selected.title}</h2><p>{selected.detail}</p></div>
                <div className="cw-hero-state"><StatePill value={workflowState} /><strong>{money(selected.notional)}</strong><span>{selected.owner_role || 'Resolution Ops'}</span></div>
              </section>

              <div className="cw-grid">
                <Section kicker="Terms" title="Contract">
                  <div className="cw-fields"><Field label="Subject">{selected.subject}</Field><Field label="Work type">{labelize(selected.kind)}</Field><Field label="Market title">{report.title || selected.detail}</Field><Field label="Category">{report.category || '—'}</Field></div>
                </Section>

                <Section kicker="Control" title="Authority">
                  <div className="cw-fields"><Field label="State">{selected.severity === 'critical' ? 'Review required' : 'Governed'}</Field><Field label="Owner role">{selected.owner_role || 'Resolution Ops'}</Field><Field label="Primary risk">{labelize(report?.primary_risk_driver || selected.kind)}</Field><Field label="Boundary">Deterministic core remains binding</Field></div>
                </Section>

                <Section kicker="Record" title="Evidence">
                  <div className="cw-fields"><Field label="Packet">{Object.keys(packet).length ? 'Available' : 'No market packet loaded'}</Field><Field label="Resolution outcome">{resolution.outcome || report?.verdict?.key || 'Review'}</Field><Field label="Evidence state">{workflowState === 'WAITING' ? 'External dependency' : workflowState === 'INVESTIGATING' ? 'Needs investigation' : 'Reviewable'}</Field><Field label="Audit posture">Traceable</Field></div>
                </Section>

                <Section kicker="Operator" title="Next action">
                  <p className="cw-next-action">{selected.recommended_action || 'Inspect the governed case record.'}</p>
                  <div className="cw-edit-grid">
                    <label><span>Status</span><select value={status} onChange={e => setStatus(e.target.value)}><option value="open">Open</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option></select></label>
                    <label><span>Owner</span><input value={owner} onChange={e => setOwner(e.target.value)} placeholder="Operator or team" /></label>
                    <label className="wide"><span>Handoff note</span><textarea value={note} onChange={e => setNote(e.target.value)} placeholder="What changed, what remains, and what the next reviewer needs to know." /></label>
                  </div>
                  <div className="cw-action-row"><button className="primary" onClick={saveWorkState} disabled={saving}>{saving ? 'Saving…' : 'Save operator state'}</button><span>Changes affect ownership/workflow only — never contract terms or outcomes.</span></div>
                </Section>
              </div>

              <Section kicker="Trace" title="Resolution path">
                <div className="cw-trace">
                  {['Contract captured', 'Authority checked', 'Evidence assessed', workflowState === 'READY_FOR_REVIEW' ? 'Ready for human review' : workflowState === 'WAITING' ? 'Waiting on dependency' : 'Investigation required', 'Audit retained'].map((step, index) => <div key={step}><b>{index + 1}</b><span>{step}</span></div>)}
                </div>
              </Section>
            </>}
          </main>
        </div>
      </div>
    </div>}
  </>
}
