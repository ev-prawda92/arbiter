import React, { useEffect, useMemo, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { ConsoleMetric, ConsolePageHeader, ConsoleRail } from './ConsoleShell'
import './console.css'

const VIEW_META = {
  overview: ['Executive overview', 'See portfolio posture, exposed notional, audit integrity, and the exceptions that need attention.'],
  work: ['Resolution operations', 'Follow each decision from contract terms to authority, evidence, resolution, human review, and audit.'],
  cases: ['Case registry', 'Review saved contract analyses and reusable templates without leaving the operating console.'],
  resolution: ['Resolution docket', 'Inspect contracts, governed resolution state, and the rationale behind each decision.'],
  portfolio: ['Portfolio intelligence', 'See where resolution risk and held notional concentrate across the portfolio.'],
  benchmark: ['Benchmark assurance', 'Separate engineering integrity from reportable benchmark quality and real-world evidence coverage.'],
  controls: ['Controls & authorities', 'Inspect resolution infrastructure, governed authorities, developer posture, and recent audit activity.'],
  validation: ['Validation lab', 'Track deployment, resilience, external assurance, shadow-pilot, and reference-exchange readiness.'],
  policy: ['Policy governance', 'Inspect the active policy and pending governance drafts that shape automated resolution.'],
}

function money(n) {
  if (n === 0) return '$0'
  if (!n) return '—'
  return `$${(Number(n) / 1e6).toFixed(Number(n) >= 1e7 ? 0 : 1)}M`
}

function labelize(value) {
  return String(value || '—').replaceAll('_', ' ').replace(/\b\w/g, m => m.toUpperCase())
}

function normalizeVerdict(item) {
  const raw = String(item?.verdict?.key || item?.verdict || item?.outcome || item?.resolution || '').toUpperCase()
  if (['YES', 'NO', 'HOLD', 'BLOCK', 'REVIEW', 'READY'].includes(raw)) return raw
  if (item?.status === 'resolved') return 'RESOLVED'
  if (item?.severity === 'critical') return 'HOLD'
  return 'REVIEW'
}

function statusTone(value) {
  const v = String(value || '').toUpperCase()
  if (['YES', 'READY', 'RESOLVED', 'SUFFICIENT', 'VERIFIED', 'PASS', 'HEALTHY', 'CLEAN'].includes(v)) return 'good'
  if (['NO', 'BLOCK', 'CRITICAL', 'FAIL', 'FAILED'].includes(v)) return 'bad'
  if (['HOLD', 'REVIEW', 'HIGH', 'INSUFFICIENT', 'WARNING', 'CHECK', 'MONITORED'].includes(v)) return 'warn'
  return 'neutral'
}

async function getJson(path) {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path} returned ${r.status}`)
  return r.json()
}

function ConsoleApp() {
  const [view, setView] = useState('work')
  const [data, setData] = useState({})
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [advisorOpen, setAdvisorOpen] = useState(false)

  const loadView = async (target = view, force = false) => {
    if (!force && data[target]) return
    setLoading(true)
    setError('')
    try {
      let next
      if (target === 'work') {
        const [queue, overview] = await Promise.all([getJson('/api/work-queue'), getJson('/api/overview')])
        next = { queue, overview }
        const firstActive = (queue.items || []).find(item => item.status !== 'resolved')
        if (!selectedId && firstActive) setSelectedId(firstActive.id)
      } else if (target === 'overview') {
        next = await getJson('/api/overview')
      } else if (target === 'cases') {
        const [cases, templates] = await Promise.all([getJson('/api/cases'), getJson('/api/templates')])
        next = { cases: cases.cases || [], templates: templates.templates || [] }
      } else if (target === 'resolution') {
        next = await getJson('/api/markets')
      } else if (target === 'portfolio') {
        const [portfolio, executive] = await Promise.all([getJson('/api/portfolio'), getJson('/api/executive')])
        next = { portfolio, executive }
      } else if (target === 'benchmark') {
        const [development, real] = await Promise.all([getJson('/api/benchmark'), getJson('/api/real-benchmark')])
        next = { development, real }
      } else if (target === 'controls') {
        const [infrastructure, authorities, audit, developer] = await Promise.all([
          getJson('/api/infrastructure'), getJson('/api/authorities'), getJson('/api/audit?limit=20'), getJson('/api/developer')
        ])
        next = { infrastructure, authorities: authorities.authorities || [], audit, developer }
      } else if (target === 'validation') {
        const [deployment, resilience, assurance, shadow, exchange] = await Promise.all([
          getJson('/api/deployment/posture'), getJson('/api/resilience-lab/posture'), getJson('/api/external-assurance/posture'),
          getJson('/api/shadow-pilots/posture'), getJson('/api/reference-exchange')
        ])
        next = { deployment, resilience, assurance, shadow, exchange }
      } else if (target === 'policy') {
        const [policy, drafts] = await Promise.all([getJson('/api/policy'), getJson('/api/policy/drafts')])
        next = { policy, drafts: drafts.drafts || [] }
      }
      setData(prev => ({ ...prev, [target]: next }))
    } catch (e) {
      console.error(e)
      setError(e.message || 'Unable to load console data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadView('work') }, [])
  useEffect(() => { loadView(view) }, [view])

  const meta = VIEW_META[view] || VIEW_META.work
  const advisor = data.work?.overview?.agent_brief || data.overview?.agent_brief

  return (
    <div className="console-app">
      <ConsoleRail view={view} onViewChange={setView} onRefresh={() => loadView(view, true)} />
      <main className="console-main">
        <ConsolePageHeader
          eyebrow="Governed resolution console"
          title={meta[0]}
          description={meta[1]}
          action={() => setAdvisorOpen(true)}
        />
        {error && <div className="console-error">{error}</div>}
        {loading && <div className="console-loading">Refreshing governed state…</div>}

        {view === 'overview' && <OverviewPanel data={data.overview} onOpenWork={() => setView('work')} />}
        {view === 'work' && <WorkPanel data={data.work} selectedId={selectedId} setSelectedId={setSelectedId} />}
        {view === 'cases' && <CasesPanel data={data.cases} />}
        {view === 'resolution' && <ResolutionPanel data={data.resolution} />}
        {view === 'portfolio' && <PortfolioPanel data={data.portfolio} />}
        {view === 'benchmark' && <BenchmarkPanel data={data.benchmark} />}
        {view === 'controls' && <ControlsPanel data={data.controls} />}
        {view === 'validation' && <ValidationPanel data={data.validation} />}
        {view === 'policy' && <PolicyPanel data={data.policy} />}
      </main>
      {advisorOpen && <AdvisorDrawer brief={advisor} onClose={() => setAdvisorOpen(false)} onOpenWork={() => { setAdvisorOpen(false); setView('work') }} />}
    </div>
  )
}

function OverviewPanel({ data, onOpenWork }) {
  if (!data) return <ConsoleEmpty text="Loading executive resolution posture…" />
  const h = data.health || {}
  const a = data.attention || {}
  return (
    <>
      <ConsoleBanner health={h} text="Arbiter compresses contract, evidence, control, resolution, and audit state into one operating picture." />
      <section className="console-metrics">
        <ConsoleMetric value={String(h.posture || '—').toUpperCase()} label="Portfolio posture" />
        <ConsoleMetric value={money(h.resolution_risk_notional)} label="Resolution-risk notional" tone="warn" />
        <ConsoleMetric value={money(h.held_notional)} label="Held before payout" tone="bad" />
        <ConsoleMetric value={a.active || 0} label="Active operator items" />
        <ConsoleMetric value={h.audit_chain_ok === true ? 'VERIFIED' : 'CHECK'} label="Audit integrity" />
      </section>
      <div className="console-two-col">
        <ConsoleCard title="Highest-risk contracts" kicker="Priority">
          <div className="console-list">
            {(data.top_risks || []).map(r => <div className="console-list-row" key={r.ticker}><div><strong>{r.title}</strong><span>{r.ticker} · risk {r.composite}</span></div><b>{money(r.open_interest)}</b></div>)}
            {!data.top_risks?.length && <ConsoleEmpty text="No elevated contracts surfaced." />}
          </div>
        </ConsoleCard>
        <ConsoleCard title="What needs attention" kicker="Operator load">
          <div className="console-brief-stack">
            {(data.agent_brief?.brief || []).map((line, i) => <p key={i}>{line}</p>)}
            <button className="console-dark-button" onClick={onOpenWork}>Open work queue →</button>
          </div>
        </ConsoleCard>
      </div>
    </>
  )
}

function WorkPanel({ data, selectedId, setSelectedId }) {
  if (!data) return <ConsoleEmpty text="Loading resolution operations…" />
  const { queue, overview } = data
  const items = queue?.items || []
  const active = items.filter(i => i.status !== 'resolved')
  const selected = items.find(i => i.id === selectedId) || active[0] || items[0]
  const summary = queue?.summary || {}
  const health = overview?.health || {}
  return (
    <>
      <ConsoleBanner health={health} text="Arbiter surfaces the cases that need judgment and keeps deterministic logic as the decision boundary." />
      <section className="console-metrics">
        <ConsoleMetric value={summary.active ?? active.length} label="Active cases" />
        <ConsoleMetric value={summary.critical ?? 0} label="Critical" tone="bad" />
        <ConsoleMetric value={summary.high ?? 0} label="High priority" tone="warn" />
        <ConsoleMetric value={money(summary.notional)} label="Notional represented" />
        <ConsoleMetric value={String(health.posture || '—').toUpperCase()} label="Portfolio posture" />
      </section>
      <div className="console-workspace">
        <section className="console-table-card">
          <SectionHead kicker="Needs attention" title="Decision queue" meta={`${active.length} open`} />
          <div className="console-table-scroll"><table className="console-table"><thead><tr><th>Case</th><th>State</th><th>Owner</th><th>Resolution basis</th><th>Notional</th></tr></thead><tbody>
            {active.map(item => {
              const verdict = normalizeVerdict(item)
              return <tr key={item.id} className={selected?.id === item.id ? 'selected' : ''} onClick={() => setSelectedId(item.id)}>
                <td><strong>{item.title}</strong><span>{labelize(item.kind || 'resolution')}</span></td>
                <td><Pill value={verdict} /></td><td>{item.owner_role || 'Resolution Ops'}</td>
                <td className="basis">{item.detail || item.recommended_action || 'Review governed case state.'}</td>
                <td>{item.notional ? money(item.notional) : '—'}</td>
              </tr>
            })}
            {!active.length && <tr><td colSpan="5"><ConsoleEmpty text="No active exceptions. Arbiter will surface governed work here when state changes." /></td></tr>}
          </tbody></table></div>
        </section>
        <ResolutionInspector selected={selected} />
      </div>
    </>
  )
}

function ResolutionInspector({ selected }) {
  return <aside className="console-inspector"><SectionHead kicker="Selected case" title="Resolution trace" />
    {selected ? <>
      <div className="console-inspector-title"><Pill value={normalizeVerdict(selected)} /><h3>{selected.title}</h3><p>{selected.detail}</p></div>
      <div className="console-trace">
        <TraceStep label="Contract" value={labelize(selected.kind || 'exception')} state="Captured" />
        <TraceStep label="Authority" value="Governed source precedence" state={selected.severity === 'critical' ? 'Review' : 'Checked'} />
        <TraceStep label="Evidence" value="Frozen evidence state" state={normalizeVerdict(selected) === 'HOLD' ? 'Insufficient' : 'Review'} />
        <TraceStep label="Resolution" value={selected.recommended_action || 'Operator review required'} state={normalizeVerdict(selected)} />
      </div>
      <div className="console-next-action"><span>Recommended next action</span><strong>{selected.recommended_action || 'Inspect the governed case record.'}</strong><button onClick={() => window.location.href = '/'}>Open full Arbiter case →</button></div>
    </> : <ConsoleEmpty text="Select a case to inspect its decision trace." />}
  </aside>
}

function CasesPanel({ data }) {
  if (!data) return <ConsoleEmpty text="Loading cases…" />
  return <div className="console-two-col"><ConsoleCard kicker="Saved analyses" title={`Cases · ${data.cases.length}`}>
    <div className="console-list">{data.cases.slice(0, 12).map(c => <div className="console-list-row" key={c.case_id}><div><strong>{c.title || c.case_id}</strong><span>{c.case_id} · {labelize(c.status || c.latest_run?.compilation?.status)}</span></div><Pill value={c.latest_run?.compilation?.status || c.status || 'REVIEW'} /></div>)}{!data.cases.length && <ConsoleEmpty text="No saved cases yet." />}</div>
  </ConsoleCard><ConsoleCard kicker="Reusable drafting" title={`Templates · ${data.templates.length}`}>
    <div className="console-list">{data.templates.slice(0, 12).map(t => <div className="console-list-row" key={t.template_id || t.id}><div><strong>{t.name || t.title}</strong><span>{t.template_id || t.id}</span></div></div>)}{!data.templates.length && <ConsoleEmpty text="No templates saved yet." />}</div>
  </ConsoleCard></div>
}

function ResolutionPanel({ data }) {
  const markets = data?.markets || []
  if (!data) return <ConsoleEmpty text="Loading resolution docket…" />
  const counts = markets.reduce((acc, m) => { const k = normalizeVerdict(m); acc[k] = (acc[k] || 0) + 1; return acc }, {})
  const total = markets.reduce((n,m) => n + (m.open_interest || 0), 0)
  return <><section className="console-metrics"><ConsoleMetric value={markets.length} label="Contracts" /><ConsoleMetric value={money(total)} label="Notional" /><ConsoleMetric value={counts.YES || counts.READY || 0} label="Ready / yes" /><ConsoleMetric value={counts.HOLD || 0} label="Hold" tone="warn" /><ConsoleMetric value={counts.REVIEW || counts.BLOCK || 0} label="Review / block" tone="bad" /></section>
    <ConsoleCard kicker="Governed docket" title="Contracts"><div className="console-table-scroll"><table className="console-table resolution-table"><thead><tr><th>Contract</th><th>State</th><th>Category</th><th>Open interest</th></tr></thead><tbody>{markets.map(m => <tr key={m.ticker}><td><strong>{m.title}</strong><span>{m.ticker}</span></td><td><Pill value={normalizeVerdict(m)} /></td><td>{m.category || '—'}</td><td>{money(m.open_interest)}</td></tr>)}</tbody></table></div></ConsoleCard></>
}

function PortfolioPanel({ data }) {
  if (!data) return <ConsoleEmpty text="Loading portfolio intelligence…" />
  const p = data.portfolio || {}
  const e = data.executive || {}
  return <><section className="console-metrics"><ConsoleMetric value={money(p.resolution_risk_notional || e.resolution_risk_notional)} label="Resolution-risk notional" tone="warn" /><ConsoleMetric value={money(p.held_notional || e.held_notional)} label="Held notional" tone="bad" /><ConsoleMetric value={p.coverage_gap_count ?? e.coverage_gap_count ?? '—'} label="Coverage gaps" /><ConsoleMetric value={labelize(p.primary_risk_driver || e.primary_risk_driver)} label="Primary risk driver" /><ConsoleMetric value={p.audit_chain_ok === true || e.audit_chain_ok === true ? 'VERIFIED' : 'CHECK'} label="Audit integrity" /></section>
    <div className="console-two-col"><JsonSummary title="Portfolio posture" value={p} /><JsonSummary title="Executive posture" value={e} /></div></>
}

function BenchmarkPanel({ data }) {
  if (!data) return <ConsoleEmpty text="Loading benchmark assurance…" />
  const real = data.real || {}; const dev = data.development || {}
  const realSummary = real.reportability || real.summary || real
  return <><section className="console-banner benchmark-banner"><div><strong>Integrity ≠ validity.</strong><span>A hash-valid frozen dataset can still be non-reportable if curation, evidence, or labels are insufficient.</span></div><Pill value={realSummary.reportable === true ? 'PASS' : 'REVIEW'} /></section>
    <div className="console-two-col"><JsonSummary title="Real-world holdout" value={real} /><JsonSummary title="Development benchmark" value={dev} /></div></>
}

function ControlsPanel({ data }) {
  if (!data) return <ConsoleEmpty text="Loading controls and authorities…" />
  return <><div className="console-two-col"><JsonSummary title="Infrastructure posture" value={data.infrastructure} /><JsonSummary title="Developer surface" value={data.developer} /></div>
    <ConsoleCard kicker="Governed sources" title={`Authorities · ${data.authorities.length}`}><div className="console-list">{data.authorities.map(a => <div className="console-list-row" key={a.authority_id || a.id}><div><strong>{a.name || a.authority_id || a.id}</strong><span>{a.authority_id || a.id} · {labelize(a.status || a.kind || 'authority')}</span></div><Pill value={a.status || 'READY'} /></div>)}</div></ConsoleCard>
    <JsonSummary title="Recent audit activity" value={data.audit} />
  </>
}

function ValidationPanel({ data }) {
  if (!data) return <ConsoleEmpty text="Loading validation program…" />
  const cards = [['Deployment', data.deployment], ['Resilience', data.resilience], ['External assurance', data.assurance], ['Shadow pilots', data.shadow], ['Reference exchange', data.exchange]]
  return <div className="console-validation-grid">{cards.map(([title, value]) => <JsonSummary key={title} title={title} value={value} />)}</div>
}

function PolicyPanel({ data }) {
  if (!data) return <ConsoleEmpty text="Loading policy governance…" />
  return <div className="console-two-col"><JsonSummary title={`Active policy · ${data.policy?.version || data.policy?.policy_version || 'current'}`} value={data.policy} /><ConsoleCard kicker="Governance workflow" title={`Drafts · ${data.drafts.length}`}><div className="console-list">{data.drafts.map(d => <div className="console-list-row" key={d.draft_id || d.id}><div><strong>{d.title || d.draft_id || d.id}</strong><span>{labelize(d.status || 'draft')}</span></div><Pill value={d.status || 'REVIEW'} /></div>)}{!data.drafts.length && <ConsoleEmpty text="No pending policy drafts." />}</div></ConsoleCard></div>
}

function AdvisorDrawer({ brief, onClose, onOpenWork }) {
  return <div className="console-drawer-backdrop" onClick={onClose}><aside className="console-drawer" onClick={e => e.stopPropagation()}><div className="console-drawer-head"><div><span>Advisory only</span><h2>Ask Arbiter</h2></div><button onClick={onClose}>×</button></div>
    <div className="console-advisor-intro"><strong>{brief?.headline || 'Resolution operations briefing'}</strong><p>{brief?.boundary || 'Advisory summaries never override governed resolution logic.'}</p></div>
    <h3>Current briefing</h3>{(brief?.brief || ['Open the work queue to inspect current governed exceptions.']).map((x,i) => <p className="console-advisor-line" key={i}>{x}</p>)}
    <h3>Top actions</h3>{(brief?.top_actions || []).map(a => <div className="console-advisor-action" key={a.id}><Pill value={a.severity || 'REVIEW'} /><strong>{a.title}</strong><p>{a.recommended_action}</p></div>)}
    <button className="console-dark-button" onClick={onOpenWork}>Open resolution operations →</button>
  </aside></div>
}

function ConsoleBanner({ health, text }) {
  return <section className="console-banner"><div><strong>Resolve from evidence, not intuition.</strong><span>{text}</span></div><span className={`console-state ${health?.audit_chain_ok === true ? 'good' : 'warn'}`}>{health?.audit_chain_ok === true ? 'Audit verified' : 'Audit check'}</span></section>
}

function ConsoleCard({ title, kicker, children }) { return <section className="console-card"><SectionHead title={title} kicker={kicker} /><div className="console-card-body">{children}</div></section> }
function SectionHead({ kicker, title, meta }) { return <div className="console-section-head"><div><span className="console-kicker">{kicker}</span><h2>{title}</h2></div>{meta && <span>{meta}</span>}</div> }
function Pill({ value }) { return <span className={`console-pill ${statusTone(value)}`}>{labelize(value)}</span> }
function ConsoleEmpty({ text }) { return <div className="console-empty">{text}</div> }

function TraceStep({ label, value, state }) {
  return <div className="console-trace-step"><div className="console-trace-dot" /><div><span>{label}</span><strong>{value}</strong></div><Pill value={state} /></div>
}

function JsonSummary({ title, value }) {
  const rows = Object.entries(value || {}).filter(([,v]) => ['string','number','boolean'].includes(typeof v)).slice(0, 8)
  return <ConsoleCard kicker="System posture" title={title}><div className="console-summary-grid">{rows.map(([k,v]) => <div key={k}><span>{labelize(k)}</span><strong>{typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v)}</strong></div>)}{!rows.length && <ConsoleEmpty text="No scalar summary fields available." />}</div><details className="console-json"><summary>View raw record</summary><pre>{JSON.stringify(value, null, 2)}</pre></details></ConsoleCard>
}

ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><ConsoleApp /></React.StrictMode>)
