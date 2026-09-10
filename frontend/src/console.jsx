import React, { useEffect, useMemo, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { ConsoleMetric, ConsolePageHeader, ConsoleRail } from './ConsoleShell'
import './console.css'

function money(n) {
  if (!n) return '—'
  return `$${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`
}

function normalizeVerdict(item) {
  const raw = String(item.verdict || item.outcome || item.resolution || '').toUpperCase()
  if (['YES', 'NO', 'HOLD', 'BLOCK', 'REVIEW', 'READY'].includes(raw)) return raw
  if (item.status === 'resolved') return 'RESOLVED'
  if (item.severity === 'critical') return 'HOLD'
  return 'REVIEW'
}

function statusTone(value) {
  const v = String(value || '').toUpperCase()
  if (['YES', 'READY', 'RESOLVED', 'SUFFICIENT', 'VERIFIED'].includes(v)) return 'good'
  if (['NO', 'BLOCK', 'CRITICAL'].includes(v)) return 'bad'
  if (['HOLD', 'REVIEW', 'HIGH', 'INSUFFICIENT'].includes(v)) return 'warn'
  return 'neutral'
}

function ConsoleApp() {
  const [view, setView] = useState('work')
  const [queue, setQueue] = useState(null)
  const [overview, setOverview] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [queueR, overviewR] = await Promise.all([
        fetch('/api/work-queue'),
        fetch('/api/overview'),
      ])
      if (!queueR.ok || !overviewR.ok) throw new Error('Arbiter API is unavailable')
      const [queueData, overviewData] = await Promise.all([queueR.json(), overviewR.json()])
      setQueue(queueData)
      setOverview(overviewData)
      const firstActive = (queueData.items || []).find(item => item.status !== 'resolved')
      if (!selectedId && firstActive) setSelectedId(firstActive.id)
    } catch (e) {
      console.error(e)
      setError(e.message || 'Unable to load console data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const items = queue?.items || []
  const active = useMemo(() => items.filter(i => i.status !== 'resolved'), [items])
  const selected = items.find(i => i.id === selectedId) || active[0] || items[0]
  const summary = queue?.summary || {}
  const health = overview?.health || {}

  const pageTitle = view === 'work' ? 'Resolution operations' : view[0].toUpperCase() + view.slice(1)

  return (
    <div className="console-app">
      <ConsoleRail view={view} onViewChange={setView} onRefresh={load} />
      <main className="console-main">
        <ConsolePageHeader
          eyebrow="Governed resolution console"
          title={pageTitle}
          description="Follow each decision from contract terms to authority, evidence, resolution, human review, and audit — without reconstructing the system yourself."
          action={() => window.alert('Ask Arbiter is a UI placeholder for the advisory agent surface.')}
        />

        {error && <div className="console-error">{error}</div>}

        <section className="console-banner">
          <div>
            <strong>Resolve from evidence, not intuition.</strong>
            <span>Arbiter surfaces the contracts that need judgment and keeps deterministic logic as the decision boundary.</span>
          </div>
          <span className={`console-state ${health.audit_chain_ok === true ? 'good' : 'warn'}`}>
            {health.audit_chain_ok === true ? 'Audit verified' : 'Audit check'}
          </span>
        </section>

        <section className="console-metrics">
          <ConsoleMetric value={summary.active ?? active.length} label="Active cases" />
          <ConsoleMetric value={summary.critical ?? 0} label="Critical" tone="bad" />
          <ConsoleMetric value={summary.high ?? 0} label="High priority" tone="warn" />
          <ConsoleMetric value={money(summary.notional)} label="Notional represented" />
          <ConsoleMetric value={String(health.posture || '—').toUpperCase()} label="Portfolio posture" />
        </section>

        {view !== 'work' ? (
          <section className="console-placeholder">
            <span>Console shell preview</span>
            <h2>{pageTitle}</h2>
            <p>This branch establishes the new operating shell first. Existing Arbiter modules remain intact; subsequent passes can migrate each surface into this navigation and interaction model.</p>
            <button onClick={() => setView('work')}>Open Work Queue</button>
          </section>
        ) : (
          <div className="console-workspace">
            <section className="console-table-card">
              <div className="console-section-head">
                <div>
                  <span className="console-kicker">Needs attention</span>
                  <h2>Decision queue</h2>
                </div>
                <span>{active.length} open</span>
              </div>

              <div className="console-table-scroll">
                <table className="console-table">
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>State</th>
                      <th>Owner</th>
                      <th>Resolution basis</th>
                      <th>Notional</th>
                    </tr>
                  </thead>
                  <tbody>
                    {active.map(item => {
                      const verdict = normalizeVerdict(item)
                      return (
                        <tr key={item.id} className={selected?.id === item.id ? 'selected' : ''} onClick={() => setSelectedId(item.id)}>
                          <td>
                            <strong>{item.title}</strong>
                            <span>{String(item.kind || 'resolution').replaceAll('_', ' ')}</span>
                          </td>
                          <td><span className={`console-pill ${statusTone(verdict)}`}>{verdict}</span></td>
                          <td>{item.owner_role || 'Resolution Ops'}</td>
                          <td className="basis">{item.detail || item.recommended_action || 'Review governed case state.'}</td>
                          <td>{item.notional ? money(item.notional) : '—'}</td>
                        </tr>
                      )
                    })}
                    {!active.length && !loading && (
                      <tr><td colSpan="5" className="console-empty">No active exceptions. Arbiter will surface governed work here when state changes.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <aside className="console-inspector">
              <div className="console-section-head">
                <div>
                  <span className="console-kicker">Selected case</span>
                  <h2>Resolution trace</h2>
                </div>
              </div>
              {selected ? (
                <>
                  <div className="console-inspector-title">
                    <span className={`console-pill ${statusTone(normalizeVerdict(selected))}`}>{normalizeVerdict(selected)}</span>
                    <h3>{selected.title}</h3>
                    <p>{selected.detail}</p>
                  </div>
                  <div className="console-trace">
                    <TraceStep label="Contract" value={String(selected.kind || 'exception').replaceAll('_', ' ')} state="Captured" />
                    <TraceStep label="Authority" value="Governed source precedence" state={selected.severity === 'critical' ? 'Review' : 'Checked'} />
                    <TraceStep label="Evidence" value="Frozen evidence state" state={normalizeVerdict(selected) === 'HOLD' ? 'Insufficient' : 'Review'} />
                    <TraceStep label="Resolution" value={selected.recommended_action || 'Operator review required'} state={normalizeVerdict(selected)} />
                  </div>
                  <div className="console-next-action">
                    <span>Recommended next action</span>
                    <strong>{selected.recommended_action || 'Inspect the governed case record.'}</strong>
                    <button onClick={() => window.location.href = '/'}>Open full Arbiter case →</button>
                  </div>
                </>
              ) : <p className="console-empty">Select a case to inspect its decision trace.</p>}
            </aside>
          </div>
        )}
      </main>
    </div>
  )
}

function TraceStep({ label, value, state }) {
  return (
    <div className="console-trace-step">
      <div className="console-trace-dot" />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <span className={`console-pill ${statusTone(state)}`}>{state}</span>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConsoleApp />
  </React.StrictMode>
)
