import React, { useState, useEffect } from 'react'
import './styles.css'

import ReactDOM from 'react-dom/client'

function App() {
  const [view, setView] = useState('overview') // overview, work, cases, markets, monitoring, benchmark, infrastructure, policy
  const [markets, setMarkets] = useState([])
  const [monitoring, setMonitoring] = useState(null)
  const [overview, setOverview] = useState(null)
  const [workQueue, setWorkQueue] = useState(null)
  const [policy, setPolicy] = useState(null)
  const [benchmark, setBenchmark] = useState(null)
  const [infrastructure, setInfrastructure] = useState(null)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [analyzeModal, setAnalyzeModal] = useState(false)
  const [analysisSeed, setAnalysisSeed] = useState(null)
  const [casesData, setCasesData] = useState({ cases: [], templates: [] })
  const [copilotCase, setCopilotCase] = useState(null)
  const [analyzingLive, setAnalyzingLive] = useState(false)

  useEffect(() => {
    loadMarkets()
    loadOverview()
  }, [])

  const loadMarkets = async (live = false) => {
    setLoading(true)
    try {
      const r = await fetch(`/api/markets?live=${live}`)
      const d = await r.json()
      setMarkets(d.markets || [])
      if (d.markets && d.markets.length > 0) {
        selectMarket(d.markets[0])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }



  const loadCases = async () => {
    try {
      const [casesR, templatesR] = await Promise.all([fetch('/api/cases'), fetch('/api/templates')])
      const [cases, templates] = await Promise.all([casesR.json(), templatesR.json()])
      setCasesData({ cases: cases.cases || [], templates: templates.templates || [] })
    } catch (e) { console.error(e) }
  }


  const saveCaseAsTemplate = async (caseItem) => {
    const name = window.prompt('Template name', caseItem.title.slice(0, 60))
    if (!name) return
    try {
      const r = await fetch(`/api/cases/${caseItem.case_id}/template`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, actor: 'operator:market-ops' })
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'template creation failed')
      await loadCases()
    } catch (e) { console.error(e); window.alert(e.message) }
  }

  const openNewAnalysis = (seed = null) => {
    setAnalysisSeed(seed)
    setAnalyzeModal(true)
  }

  const loadOverview = async () => {
    try {
      const r = await fetch('/api/overview')
      setOverview(await r.json())
    } catch (e) { console.error(e) }
  }

  const loadWorkQueue = async () => {
    try {
      const r = await fetch('/api/work-queue')
      setWorkQueue(await r.json())
    } catch (e) { console.error(e) }
  }

  const updateWorkItem = async (id, status) => {
    try {
      const r = await fetch(`/api/work-queue/${id}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, actor: 'operator:compliance' })
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'update failed')
      setWorkQueue(d.queue)
      await loadOverview()
    } catch (e) { console.error(e) }
  }

  const loadMonitoring = async () => {
    try {
      const [portfolioR, executiveR] = await Promise.all([fetch('/api/portfolio'), fetch('/api/executive')])
      const [portfolio, executive] = await Promise.all([portfolioR.json(), executiveR.json()])
      setMonitoring({ ...portfolio, executive })
    } catch (e) {
      console.error(e)
    }
  }

  const loadBenchmark = async () => {
    try {
      const r = await fetch('/api/benchmark')
      const d = await r.json()
      setBenchmark(d)
    } catch (e) {
      console.error(e)
    }
  }

  const loadInfrastructure = async () => {
    try {
      const [infraR, authR, auditR, devR] = await Promise.all([
        fetch('/api/infrastructure'), fetch('/api/authorities'), fetch('/api/audit?limit=25'), fetch('/api/developer')
      ])
      const [infra, authorities, audit, developer] = await Promise.all([infraR.json(), authR.json(), auditR.json(), devR.json()])
      setInfrastructure({ ...infra, authorities: authorities.authorities || [], audit, developer })
    } catch (e) {
      console.error(e)
    }
  }

  const loadPolicy = async () => {
    try {
      const [r, dr] = await Promise.all([fetch('/api/policy'), fetch('/api/policy/drafts')])
      const [d, drafts] = await Promise.all([r.json(), dr.json()])
      setPolicy({ ...d, drafts: drafts.drafts || [] })
    } catch (e) {
      console.error(e)
    }
  }

  const selectMarket = async (m) => {
    setSelected(m)
    try {
      const r = await fetch(`/api/markets/${m.ticker}`)
      const d = await r.json()
      setDetail(d)
    } catch (e) {
      console.error(e)
    }
  }

  const handleViewChange = async (v) => {
    setView(v)
    if (v === 'overview' && !overview) {
      await loadOverview()
    }
    if (v === 'work' && !workQueue) {
      await loadWorkQueue()
    }
    if (v === 'cases') {
      await loadCases()
    }
    if (v === 'monitoring' && !monitoring) {
      await loadMonitoring()
    }
    if (v === 'benchmark' && !benchmark) {
      await loadBenchmark()
    }
    if (v === 'infrastructure' && !infrastructure) {
      await loadInfrastructure()
    }
    if (v === 'policy' && !policy) {
      await loadPolicy()
    }
  }

  return (
    <div className="arbiter">
      <Rail markets={markets} view={view} onViewChange={handleViewChange} onRefresh={() => { loadMarkets(); loadOverview(); loadWorkQueue(); }} />

      {view === 'overview' && (
        <OverviewView data={overview} onWork={() => handleViewChange('work')} onResolution={() => handleViewChange('markets')} />
      )}

      {view === 'work' && (
        <WorkQueueView data={workQueue} onUpdate={updateWorkItem} />
      )}
      
      {view === 'cases' && (
        <CasesView data={casesData} onNew={() => openNewAnalysis()} onOpen={(seed) => openNewAnalysis(seed)} onTemplate={saveCaseAsTemplate} onCopilot={setCopilotCase} />
      )}

      {view === 'markets' && (
        <MarketsView
          markets={markets}
          selected={selected}
          detail={detail}
          loading={loading}
          onSelectMarket={selectMarket}
          onAnalyzeClick={() => openNewAnalysis()}
        />
      )}
      
      {view === 'monitoring' && (
        <MonitoringView data={monitoring} onViewMarkets={() => setView('markets')} />
      )}
      
      {view === 'benchmark' && (
        <BenchmarkView data={benchmark} />
      )}

      {view === 'infrastructure' && (
        <InfrastructureView data={infrastructure} />
      )}

      {view === 'policy' && (
        <PolicyView data={policy} onReload={loadPolicy} />
      )}

      {copilotCase && (
        <CopilotModal caseItem={copilotCase} onClose={() => setCopilotCase(null)} />
      )}

      {analyzeModal && (
        <AnalyzeModal
          initial={analysisSeed}
          onClose={() => { setAnalyzeModal(false); setAnalysisSeed(null) }}
          onSuccess={(result) => {
            setAnalyzeModal(false)
            setAnalysisSeed(null)
            loadCases()
            setSelected({
              ticker: result.report.ticker || 'LIVE-INPUT',
              title: result.report.title,
              category: result.report.category || 'live analysis',
              open_interest: 0,
              verdict: result.report.verdict,
              rules_primary: result.report.rules_primary || ''
            })
            setDetail({
              report: result.report,
              resolution: result.resolution,
              design: result.design,
              compilation: result.compilation
            })
            setView('markets')
          }}
        />
      )}
    </div>
  )
}

function Rail({ markets, view, onViewChange, onRefresh }) {
  return (
    <div className="rail">
      <div className="rail-in">
        <div className="brand">
          <span className="wordmark">ARBITER</span>
          <span className="sub">Resolution Control Infrastructure</span>
        </div>
        <div className="nav">
          <button className={`nav-btn ${view === 'overview' ? 'active' : ''}`} onClick={() => onViewChange('overview')}>Overview</button>
          <button className={`nav-btn ${view === 'work' ? 'active' : ''}`} onClick={() => onViewChange('work')}>Work Queue</button>
          <button className={`nav-btn ${view === 'cases' ? 'active' : ''}`} onClick={() => onViewChange('cases')}>Cases</button>
          <button
            className={`nav-btn ${view === 'markets' ? 'active' : ''}`}
            onClick={() => onViewChange('markets')}
          >
            Resolution
          </button>
          <button
            className={`nav-btn ${view === 'monitoring' ? 'active' : ''}`}
            onClick={() => onViewChange('monitoring')}
          >
            Portfolio
          </button>
          <button
            className={`nav-btn ${view === 'benchmark' ? 'active' : ''}`}
            onClick={() => onViewChange('benchmark')}
          >
            Benchmark
          </button>
          <button
            className={`nav-btn ${view === 'infrastructure' ? 'active' : ''}`}
            onClick={() => onViewChange('infrastructure')}
          >
            Controls
          </button>
          <button
            className={`nav-btn ${view === 'policy' ? 'active' : ''}`}
            onClick={() => onViewChange('policy')}
          >
            Policy
          </button>
          <button className="nav-btn refresh" onClick={onRefresh} title="Reload markets">
            ↻
          </button>
        </div>
      </div>
    </div>
  )
}

function OverviewView({ data, onWork, onResolution }) {
  if (!data) return <div className="view"><p>Loading exchange resolution health...</p></div>
  const h = data.health || {}
  const a = data.attention || {}
  const brief = data.agent_brief || {}
  const money = n => `$${((n || 0) / 1e6).toFixed(1)}M`
  return (
    <div className="view executive-overview">
      <div className="strip overview-strip">
        <p className="eyebrow">Exchange Resolution Health · Executive Overview</p>
        <h1>What needs attention, what money is exposed, and whether settlement controls are working.</h1>
        <p className="dek">A read-only view for leadership. Arbiter compresses contract, evidence, control, resolution, and audit state into one operating picture.</p>
        <div className="metrics overview-metrics">
          <div className="metric"><div className="n">{String(h.posture || '—').toUpperCase()}</div><div className="l">portfolio posture</div></div>
          <div className="metric"><div className="n">{money(h.resolution_risk_notional)}</div><div className="l">resolution-risk notional</div></div>
          <div className="metric warn"><div className="n">{money(h.held_notional)}</div><div className="l">held before payout</div></div>
          <div className="metric"><div className="n">{a.active || 0}</div><div className="l">active operator items</div></div>
          <div className="metric"><div className="n">{h.primary_risk_driver || '—'}</div><div className="l">primary risk driver</div></div>
          <div className="metric"><div className="n">{h.audit_chain_ok === true ? 'VERIFIED' : 'CHECK'}</div><div className="l">audit integrity</div></div>
        </div>
      </div>
      <div className="overview-wrap">
        <section className="agent-brief-card">
          <div className="brief-head"><div><p className="eyebrow">Resolution Operations Agent · Advisory</p><h2>{brief.headline}</h2></div><span className="agent-mode">NON-BINDING</span></div>
          <div className="brief-grid">
            <div><h3>Today</h3>{(brief.brief || []).map((x,i)=><p key={i} className="brief-line">{x}</p>)}</div>
            <div><h3>Top actions</h3>{(brief.top_actions || []).map(x=><div className="action-card" key={x.id}><span className={`severity ${x.severity}`}>{x.severity}</span><strong>{x.title}</strong><p>{x.recommended_action}</p></div>)}</div>
          </div>
          <div className="overview-actions"><button onClick={onWork}>Open operator work queue →</button><button className="secondary" onClick={onResolution}>Inspect resolution cases</button></div>
        </section>
        <section className="exec-risk-list">
          <h2 className="sect-h">Highest-risk contracts</h2>
          {(data.top_risks || []).map(r => <div className="exec-risk-row" key={r.ticker}><div><span className="mono">{r.ticker}</span><strong>{r.title}</strong></div><span>risk {r.composite}</span><span>{money(r.open_interest)}</span></div>)}
        </section>
        <p className="boundary-note">{brief.boundary || data.boundary}</p>
      </div>
    </div>
  )
}

function WorkQueueView({ data, onUpdate }) {
  if (!data) return <div className="view"><p>Loading compliance work queue...</p></div>
  const s = data.summary || {}
  const active = (data.items || []).filter(i => i.status !== 'resolved')
  const resolved = (data.items || []).filter(i => i.status === 'resolved')
  const money = n => `$${((n || 0) / 1e6).toFixed(1)}M`
  const row = item => (
    <div className={`work-row ${item.severity}`} key={item.id}>
      <div className="work-main"><div className="work-meta"><span className={`severity ${item.severity}`}>{item.severity}</span><span>{item.kind.replaceAll('_',' ')}</span><span>{item.owner_role}</span></div><h3>{item.title}</h3><p>{item.detail}</p><div className="work-action"><strong>Recommended:</strong> {item.recommended_action}</div></div>
      <div className="work-side"><div className="work-money">{item.notional ? money(item.notional) : '—'}</div><select value={item.status} onChange={e => onUpdate(item.id, e.target.value)}><option value="open">Open</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option></select></div>
    </div>
  )
  return (
    <div className="view work-view">
      <div className="strip work-strip"><p className="eyebrow">Compliance / Resolution Operations Workspace</p><h1>Handle exceptions, not dashboards.</h1><p className="dek">Arbiter continuously derives work from contract risk, authority state, evidence gaps, HOLDs, and audit integrity. The operator handles the exceptions that actually require judgment.</p><div className="metrics"><div className="metric"><div className="n">{s.active || 0}</div><div className="l">active items</div></div><div className="metric warn"><div className="n">{s.critical || 0}</div><div className="l">critical</div></div><div className="metric"><div className="n">{s.high || 0}</div><div className="l">high priority</div></div><div className="metric"><div className="n">{money(s.notional)}</div><div className="l">notional represented</div></div></div></div>
      <div className="work-wrap"><h2 className="sect-h">Needs attention</h2>{active.length ? active.map(row) : <div className="empty-work">No active exceptions. Arbiter will surface new work here as governed state changes.</div>}{resolved.length > 0 && <><h2 className="sect-h resolved-h">Resolved</h2>{resolved.map(row)}</>}<p className="boundary-note">{data.boundary}</p></div>
    </div>
  )
}

function MarketsView({ markets, selected, detail, loading, onSelectMarket, onAnalyzeClick }) {
  const clean = markets.filter(m => m.verdict.key === 'clean').length
  const monitored = markets.filter(m => m.verdict.key === 'monitored').length
  const review = markets.filter(m => m.verdict.key === 'review').length
  const totalOI = markets.reduce((a, m) => a + (m.open_interest || 0), 0)
  const reviewOI = markets
    .filter(m => m.verdict.key === 'review')
    .reduce((a, m) => a + (m.open_interest || 0), 0)

  return (
    <div className="view">
      <Strip
        count={markets.length}
        clean={clean}
        monitored={monitored}
        review={review}
        totalOI={totalOI}
        reviewOI={reviewOI}
        onAnalyzeClick={onAnalyzeClick}
      />
      <div className="wrap">
        <div className="docket-col">
          <h2 className="col-h">Docket ({markets.length})</h2>
          <div className="docket">
            {markets.map(m => (
              <button
                key={m.ticker}
                className={`item ${selected?.ticker === m.ticker ? 'active' : ''}`}
                onClick={() => onSelectMarket(m)}
                data-verdict={m.verdict.key}
              >
                <div className="item-top">
                  <span className="item-id">{m.ticker}</span>
                  <span className="item-oi">${(m.open_interest / 1e6).toFixed(1)}M</span>
                </div>
                <p className="item-q">{m.title}</p>
                <div className="item-foot">
                  <span className="cat">{m.category}</span>
                  <span className={`vtag ${m.verdict.key}`}>{m.verdict.label}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
        {detail && selected && (
          <DetailPanel detail={detail} market={selected} />
        )}
      </div>
    </div>
  )
}

function Strip({ count, clean, monitored, review, totalOI, reviewOI, onAnalyzeClick }) {
  return (
    <div className="strip">
      <p className="eyebrow">Resolution Workspace</p>
      <h1>Design, monitor, and resolve event contracts with an auditable evidence trail.</h1>
      <p className="dek">
        Arbiter evaluates resolution terms on source, timing, and definition; monitors the governing evidence; and produces a portable resolution record. Contracts that cannot resolve cleanly are held before money moves.
      </p>
      <div className="metrics">
        <div className="metric">
          <div className="n">{count}</div>
          <div className="l">contracts reviewed</div>
        </div>
        <div className="metric">
          <div className="n">${(totalOI / 1e6).toFixed(0)}M</div>
          <div className="l">notional in batch</div>
        </div>
        <div className="metric">
          <div className="n">{clean}</div>
          <div className="l">auto-resolve clean</div>
        </div>
        <div className="metric">
          <div className="n">{monitored}</div>
          <div className="l">resolve · monitored</div>
        </div>
        <div className="metric warn">
          <div className="n">{review}</div>
          <div className="l">held — dispute risk</div>
        </div>
        <div className="metric warn">
          <div className="n">${(reviewOI / 1e6).toFixed(1)}M</div>
          <div className="l">notional held pre-payout</div>
        </div>
        <button className="metric cta" onClick={onAnalyzeClick}>
          <span className="n">Review contract design →</span>
          <span className="l">pre-listing resolution intelligence</span>
        </button>
      </div>
    </div>
  )
}

function DetailPanel({ detail, market }) {
  const { report, resolution } = detail
  const { levers, verdict, composite } = report
  const { trail, outcome } = resolution || {}

  const fillPercent = (val) => {
    if (val <= 20) return val / 20 * 40
    if (val <= 50) return 40 + (val - 20) / 30 * 30
    return 70 + (val - 50) / 50 * 30
  }

  const fillClass = (val) => {
    if (val <= 20) return 'lo'
    if (val <= 50) return 'mid'
    return 'hi'
  }

  const compilerGate = detail.compilation?.status
  const effectiveVerdict = compilerGate === 'BLOCK'
    ? { key: 'review', label: 'BLOCKED', note: 'specification gate' }
    : compilerGate === 'REVIEW'
      ? { key: 'review', label: 'REVIEW', note: 'human review required' }
      : verdict

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="id">{report.ticker}</div>
        <div className="cat2">{report.category}</div>
        <h2>{report.title}</h2>
        <div className={`stamp ${effectiveVerdict.key}`}>
          <span className="v">{effectiveVerdict.label.replace(' — ', ' ')}</span>
          <span className="s">{effectiveVerdict.note}{compilerGate ? ` · ${compilerGate}` : ` · ${composite}`}</span>
        </div>
      </div>

      <div className="sect">
        <p className="sect-h">Resolution criteria</p>
        <div className="crit">
          <div className="row">
            <span className="k">Source</span>
            {report.rules_primary || market?.rules_primary || 'No resolution criteria available.'}
          </div>
        </div>
      </div>

      {detail.compilation && (
        <div className="sect">
          <p className="sect-h">Compiled resolution specification</p>
          <div className="compiler-inline">
            <div className="panel-title-row"><strong>Compiler status</strong><span className={`compile-status ${detail.compilation.status.toLowerCase()}`}>{detail.compilation.status}</span></div>
            <div className="compiler-grid">
              <div><span className="result-label">Authorities</span><strong>{detail.compilation.proposed_spec.authority_ids.join(', ') || 'UNRESOLVED'}</strong></div>
              <div><span className="result-label">Definition</span><strong>{detail.compilation.proposed_spec.definition.type || 'UNRESOLVED'}</strong></div>
              <div><span className="result-label">Compiler</span><strong>v{detail.compilation.compiler_version}</strong></div>
            </div>
            {detail.compilation.unresolved_fields.length > 0 && <div className="unresolved"><strong>Unresolved:</strong> {detail.compilation.unresolved_fields.join(' · ')}</div>}
            {detail.compilation.recommended_fixes?.length > 0 && (
              <div className="compiler-fixes">
                <strong>Recommended fixes</strong>
                {detail.compilation.recommended_fixes.map((f, i) => <div key={`${f.field}-${i}`}>• {f.action}</div>)}
              </div>
            )}
            <details><summary>View proposed machine-readable specification</summary><pre>{JSON.stringify(detail.compilation.proposed_spec, null, 2)}</pre></details>
          </div>
        </div>
      )}

      <div className="sect">
        <p className="sect-h">Ambiguity by lever</p>
        {['source', 'timing', 'definition'].map(k => {
          const l = levers[k]
          return (
            <div key={k} className="lever">
              <div className="lever-top">
                <span className="lever-name">
                  {k.charAt(0).toUpperCase() + k.slice(1)}
                  <span>{l.question}</span>
                </span>
                <span className="lever-score">{l.score}/100</span>
              </div>
              <div className="track">
                <div
                  className={`fill ${fillClass(l.score)}`}
                  style={{ width: `${fillPercent(l.score)}%` }}
                />
              </div>
              <ul className="flags">
                {l.flags.length ? (
                  l.flags.map((f, i) => <li key={i}>{f}</li>)
                ) : (
                  <li className="none">clean — no flags</li>
                )}
              </ul>
            </div>
          )
        })}
        <div className="composite">
          <span className="big">{composite}</span>
          <span className="txt">
            Composite dispute-risk score · <b>{compilerGate === 'BLOCK' ? 'BLOCKED BY SPECIFICATION' : compilerGate === 'REVIEW' ? 'REVIEW REQUIRED' : verdict.label}</b>
            <br />
            weighted: source 0.30 · timing 0.30 · definition 0.40
          </span>
        </div>
      </div>

      {trail && (
        <div className="sect">
          <p className="sect-h">Resolution trail</p>
          <div className="ledger">
            {trail.map((s, i) => (
              <div key={i} className={`lstep ${s.hold ? 'hold' : ''}`}>
                <div className="lstep-t">
                  <span className="lstep-act">{s.act}</span>
                  <span className="lstep-ts">{s.ts}</span>
                </div>
                <div className="lstep-d">{s.detail}</div>
                <div className="lstep-hash">sig {s.sig}…</div>
              </div>
            ))}
          </div>
          <div className={`outcome outcome-${outcome?.toLowerCase() || 'pending'}`}>
            {outcome === 'HELD' && (
              <>
                <span className="badge held">HELD</span>
                No auto-resolution. Escalated to human review before any payout.
              </>
            )}
            {outcome === 'YES' && (
              <>
                <span className="badge yes">YES</span>
                Resolved automatically and written to the ledger with a signed evidence trail.
              </>
            )}
            {outcome === 'NO' && (
              <>
                <span className="badge no">NO</span>
                Resolved automatically and written to the ledger with a signed evidence trail.
              </>
            )}
            {outcome === 'PENDING' && (
              <>
                <span className="badge pending">PENDING</span>
                Contract is clean but awaiting the source value to auto-resolve.
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function MonitoringView({ data, onViewMarkets }) {
  const [lens, setLens] = useState('executive')
  if (!data) return <div className="view"><p>Loading portfolio intelligence...</p></div>

  const s = data.summary || {}
  const by_cat = data.by_category || []
  const gaps = data.coverage_gaps || []
  const pressure = data.lever_pressure || {}
  const topRisks = data.top_risks || []
  const exec = data.executive || {}
  const shared = exec.shared || {}
  const lenses = exec.lenses || {}
  const active = lenses[lens] || {}
  const money = (n) => `$${((n || 0) / 1e6).toFixed(1)}M`

  return (
    <div className="view portfolio-view">
      <div className="strip portfolio-strip">
        <p className="eyebrow">Portfolio Resolution Intelligence · Read-Only</p>
        <h1>A shared resolution-risk control plane for the executive team.</h1>
        <p className="dek">
          Compliance, Market Operations, Finance, and leadership see the same governed contract and evidence state through different operating lenses. The lens changes prioritization—not settlement logic.
        </p>
        <div className="metrics portfolio-metrics">
          <div className="metric"><div className="n">{money(shared.total_notional)}</div><div className="l">portfolio notional</div></div>
          <div className="metric"><div className="n">{money(shared.resolution_risk_notional)}</div><div className="l">resolution-risk notional</div></div>
          <div className="metric"><div className="n">{money(shared.held_notional)}</div><div className="l">held before payout</div></div>
          <div className="metric"><div className="n">{shared.resolution_risk_pct ?? 0}%</div><div className="l">notional monitored / held</div></div>
          <div className="metric"><div className="n">{shared.primary_risk_driver || '—'}</div><div className="l">primary risk driver</div></div>
          <div className="metric"><div className="n">{shared.audit_chain_ok === true ? 'VERIFIED' : 'CHECK'}</div><div className="l">audit chain</div></div>
        </div>
      </div>

      <div className="portfolio-wrap">
        <section className="role-lens-card">
          <div className="role-tabs">
            {[
              ['executive','Executive'], ['compliance','Compliance'], ['market_ops','Market Ops'], ['finance','Finance / CFO']
            ].map(([key,label]) => (
              <button key={key} className={`role-tab ${lens === key ? 'active' : ''}`} onClick={() => setLens(key)}>{label}</button>
            ))}
          </div>
          <div className="role-lens-body">
            <p className="eyebrow">{lens.replace('_',' ')} lens</p>
            <h2>{active.question}</h2>
            <p className="role-headline">{active.headline}</p>
            <div className="priority-list">
              {(active.priorities || []).map((p, i) => (
                <div className="priority-row" key={`${p.name}-${i}`}>
                  <span className={`priority-dot ${p.severity || 'medium'}`}></span>
                  <div><strong>{p.name}</strong><p>{p.detail}</p></div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="monitor-section">
          <h2 className="sect-h">Portfolio posture</h2>
          <div className="summary-grid">
            <div className="summary-card"><div className="n">{s.reviewed || 0}</div><div className="l">contracts reviewed</div></div>
            <div className="summary-card"><div className="n">{s.counts?.clean || 0}</div><div className="l">auto-resolve clean</div></div>
            <div className="summary-card"><div className="n">{s.counts?.monitored || 0}</div><div className="l">monitored</div></div>
            <div className="summary-card warn"><div className="n">{s.counts?.review || 0}</div><div className="l">held for review</div></div>
          </div>
        </div>

        <div className="monitor-section">
          <h2 className="sect-h">Risk pressure</h2>
          <div className="summary-grid">
            {['source', 'timing', 'definition'].map(k => (
              <div className={`summary-card ${pressure.primary_driver === k ? 'warn' : ''}`} key={k}>
                <div className="n">{pressure.averages?.[k] ?? 0}</div>
                <div className="l">{k} average risk</div>
              </div>
            ))}
          </div>
        </div>

        {topRisks.length > 0 && (
          <div className="monitor-section">
            <h2 className="sect-h">Highest-risk contracts</h2>
            <div className="table-like">
              {topRisks.map(row => (
                <div key={row.ticker} className="table-row risk-row">
                  <div className="col"><span className="mono">{row.ticker}</span><br />{row.title}</div>
                  <div className="col num">risk {row.composite}</div>
                  <div className="col num">{money(row.open_interest)}</div>
                  <div className="col">{row.primary_flag || 'no active flag'}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="monitor-section">
          <h2 className="sect-h">Risk by category</h2>
          <div className="table-like">
            {by_cat.map(row => (
              <div key={row.category} className="table-row">
                <div className="col">{row.category}</div>
                <div className="col num">{row.count} contracts</div>
                <div className="col num">{row.review_count} held ({row.review_rate}%)</div>
                <div className="col num">{money(row.held_notional)} held</div>
              </div>
            ))}
          </div>
        </div>

        {gaps.length > 0 && (
          <div className="monitor-section">
            <h2 className="sect-h">Coverage gaps</h2>
            {gaps.map((g, i) => (
              <div key={i} className="gap"><p className="gap-cat">{g.category}</p><p className="gap-rec">{g.recommendation}</p></div>
            ))}
          </div>
        )}
        <p className="boundary-note">{exec.boundary || data.boundary}</p>
      </div>
    </div>
  )
}

function BenchmarkView({ data }) {
  if (!data) return <div className="view"><p>Loading benchmark...</p></div>
  const m = data.metrics || {}
  const modes = m.by_expected_failure_mode || {}
  const pct = (x) => x == null ? '—' : `${(x * 100).toFixed(1)}%`

  return (
    <div className="view benchmark-view">
      <div className="strip benchmark-strip">
        <p className="eyebrow">Arbiter Resolution Benchmark</p>
        <h1>Test the resolution engine against known-clean contracts and controlled defects.</h1>
        <p className="dek">
          This is a development/calibration benchmark, not an external accuracy claim. Clean parents test false alarms; controlled mutations test whether Arbiter detects planted source, timing, and definition failures and attributes them to the correct lever.
        </p>
        <div className="metrics benchmark-metrics">
          <div className="metric"><div className="n">{m.total_cases || 0}</div><div className="l">total eval cases</div></div>
          <div className="metric"><div className="n">{m.clean_cases || 0}</div><div className="l">real clean parents</div></div>
          <div className="metric"><div className="n">{m.mutation_cases || 0}</div><div className="l">controlled mutations</div></div>
          <div className="metric"><div className="n">{pct(m.defect_detection_rate)}</div><div className="l">defect detection</div></div>
          <div className="metric"><div className="n">{pct(m.correct_lever_rate_on_detected)}</div><div className="l">lever attribution</div></div>
          <div className="metric"><div className="n">{pct(m.clean_auto_resolve_rate)}</div><div className="l">clean recognition</div></div>
        </div>
      </div>

      <div className="benchmark-wrap">
        <section className="benchmark-card">
          <p className="sect-h">Controlled failure modes</p>
          <div className="benchmark-table">
            {Object.entries(modes).map(([name, row]) => (
              <div className="benchmark-row" key={name}>
                <div>
                  <div className="benchmark-code">{name}</div>
                  <div className="benchmark-sub">{row.n} validated cases</div>
                </div>
                <div className="benchmark-score">{row.detected}/{row.n}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="benchmark-card benchmark-method">
          <p className="sect-h">Methodology boundary</p>
          <h3>Development benchmark</h3>
          <p>{data.methodology?.note}</p>
          <div className="benchmark-rule">
            <strong>Do not market these numbers as independent accuracy.</strong>
            <span>The clean set was used during development. A separate untouched holdout is required before external performance claims.</span>
          </div>
          <div className="benchmark-rule">
            <strong>Mutation lineage is explicit.</strong>
            <span>Each synthetic case descends from a real clean parent and carries a known planted defect plus a deterministic validator.</span>
          </div>
          <div className="benchmark-rule">
            <strong>Binding resolution remains deterministic.</strong>
            <span>The benchmark evaluates the governed Arbiter engine; an LLM is not used to declare benchmark truth.</span>
          </div>
        </section>
      </div>
    </div>
  )
}

function InfrastructureView({ data }) {
  const [providerForm, setProviderForm] = useState({ provider: 'openai', api_key: '', default_model: 'gpt-6-astra', fast_model: 'gpt-5.6-terra', daily_max_calls: 500 })
  const [providerMessage, setProviderMessage] = useState('')
  if (!data) return <div className="view"><p>Loading resolution controls...</p></div>
  const d = data.domain || {}
  const controls = data.controls || []
  const authorities = data.authorities || []
  const audit = data.audit || {}
  return (
    <div className="view control-view">
      <div className="section-head">
        <p className="eyebrow">Resolution Control Infrastructure</p>
        <h1>Define → Evidence → Resolve → Audit</h1>
        <p>Persistent controls behind settlement: versioned contract specifications, governed authorities, append-only evidence, replayable resolution runs, and a hash-chained audit record.</p>
      </div>
      <div className="control-metrics">
        {[
          ['Contract versions', d.contracts || 0], ['Authorities', d.authorities || 0],
          ['Evidence records', d.evidence_records || 0], ['Resolution runs', d.resolution_runs || 0],
          ['Audit events', d.audit_events || 0], ['Audit chain', d.audit_chain?.ok ? 'VERIFIED' : 'CHECK']
        ].map(([label,value]) => <div className="stat-card" key={label}><div className="n">{value}</div><div className="l">{label}</div></div>)}
      </div>
      <div className="control-grid">
        <section className="control-panel">
          <h2>Control library</h2>
          {controls.map(c => <div className="control-row" key={c.id}>
            <div><strong>{c.id}</strong> · {c.name}</div>
            <span className={`control-severity ${c.severity}`}>{c.severity.toUpperCase()}</span>
            <p>{c.description}</p>
          </div>)}
        </section>
        <section className="control-panel">
          <h2>Governed authorities</h2>
          {authorities.map(a => <div className="authority-row" key={`${a.authority_id}-${a.version}`}>
            <div><strong>{a.name}</strong></div><div className="mono">{a.authority_id} · v{a.version}</div>
            <div className="muted">{a.organization} · {a.source_type}</div>
          </div>)}
        </section>
      </div>
      <section className="control-panel developer-panel">
        <div className="panel-title-row"><h2>Developer platform</h2><span className="audit-ok">v1 PREVIEW</span></div>
        <p>Integrate Arbiter directly into market-listing, evidence, resolution, and audit pipelines.</p>
        <div className="developer-links">
          <a href="/docs" target="_blank" rel="noreferrer">Interactive API docs ↗</a>
          <a href="/redoc" target="_blank" rel="noreferrer">ReDoc reference ↗</a>
          <a href="/openapi.json" target="_blank" rel="noreferrer">OpenAPI schema ↗</a>
        </div>
        <div className="mono muted">Auth: {data.developer?.auth?.enabled ? 'X-Arbiter-Key required' : 'local-open · configure ARBITER_API_KEYS for protected writes'}</div>
      </section>
      <section className="control-panel model-gateway-panel">
        <div className="panel-title-row"><h2>Model Intelligence Gateway</h2><span className="agent-mode">ADVISORY ONLY</span></div>
        <p>Frontier models can interpret contracts and assist operators, but cannot determine or authorize settlement.</p>
        <div className="compiler-grid">
          <div><span className="result-label">Provider</span><strong>{data.model_gateway?.provider || 'disabled'}</strong></div>
          <div><span className="result-label">Default model</span><strong>{data.model_gateway?.default_model || '—'}</strong></div>
          <div><span className="result-label">Invocations</span><strong>{data.model_gateway?.invocations?.total || 0}</strong></div>
        </div>
        <p className="boundary-note">{data.model_gateway?.authority_boundary}</p>
      </section>
      <section className="control-panel model-admin-panel">
        <div className="panel-title-row"><h2>Models & Credentials</h2><span className="audit-ok">TENANT GOVERNED</span></div>
        <p>Authorized administrators can connect a model provider without exposing the raw credential after submission. Provider models remain advisory only.</p>
        <div className="compiler-grid">
          {(data.enterprise_secrets?.providers || []).map(p => <div key={p.provider}><span className="result-label">{p.provider}</span><strong>{p.enabled ? 'Connected' : 'Disabled'}</strong><div className="mono muted">{p.credential?.masked_value || '—'}</div></div>)}
        </div>
        <div className="provider-form">
          <select value={providerForm.provider} onChange={e => setProviderForm({...providerForm, provider:e.target.value})}><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option></select>
          <input type="password" placeholder="Provider API key" value={providerForm.api_key} onChange={e => setProviderForm({...providerForm, api_key:e.target.value})} />
          <input placeholder="Default model" value={providerForm.default_model} onChange={e => setProviderForm({...providerForm, default_model:e.target.value})} />
          <input placeholder="Fast model" value={providerForm.fast_model} onChange={e => setProviderForm({...providerForm, fast_model:e.target.value})} />
          <button onClick={async () => {
            setProviderMessage('Saving…')
            try {
              const r = await fetch('/api/model-providers', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...providerForm, allowed_purposes:['contract_triage','semantic_review','case_copilot']}) })
              const d = await r.json(); if (!r.ok) throw new Error(d.detail || 'provider configuration failed')
              setProviderForm({...providerForm, api_key:''}); setProviderMessage('Connected. Reload Infrastructure to refresh status.')
            } catch (e) { setProviderMessage(e.message) }
          }}>Connect / Rotate</button>
        </div>
        {providerMessage && <p className="mono muted">{providerMessage}</p>}
        <p className="boundary-note">Raw secrets are write-only. Arbiter stores only masked metadata in application records and uses encrypted/local or external managed secret custody.</p>
      </section>
      <section className="control-panel data-plane-panel">
        <div className="panel-title-row"><h2>Production Data Plane</h2><span className={data.data_plane?.configuration_gate === 'PASS' ? 'audit-ok' : 'audit-bad'}>{data.data_plane?.configuration_gate || 'CHECK'}</span></div>
        <p>Durable storage, tenant isolation, immutable evidence payloads, concurrency controls, and recovery posture.</p>
        <div className="compiler-grid">
          <div><span className="result-label">Database</span><strong>{data.data_plane?.database?.backend || '—'}</strong></div>
          <div><span className="result-label">Tenant isolation</span><strong>{data.data_plane?.tenant_isolation?.postgres_rls ? 'PostgreSQL RLS' : '—'}</strong></div>
          <div><span className="result-label">Object store</span><strong>{data.data_plane?.object_storage?.backend || '—'}</strong></div>
        </div>
        <p className="boundary-note">{data.data_plane?.boundary}</p>
      </section>
      <section className="control-panel audit-panel">
        <div className="panel-title-row"><h2>Audit chain</h2><span className={audit.chain?.ok ? 'audit-ok' : 'audit-bad'}>{audit.chain?.ok ? 'VERIFIED' : 'UNVERIFIED'}</span></div>
        <div className="mono audit-head">HEAD {audit.chain?.head || '—'}</div>
        {(audit.events || []).slice(0,8).map(e => <div className="audit-row" key={e.event_id}>
          <span className="mono">#{e.sequence}</span><strong>{e.action}</strong><span>{e.object_type}:{e.object_id}</span><span className="muted">{e.actor}</span>
        </div>)}
      </section>
      <p className="boundary-note">Technical governance controls support exchange compliance and auditability; they do not by themselves constitute a legal compliance determination.</p>
    </div>
  )
}

function PolicyView({ data, onReload }) {
  const [draftForm, setDraftForm] = useState(null)
  if (!data) return <div className="view"><p>Loading policy...</p></div>

  const { weights, thresholds, changelog, drafts = [] } = data
  const mutate = async (url, body) => {
    try {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail || d))
      await onReload?.()
      return d
    } catch (e) { window.alert(e.message); throw e }
  }
  const beginDraft = () => setDraftForm({
    source: Math.round(weights.source * 100), timing: Math.round(weights.timing * 100), definition: Math.round(weights.definition * 100),
    clean: thresholds.clean, monitored: thresholds.monitored, note: '', actor: 'operator:policy-admin'
  })
  const createDraft = async () => {
    const total = Number(draftForm.source) + Number(draftForm.timing) + Number(draftForm.definition)
    if (Math.abs(total - 100) > 0.001) return window.alert('Policy weights must total 100%.')
    await mutate('/api/policy/drafts', {
      weights: { source: Number(draftForm.source)/100, timing: Number(draftForm.timing)/100, definition: Number(draftForm.definition)/100 },
      thresholds: { clean: Number(draftForm.clean), monitored: Number(draftForm.monitored) },
      actor: draftForm.actor, note: draftForm.note
    })
    setDraftForm(null)
  }
  const act = async (draft, action) => {
    let actor = action === 'approve' ? 'operator:compliance-checker' : action === 'activate' ? 'operator:policy-admin-2' : draft.created_by
    actor = window.prompt(`${action} as actor`, actor) || actor
    await mutate(`/api/policy/drafts/${draft.draft_id}/${action}`, { actor })
  }

  return (
    <div className="view">
      <div className="strip">
        <p className="eyebrow">Adjudication Policy</p>
        <h1>Governed, versioned, auditable.</h1>
        <p className="dek">
          Active policy is immutable in use. Changes are staged as drafts, validated, independently approved,
          then activated as a new version. Existing resolution runs remain pinned to the policy version they used.
        </p>
      </div>

      <div className="wrap policy-wrap">
        <div className="policy-section">
          <div className="panel-title-row"><h2 className="sect-h">Active policy</h2><span className="audit-ok">ACTIVE</span></div>
          <p className="policy-version">{data.version}</p>
          <div className="policy-item">
            <h3>Lever weights</h3>
            <div className="policy-grid">
              <div>Source: {Math.round(weights.source * 100)}%</div>
              <div>Timing: {Math.round(weights.timing * 100)}%</div>
              <div>Definition: {Math.round(weights.definition * 100)}%</div>
            </div>
          </div>
          <div className="policy-item">
            <h3>Verdict thresholds</h3>
            <div className="policy-grid">
              <div>Clean: ≤ {thresholds.clean}</div>
              <div>Monitored: ≤ {thresholds.monitored}</div>
              <div>Review: &gt; {thresholds.monitored}</div>
            </div>
          </div>
          {!draftForm && <button className="run" onClick={beginDraft}>Create governed policy draft</button>}
          {draftForm && <div className="policy-draft-form">
            <h3>New policy draft</h3>
            <div className="policy-edit-grid">
              <label>Source %<input type="number" value={draftForm.source} onChange={e=>setDraftForm({...draftForm,source:e.target.value})}/></label>
              <label>Timing %<input type="number" value={draftForm.timing} onChange={e=>setDraftForm({...draftForm,timing:e.target.value})}/></label>
              <label>Definition %<input type="number" value={draftForm.definition} onChange={e=>setDraftForm({...draftForm,definition:e.target.value})}/></label>
              <label>Clean ≤<input type="number" value={draftForm.clean} onChange={e=>setDraftForm({...draftForm,clean:e.target.value})}/></label>
              <label>Monitored ≤<input type="number" value={draftForm.monitored} onChange={e=>setDraftForm({...draftForm,monitored:e.target.value})}/></label>
            </div>
            <label className="policy-wide-field">Change reason<input value={draftForm.note} onChange={e=>setDraftForm({...draftForm,note:e.target.value})} placeholder="Required governance rationale"/></label>
            <div className="policy-actions"><button className="run" onClick={createDraft}>Save draft</button><button className="template-action" onClick={()=>setDraftForm(null)}>Cancel</button></div>
          </div>}
        </div>

        <div className="policy-section">
          <h2 className="sect-h">Governance workflow</h2>
          <p className="muted">Draft → submit → independent checker approval → activate. The maker cannot approve their own change.</p>
          <div className="changelog">
            {drafts.length ? drafts.map(d => <div key={d.draft_id} className="changelog-entry">
              <div className="entry-head"><span className="entry-version">{d.status.toUpperCase()}</span><span className="entry-ts mono">{d.draft_id}</span></div>
              <div className="entry-note">{d.note || 'No rationale supplied'}</div>
              <div className="entry-by">by {d.created_by} · base {d.base_version}</div>
              <div className="policy-actions">
                {d.status === 'draft' && <button className="template-action" onClick={()=>act(d,'submit')}>Submit</button>}
                {d.status === 'pending_approval' && <button className="template-action" onClick={()=>act(d,'approve')}>Approve as checker</button>}
                {d.status === 'approved' && <button className="run" onClick={()=>act(d,'activate')}>Activate version</button>}
              </div>
            </div>) : <div className="empty-card">No governed policy drafts yet.</div>}
          </div>
        </div>

        <div className="policy-section policy-history">
          <h2 className="sect-h">Active version history</h2>
          <div className="changelog">
            {changelog.map((c, i) => (
              <div key={i} className="changelog-entry">
                <div className="entry-head"><span className="entry-version">{c.version}</span><span className="entry-ts">{new Date(c.at).toISOString().slice(0, 10)}</span></div>
                <div className="entry-note">{c.note}</div><div className="entry-by">by {c.by}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function CasesView({ data, onNew, onOpen, onTemplate, onCopilot }) {
  const cases = data?.cases || []
  const templates = data?.templates || []
  return (
    <main className="cases-view page-shell">
      <div className="eyebrow">CASE REGISTRY · REUSABLE CONTRACT WORK</div>
      <div className="page-title-row">
        <div>
          <h1>Saved cases and contract templates.</h1>
          <p>Every compiler run is retained. Reopen a case, revise it, rerun it, or start a new contract from a reusable template.</p>
        </div>
        <button className="run" onClick={onNew}>New contract review</button>
      </div>
      <section className="cases-section">
        <h2 className="sect-h">Recent cases</h2>
        <div className="case-list">
          {cases.length ? cases.map(c => (
            <div className="case-row" key={c.case_id}>
              <button className="case-main" onClick={() => onOpen({ question: c.title, criteria: c.criteria, case_id: c.case_id })}>
                <div><span className="mono tiny">{c.case_id}</span><strong>{c.title}</strong><span className="muted">Updated {new Date(c.updated_at).toLocaleString()}</span></div>
                <div className="case-meta"><span className={`compile-status ${(c.compiler_status || '').toLowerCase()}`}>{c.compiler_status}</span><span>{c.resolution_outcome}</span></div>
              </button>
              <div className="case-actions">
                <button className="template-action copilot-action" onClick={() => onCopilot(c)}>Ask Copilot</button>
                <button className="template-action" onClick={() => onTemplate(c)}>Save as template</button>
              </div>
            </div>
          )) : <div className="empty-card">No saved cases yet. Compile a contract and it will appear here automatically.</div>}
        </div>
      </section>
      <section className="cases-section">
        <h2 className="sect-h">Templates</h2>
        <div className="template-grid">
          {templates.length ? templates.map(t => (
            <button className="template-card" key={t.template_id} onClick={() => onOpen({ question: t.title, criteria: t.criteria, source_template_id: t.template_id })}>
              <span className="mono tiny">{t.template_id}</span><strong>{t.name}</strong><span>{t.title}</span><small>Start new case from template →</small>
            </button>
          )) : <div className="empty-card">No templates yet. Templates can be created from validated recurring contract structures.</div>}
        </div>
      </section>
    </main>
  )
}

function CopilotModal({ caseItem, onClose }) {
  const [question, setQuestion] = useState('Why is this case in its current state, and what should I do next?')
  const [answer, setAnswer] = useState(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const ask = async () => {
    if (!question.trim()) return
    setLoading(true); setErr('')
    try {
      const r = await fetch(`/api/cases/${caseItem.case_id}/copilot`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, model_tier: 'default' })
      })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail || d))
      setAnswer(d)
    } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }

  const o = answer?.output || {}
  return (
    <div className="scrim open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal copilot-modal">
        <div className="modal-head">
          <div><p className="eyebrow">ARBITER COPILOT · ADVISORY</p><h3>{caseItem.title}</h3><p>Ask about governed case state, compiler findings, evidence, and next actions. Copilot cannot authorize settlement.</p></div>
          <button className="x" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="copilot-boundary">AI interprets and explains. Policy, evidence, deterministic logic, and human approvals remain authoritative.</div>
          <div className="field"><label>Operator question</label><textarea value={question} onChange={e=>setQuestion(e.target.value)} /></div>
          <button className="run" disabled={loading} onClick={ask}>{loading ? 'Analyzing…' : 'Ask Arbiter Copilot'}</button>
          {err && <div className="err show">{err}</div>}
          {answer && <div className="copilot-response">
            <div className="panel-title-row"><h4>Advisory answer</h4><span className="agent-mode">NON-BINDING</span></div>
            <p className="copilot-answer">{o.answer}</p>
            <div className="compiler-grid">
              <div><span className="result-label">Case state</span><strong>{o.case_state || '—'}</strong></div>
              <div><span className="result-label">Confidence</span><strong>{o.confidence || '—'}</strong></div>
              <div><span className="result-label">Human judgment</span><strong>{o.requires_human_judgment ? 'REQUIRED' : 'NOT FLAGGED'}</strong></div>
            </div>
            {!!o.next_actions?.length && <div className="compiler-fixes"><strong>Next actions</strong>{o.next_actions.map((x,i)=><div key={i}>• {x}</div>)}</div>}
            {!!o.grounding?.length && <div className="compiler-fixes"><strong>Grounded in case record</strong>{o.grounding.map((x,i)=><div key={i}>• {x}</div>)}</div>}
            <details><summary>Model provenance</summary><pre>{JSON.stringify(answer.provenance, null, 2)}</pre></details>
          </div>}
        </div>
      </div>
    </div>
  )
}

function AnalyzeModal({ onClose, onSuccess, initial = null }) {
  const [q, setQ] = useState(initial?.question || '')
  const [c, setC] = useState(initial?.criteria || '')
  const [analyzing, setAnalyzing] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState(null)

  const handleAnalyze = async () => {
    if (!q.trim() || !c.trim()) {
      setErr('Enter both the market question and its resolution criteria.')
      return
    }
    setAnalyzing(true)
    setErr('')
    try {
      const analysisR = await fetch('/api/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, criteria: c, use_llm: false, case_id: initial?.case_id || null, source_template_id: initial?.source_template_id || null })
      })
      if (!analysisR.ok) throw new Error('analysis or compilation failed')
      const d = await analysisR.json()
      setResult(d)
      if (onSuccess) onSuccess(d)
    } catch (e) {
      setErr(e.message)
    } finally {
      setAnalyzing(false)
    }
  }

  const design = result?.design
  const report = result?.report

  return (
    <div className="scrim open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal modal-wide">
        <div className="modal-head">
          <div>
            <h3>Resolution Compiler</h3>
            <p>Compile natural-language market rules into a proposed executable Resolution Specification, then run the same governed integrity review before listing.</p>
          </div>
          <button className="x" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="field">
            <label htmlFor="q">Market question</label>
            <input
              id="q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Will the front-month WTI crude contract settle above $80.00 on Sep 30, 2026?"
            />
          </div>
          <div className="field">
            <label htmlFor="c">Resolution criteria</label>
            <textarea
              id="c"
              value={c}
              onChange={(e) => setC(e.target.value)}
              placeholder="Settles YES if the NYMEX front-month Light Sweet Crude Oil futures settlement price on the settlement date is at or above $80.00. Source: CME Group official daily settlement..."
            />
          </div>
          {err && <div className="err show">{err}</div>}
          <button className="run" onClick={handleAnalyze} disabled={analyzing}>
            {analyzing ? '⟳ Compiling…' : 'Compile + review contract'}
          </button>

          {result?.compilation && (
            <div className="design-block compiler-result">
              <div className="panel-title-row"><h4>Resolution Specification</h4><span className={`compile-status ${result.compilation.status.toLowerCase()}`}>{result.compilation.status}</span></div>
              <div className="compiler-grid">
                <div><span className="result-label">Authorities</span><strong>{result.compilation.proposed_spec.authority_ids.join(', ') || 'UNRESOLVED'}</strong></div>
                <div><span className="result-label">Definition</span><strong>{result.compilation.proposed_spec.definition.type || 'UNRESOLVED'}</strong></div>
                <div><span className="result-label">Compiler</span><strong>v{result.compilation.compiler_version}</strong></div>
              </div>
              {result.compilation.unresolved_fields.length > 0 && <div className="unresolved"><strong>Unresolved:</strong> {result.compilation.unresolved_fields.join(' · ')}</div>}
              {result.compilation.semantic && (
                <div className="semantic-card">
                  <div className="panel-title-row">
                    <h4>Semantic Contract Intelligence</h4>
                    <span className={`compile-status ${(result.compilation.semantic.status || '').toLowerCase()}`}>{result.compilation.semantic.status}</span>
                  </div>
                  {result.compilation.semantic.concepts?.map((concept) => (
                    <div key={concept.concept_id} className="semantic-concept">
                      <strong>{concept.name}</strong>
                      <p>{concept.plain_language}</p>
                    </div>
                  ))}
                  {result.compilation.semantic.clarification_questions?.length > 0 && (
                    <div className="compiler-fixes">
                      <strong>Meaning that still needs to be pinned down</strong>
                      {result.compilation.semantic.clarification_questions.map((q, i) => (
                        <div key={`${q.field}-${i}`}>• {q.question}</div>
                      ))}
                    </div>
                  )}
                  <details><summary>View extracted semantics</summary><pre>{JSON.stringify(result.compilation.semantic.extracted_semantics, null, 2)}</pre></details>
                </div>
              )}
              {result.compilation.recommended_fixes?.length > 0 && (
                <div className="compiler-fixes">
                  <strong>Recommended fixes</strong>
                  {result.compilation.recommended_fixes.map((f, i) => <div key={`${f.field}-${i}`}>• {f.action}</div>)}
                </div>
              )}
              <details><summary>View proposed machine-readable specification</summary><pre>{JSON.stringify(result.compilation.proposed_spec, null, 2)}</pre></details>
            </div>
          )}

          {design && report && (
            <div className="design-result">
              <div className="design-summary">
                <div>
                  <span className="result-label">Listing readiness</span>
                  <strong>{design.readiness_score}/100</strong>
                </div>
                <div>
                  <span className="result-label">Status</span>
                  <strong className={`status-${report.verdict.key}`}>{design.status}</strong>
                </div>
                <div>
                  <span className="result-label">Dispute risk</span>
                  <strong>{report.composite}/100</strong>
                </div>
              </div>

              <div className="design-block">
                <h4>Detected deficiencies</h4>
                {design.deficiencies.length ? (
                  <div className="deficiency-list">
                    {design.deficiencies.map((d, i) => (
                      <div className="deficiency" key={`${d.lever}-${i}`}>
                        <span className={`severity ${d.severity}`}>{d.severity}</span>
                        <span className="mono">{d.lever}</span>
                        <span>{d.flag}</span>
                      </div>
                    ))}
                  </div>
                ) : <p className="clean-copy">No structural deficiencies detected by the governed rule set.</p>}
              </div>

              <div className="design-block">
                <h4>Recommended drafting fixes</h4>
                {design.recommended_clauses.length ? design.recommended_clauses.map((fix, i) => (
                  <div className="fix-card" key={i}>
                    <div className="fix-head"><span className="mono">{fix.lever}</span>{fix.title}</div>
                    <p>{fix.text}</p>
                  </div>
                )) : <p className="clean-copy">No drafting additions recommended.</p>}
              </div>

              <div className="design-block">
                <h4>Revised criteria package</h4>
                <pre className="drafting-fix">{design.drafting_fix}</pre>
              </div>

              <p className="authority-note">{design.principle}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
