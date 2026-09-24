import React, { useEffect, useState } from 'react'
import { api, blocker, money, plural, post, splitTitle, TIER } from './api'
import { useDecisionOrder } from './hooks'
import { Loading } from './Today'

const RELATION = {
  same_event: 'same event',
  same_series: 'same series, earlier event',
  cross_event: 'different event',
  cross_venue: 'other venue',
  decided: 'this contract',
}
const STATUS = {
  novel: ['First ruling', 'No precedent covers these contracts. This decision becomes the precedent.'],
  follows: ['Follows precedent', 'Agrees with the applicable ruling and cites it.'],
  consistent: ['Consistent with precedent', 'Agrees with the applicable ruling. It will be cited automatically.'],
  divergent: ['Departs from precedent', 'Explain what distinguishes these contracts, or overrule the precedent.'],
}

export default function Decide({ overview, clusters, items, clusterId, reload, go }) {
  const ordered = useDecisionOrder(clusters, items)
  const selected = ordered.find(c => c.cluster_id === clusterId) || (clusterId ? null : ordered[0])
  const [context, setContext] = useState(null)
  const [selection, setSelection] = useState('')
  const [rationale, setRationale] = useState('')
  const [governingRule, setGoverningRule] = useState('')
  const [cited, setCited] = useState([])
  const [check, setCheck] = useState(null)
  const [departMode, setDepartMode] = useState('distinguish')
  const [distinguish, setDistinguish] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [outcome, setOutcome] = useState(null)

  const cid = selected?.cluster_id
  useEffect(() => {
    setContext(null)
    setSelection('')
    setRationale('')
    setGoverningRule('')
    setCited([])
    setCheck(null)
    setDistinguish('')
    setDepartMode('distinguish')
    setError('')
    if (!cid) return
    api(`/api/decision-context/${encodeURIComponent(cid)}`).then(setContext).catch(e => setError(e.message))
  }, [cid])

  useEffect(() => {
    if (!cid || !selection.trim()) {
      setCheck(null)
      return
    }
    const t = setTimeout(() => {
      post('/api/decisions/consistency', { cluster_id: cid, selection, precedent_ids: cited }).then(setCheck).catch(() => setCheck(null))
    }, 300)
    return () => clearTimeout(t)
  }, [selection, cited, cid])

  if (!overview) return <Loading />

  function follow(m) {
    setSelection(m.ruling?.selection || '')
    setGoverningRule(m.ruling?.governing_rule || '')
    setCited(c => Array.from(new Set([...c, m.precedent_id])))
    if (!rationale.trim()) setRationale(`Follows precedent ${m.precedent_id}: the ${TIER[m.tier]?.toLowerCase()} applies to these contracts.`)
    setTimeout(() => document.getElementById('rule')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }

  async function record() {
    setSaving(true)
    setError('')
    const divergent = check?.status === 'divergent'
    try {
      const next = await post('/api/decisions', {
        cluster_id: cid,
        selection,
        rationale,
        governing_rule: governingRule,
        precedent_ids: cited,
        distinguish: divergent && departMode === 'distinguish' ? distinguish : '',
        overrules: divergent && departMode === 'overrule' ? check?.precedent?.precedent_id : null,
        owner: 'Resolution Ops',
        actor: 'operator:resolution-ops',
      })
      setOutcome({ ...next, pattern: selected })
      await reload()
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      if (e.status === 409 && e.body?.detail?.consistency) setCheck(e.body.detail.consistency)
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const b = selected ? blocker(selected.blocker_type) : null
  const prompt = context?.decision_prompt || {}
  const clearable = context?.clearability ? context.clearability.clearable : true
  const matches = context?.precedent_matches || []
  const status = check?.status
  const needsDeparture = status === 'divergent'
  const ready = selection.trim() && rationale.trim() && (!needsDeparture || departMode === 'overrule' || distinguish.trim())
  const next = ordered.find(c => c.cluster_id !== cid)

  return (
    <div className="decide">
      <aside className="decide-list">
        <span className="nav-label">{plural(ordered.length, 'pattern')} to decide</span>
        {ordered.map(c => {
          const cb = blocker(c.blocker_type)
          return (
            <a key={c.cluster_id} href={`#/decide/${c.cluster_id}`} className={`mini tone-${cb.tone} ${c.cluster_id === cid ? 'on' : ''}`}>
              <span className="pattern-bar" />
              <span>
                <strong>{splitTitle(c.example_title).question}</strong>
                <small>{cb.name} · {plural(c.count, 'case')}{c.precedent ? ' · precedent' : ''}</small>
              </span>
            </a>
          )
        })}
        {ordered.length === 0 && <p className="empty">Queue is clear.</p>}
      </aside>

      <div className="decide-main">
        {outcome && <Outcome outcome={outcome} next={next} onDismiss={() => setOutcome(null)} />}

        {!selected ? (
          !outcome && (
            <div className="panel empty-state">
              <h2>{clusterId ? 'That pattern has been decided.' : 'Nothing to decide.'}</h2>
              <p>{ordered.length ? 'Pick the next pattern on the left.' : 'Every open case is covered. New ones arrive with the next venue sync.'}</p>
            </div>
          )
        ) : (
          <>
            <header className={`decide-head tone-${b.tone}`}>
              <div className="pattern-top">
                <span className={`tag ${b.tone}`}>{b.name}</span>
                {selected.precedent && <span className="tag precedent">Precedent applies</span>}
              </div>
              <h1>{splitTitle(selected.example_title).question}{selected.count > 1 && <span className="plus"> + {selected.count - 1} more</span>}</h1>
              <div className="stats">
                <div><small>Cases</small><strong>{selected.count}</strong></div>
                <div><small>Exposure</small><strong>{money(selected.notional)}</strong></div>
                <div><small>One ruling clears</small><strong>{clearable ? plural(selected.count, 'case') : 'none'}</strong></div>
              </div>
              <ol className="steps">
                <li><a href="#understand" onClick={e => { e.preventDefault(); document.getElementById('understand')?.scrollIntoView({ behavior: 'smooth' }) }}>1 · Understand</a></li>
                <li className={matches.length ? 'lit' : ''}><a href="#precedent" onClick={e => { e.preventDefault(); document.getElementById('precedent')?.scrollIntoView({ behavior: 'smooth' }) }}>2 · Precedent</a></li>
                <li className={selection ? 'lit' : ''}><a href="#rule" onClick={e => { e.preventDefault(); document.getElementById('rule')?.scrollIntoView({ behavior: 'smooth' }) }}>3 · Rule</a></li>
              </ol>
            </header>

            <section className="panel" id="understand">
              <div className="panel-head"><h2><span className="step-n">1</span>The judgment Arbiter needs</h2></div>
              <h3 className="question">{prompt.question || 'What governed judgment resolves this pattern?'}</h3>
              <p className="muted">{selected.why_human || prompt.context}</p>
              <div className="rule-line"><small>Clears when</small><span>{prompt.clear_condition || selected.clear_condition}</span></div>
              <details className="cases-box" open={selected.count <= 3}>
                <summary>{plural(selected.count, 'affected case')}</summary>
                <ul className="cases">
                  {selected.cases.map(i => {
                    const t = splitTitle(i.title)
                    return (
                      <li key={i.id}>
                        <span className={`sev ${i.severity}`}>{i.severity}</span>
                        <span>{t.question}</span>
                        <span className="mono">{t.ref || i.subject}</span>
                      </li>
                    )
                  })}
                </ul>
              </details>
            </section>

            <section className="panel" id="precedent">
              <div className="panel-head">
                <h2><span className="step-n">2</span>What was ruled before</h2>
                <span className="muted">{matches.length ? `${matches.length} applicable` : 'none applies'}</span>
              </div>
              {!context && <Loading />}
              {context && matches.length === 0 && (
                <p className="muted">No earlier ruling covers these contracts. Your decision becomes precedent for future contracts with the same clause or template.</p>
              )}
              {matches.map(m => <Match key={m.precedent_id} m={m} onFollow={follow} />)}
            </section>

            <section className="panel" id="rule">
              <div className="panel-head"><h2><span className="step-n">3</span>Rule</h2><span className="muted">Audited · hash-chained</span></div>
              {!clearable && <div className="callout warn"><strong>This ruling won’t clear cases.</strong><span>{context?.clearability?.reason}</span></div>}
              <label className="field">
                <span>Ruling</span>
                <input value={selection} onChange={e => setSelection(e.target.value)} placeholder="e.g. Initial official release controls" />
              </label>
              {status && (
                <div className={`status status-${status}`}>
                  <b>{STATUS[status]?.[0]}</b>
                  <span>{STATUS[status]?.[1]}</span>
                  {check?.conflicting?.length > 0 && <span className="split">Earlier rulings disagree: {check.conflicting.map(c => `“${c.selection}”`).join(' vs ')}</span>}
                </div>
              )}
              {needsDeparture && (
                <div className="depart">
                  <div className="seg small">
                    <button className={departMode === 'distinguish' ? 'on' : ''} onClick={() => setDepartMode('distinguish')}>Distinguish</button>
                    <button className={departMode === 'overrule' ? 'on' : ''} onClick={() => setDepartMode('overrule')}>Overrule {check?.precedent?.precedent_id}</button>
                  </div>
                  {departMode === 'distinguish' ? (
                    <textarea value={distinguish} onChange={e => setDistinguish(e.target.value)} placeholder="What in these contracts’ terms or facts differs from the precedent?" />
                  ) : (
                    <p className="muted">Overruling is prospective. The earlier decisions keep governing the cases they decided, but stop guiding new contracts.</p>
                  )}
                </div>
              )}
              <label className="field">
                <span>Governing rule <em>optional</em></span>
                <input value={governingRule} onChange={e => setGoverningRule(e.target.value)} placeholder="The rule future contracts should be read by" />
              </label>
              <label className="field">
                <span>Rationale</span>
                <textarea value={rationale} onChange={e => setRationale(e.target.value)} placeholder="The rule, authority, evidence or policy basis for this judgment." />
              </label>
              {error && <div className="callout bad"><span>{error}</span></div>}
              <div className="rule-actions">
                <button className="btn primary big" disabled={saving || !ready} onClick={record}>
                  {saving ? 'Recording and re-evaluating…' : clearable ? `Record ruling · clear ${plural(selected.count, 'case')}` : 'Record ruling'}
                </button>
                <p className="fine">Changes operator workflow only. YES/NO/HOLD outcomes, settlement and payout are never changed by a decision.</p>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}

function Match({ m, onFollow }) {
  const r = m.ruling || {}
  return (
    <div className={`match tier-${m.tier}`}>
      <div className="match-head">
        <span className="tag tier">{TIER[m.tier] || m.tier}</span>
        <span className="muted small">{RELATION[m.relation] || m.relation} · score {Number(m.score).toFixed(2)} · {(r.decided_at || '').slice(0, 10)}</span>
        <a className="mono small link" href={`#/precedents/${m.precedent_id}`}>{m.precedent_id}</a>
      </div>
      <blockquote>“{r.selection}”</blockquote>
      {r.governing_rule && <p className="muted small">Rule: {r.governing_rule}</p>}
      {m.matched_clause && (
        <div className="clauses">
          <div><small>Clause ruled on</small><q>{m.matched_clause.precedent_clause}</q></div>
          <div><small>Clause in this contract</small><q>{m.matched_clause.contract_clause}</q></div>
        </div>
      )}
      <div className="match-foot">
        <span className="muted small">{plural(r.contracts || 0, 'decided contract')}</span>
        {m.applies && <button className="btn" onClick={() => onFollow(m)}>Follow this ruling</button>}
      </div>
    </div>
  )
}

function Outcome({ outcome, next, onDismiss }) {
  const work = outcome.reevaluation?.workload || {}
  const cons = outcome.consistency || {}
  const decisionId = outcome.decision?.decision_id
  const cleared = (outcome.reevaluation?.queue?.items || []).filter(i => i.governed_by?.decision_id === decisionId)
  return (
    <section className="outcome">
      <div className="outcome-top">
        <span className="check" aria-hidden="true">✓</span>
        <div>
          <h2>{work.cases_cleared ? `Cleared ${plural(work.cases_cleared, 'case')} with one ruling.` : 'Ruling recorded.'}</h2>
          <p>“{outcome.decision?.selection}”</p>
        </div>
        <button className="link" onClick={onDismiss}>Dismiss</button>
      </div>
      <div className="outcome-grid">
        <div><small>Queue</small><strong>{work.before?.active_cases ?? '—'} → {work.after?.active_cases ?? '—'}</strong><span>open cases</span></div>
        <div><small>Decisions left</small><strong>{work.after?.human_decisions ?? '—'}</strong><span>was {work.before?.human_decisions ?? '—'}</span></div>
        <div><small>Precedent</small><strong>{cons.status === 'novel' ? 'New' : cons.status === 'divergent' ? 'Departed' : 'Followed'}</strong><span>{outcome.precedent ? `${plural(outcome.precedent.clauses, 'clause')} on record` : ''}</span></div>
        <div><small>Record</small><strong className="mono">{String(outcome.decision?.decision_hash || '').slice(7, 19)}</strong><span>hash-chained</span></div>
      </div>
      {cleared.length > 0 && (
        <div className="cleared">
          {cleared.map(i => <span key={i.id} className="mono">{i.subject}</span>)}
        </div>
      )}
      <div className="outcome-actions">
        {next ? <a className="btn primary" href={`#/decide/${next.cluster_id}`} onClick={onDismiss}>Next pattern: {splitTitle(next.example_title).question.slice(0, 48)}… →</a> : <a className="btn primary" href="#/today" onClick={onDismiss}>Queue is clear. Back to Today →</a>}
        {outcome.precedent && <a className="btn ghost" href={`#/precedents/${outcome.precedent.precedent_id}`}>View precedent</a>}
      </div>
    </section>
  )
}
