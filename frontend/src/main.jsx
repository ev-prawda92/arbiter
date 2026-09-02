import React, { useState, useEffect } from 'react'
import './styles.css'

import ReactDOM from 'react-dom/client'

function App() {
  const [view, setView] = useState('markets') // markets, monitoring, benchmark, policy, analyze
  const [markets, setMarkets] = useState([])
  const [monitoring, setMonitoring] = useState(null)
  const [policy, setPolicy] = useState(null)
  const [benchmark, setBenchmark] = useState(null)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [analyzeModal, setAnalyzeModal] = useState(false)
  const [analyzingLive, setAnalyzingLive] = useState(false)

  useEffect(() => {
    loadMarkets()
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

  const loadMonitoring = async () => {
    try {
      const r = await fetch('/api/portfolio')
      const d = await r.json()
      setMonitoring(d)
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

  const loadPolicy = async () => {
    try {
      const r = await fetch('/api/policy')
      const d = await r.json()
      setPolicy(d)
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
    if (v === 'monitoring' && !monitoring) {
      await loadMonitoring()
    }
    if (v === 'benchmark' && !benchmark) {
      await loadBenchmark()
    }
    if (v === 'policy' && !policy) {
      await loadPolicy()
    }
  }

  return (
    <div className="arbiter">
      <Rail markets={markets} view={view} onViewChange={handleViewChange} onRefresh={() => loadMarkets()} />
      
      {view === 'markets' && (
        <MarketsView
          markets={markets}
          selected={selected}
          detail={detail}
          loading={loading}
          onSelectMarket={selectMarket}
          onAnalyzeClick={() => setAnalyzeModal(true)}
        />
      )}
      
      {view === 'monitoring' && (
        <MonitoringView data={monitoring} onViewMarkets={() => setView('markets')} />
      )}
      
      {view === 'benchmark' && (
        <BenchmarkView data={benchmark} />
      )}

      {view === 'policy' && (
        <PolicyView data={policy} />
      )}

      {analyzeModal && (
        <AnalyzeModal
          onClose={() => setAnalyzeModal(false)}
          onSuccess={(result) => {
            setAnalyzeModal(false)
            // Show result inline or in detail
            setDetail({ report: result.report, resolution: result.resolution })
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
          <span className="sub">Resolution Intelligence Platform</span>
        </div>
        <div className="nav">
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
            Intelligence
          </button>
          <button
            className={`nav-btn ${view === 'benchmark' ? 'active' : ''}`}
            onClick={() => onViewChange('benchmark')}
          >
            Benchmark
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

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="id">{report.ticker}</div>
        <div className="cat2">{report.category}</div>
        <h2>{report.title}</h2>
        <div className={`stamp ${verdict.key}`}>
          <span className="v">{verdict.label.replace(' — ', ' ')}</span>
          <span className="s">{verdict.note} · {composite}</span>
        </div>
      </div>

      <div className="sect">
        <p className="sect-h">Resolution criteria</p>
        <div className="crit">
          <div className="row">
            <span className="k">Source</span>
            {market.rules_primary}
          </div>
        </div>
      </div>

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
            Composite dispute-risk score · <b>{verdict.label}</b>
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
  if (!data) return <div className="view"><p>Loading monitoring data...</p></div>

  const s = data.summary || {}
  const by_cat = data.by_category || []
  const gaps = data.coverage_gaps || []
  const pressure = data.lever_pressure || {}
  const topRisks = data.top_risks || []

  return (
    <div className="view">
      <div className="strip">
        <p className="eyebrow">Portfolio Intelligence · Read-Only</p>
        <h1>Where resolution risk concentrates across the contract portfolio.</h1>
        <p className="dek">
          Because every contract flows through the same governed review, Arbiter can surface weak templates, held notional, recurring ambiguity, and the lever driving the most risk. This intelligence is read-only: it never changes an individual contract outcome.
        </p>
      </div>

      <div className="wrap monitor-wrap">
        <div className="monitor-section">
          <h2 className="sect-h">Summary</h2>
          <div className="summary-grid">
            <div className="summary-card">
              <div className="n">{s.reviewed || 0}</div>
              <div className="l">contracts reviewed</div>
            </div>
            <div className="summary-card">
              <div className="n">{s.counts?.clean || 0}</div>
              <div className="l">auto-resolve clean</div>
            </div>
            <div className="summary-card">
              <div className="n">{s.counts?.monitored || 0}</div>
              <div className="l">monitored</div>
            </div>
            <div className="summary-card warn">
              <div className="n">{s.counts?.review || 0}</div>
              <div className="l">held for review</div>
            </div>
          </div>
        </div>

        <div className="monitor-section">
          <h2 className="sect-h">Primary risk driver</h2>
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
                  <div className="col num">${(row.open_interest / 1e6).toFixed(1)}M</div>
                  <div className="col">{row.primary_flag || 'no active flag'}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="monitor-section">
          <h2 className="sect-h">Disputes by category</h2>
          <div className="table-like">
            {by_cat.map(row => (
              <div key={row.category} className="table-row">
                <div className="col">{row.category}</div>
                <div className="col num">{row.count} contracts</div>
                <div className="col num">{row.review_count} reviewed ({row.review_rate}%)</div>
                <div className="col num">${(row.held_notional / 1e6).toFixed(1)}M held</div>
              </div>
            ))}
          </div>
        </div>

        {gaps.length > 0 && (
          <div className="monitor-section">
            <h2 className="sect-h">Coverage gaps</h2>
            {gaps.map((g, i) => (
              <div key={i} className="gap">
                <p className="gap-cat">{g.category}</p>
                <p className="gap-rec">{g.recommendation}</p>
              </div>
            ))}
          </div>
        )}
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

function PolicyView({ data }) {
  if (!data) return <div className="view"><p>Loading policy...</p></div>

  const { weights, thresholds, changelog } = data

  return (
    <div className="view">
      <div className="strip">
        <p className="eyebrow">Adjudication Policy</p>
        <h1>Governed, versioned, auditable.</h1>
        <p className="dek">
          The weights and thresholds that decide when a contract auto-resolves, gets
          monitored, or is held for review are owned by the exchange or market operator, but versioned
          and logged. No policy changes happen quietly. Every shift is recorded with a
          timestamp, author, and note.
        </p>
      </div>

      <div className="wrap policy-wrap">
        <div className="policy-section">
          <h2 className="sect-h">Current policy</h2>
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
        </div>

        <div className="policy-section">
          <h2 className="sect-h">Changelog</h2>
          <div className="changelog">
            {changelog.map((c, i) => (
              <div key={i} className="changelog-entry">
                <div className="entry-head">
                  <span className="entry-version">{c.version}</span>
                  <span className="entry-ts">{new Date(c.at).toISOString().slice(0, 10)}</span>
                </div>
                <div className="entry-note">{c.note}</div>
                <div className="entry-by">by {c.by}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function AnalyzeModal({ onClose, onSuccess }) {
  const [q, setQ] = useState('')
  const [c, setC] = useState('')
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
      const r = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, criteria: c, use_llm: false })
      })
      if (!r.ok) throw new Error('analysis failed')
      const d = await r.json()
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
            <h3>Contract Intelligence</h3>
            <p>Review resolution design before listing. Arbiter scores the contract, names the deficiencies, and proposes deterministic drafting fixes.</p>
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
            {analyzing ? '⟳ Reviewing…' : 'Run contract intelligence review'}
          </button>

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
