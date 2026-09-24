import React, { useEffect, useState } from 'react'
import { api, label, plural, post, since, TIER } from './api'
import { AskAnswer } from './App'
import { Loading } from './Today'

const EXAMPLES = ['Do acting or interim leaders count?', 'What if a leader dies in office?', 'Which source controls election results?']
const STATE_TONE = { active: 'ok', overruled: 'amber', superseded: 'slate' }

export default function Precedents({ precedents, precedentId }) {
  const all = precedents?.precedents || []
  const [showRetired, setShowRetired] = useState(false)
  const list = all.filter(p => showRetired || p.state === 'active')
  const selectedId = precedentId || list[0]?.precedent_id
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    setDetail(null)
    if (selectedId) api(`/api/precedents/${encodeURIComponent(selectedId)}`).then(setDetail).catch(() => setDetail(null))
  }, [selectedId])

  if (!precedents) return <Loading />
  const retired = all.length - all.filter(p => p.state === 'active').length

  return (
    <div className="precedents">
      <header className="page-head">
        <div>
          <span className="eyebrow">Precedents</span>
          <h1>Every ruling, remembered and applied.</h1>
          <p className="lede">Each decision becomes precedent. New contracts are checked against it on arrival, and departing from it needs a stated distinction or an overrule.</p>
        </div>
      </header>

      <AskPanel />

      {all.length === 0 ? (
        <div className="panel empty-state">
          <h2>No precedents yet.</h2>
          <p>The first decision you record becomes one. <a className="link" href="#/decide">Decide a pattern →</a></p>
        </div>
      ) : (
        <div className="split-view">
          <div className="p-list">
            <div className="p-list-head">
              <span className="nav-label">{plural(all.length - retired, 'live ruling')}</span>
              {retired > 0 && (
                <label className="toggle">
                  <input type="checkbox" checked={showRetired} onChange={e => setShowRetired(e.target.checked)} /> Show {retired} retired
                </label>
              )}
            </div>
            {list.map(p => (
              <a key={p.precedent_id} href={`#/precedents/${p.precedent_id}`} className={`p-card ${p.precedent_id === selectedId ? 'on' : ''} ${p.state !== 'active' ? 'retired' : ''}`}>
                <div className="pattern-top">
                  <span className={`tag ${STATE_TONE[p.state] || 'slate'}`}>{p.state}</span>
                  {p.review_class && <span className="tag slate">{label(p.review_class)}</span>}
                </div>
                <strong>“{p.selection}”</strong>
                <small>
                  {plural((p.contracts || []).length, 'contract')} decided · {p.matched_contracts ? `applied to ${p.matched_contracts} since` : 'not applied yet'} · {since(p.decided_at)}
                </small>
              </a>
            ))}
          </div>
          <div className="p-detail">{detail ? <Detail d={detail} /> : <Loading />}</div>
        </div>
      )}
    </div>
  )
}

function AskPanel() {
  const [q, setQ] = useState('')
  const [a, setA] = useState(null)
  const [busy, setBusy] = useState(false)
  async function ask(question) {
    const text = question ?? q
    if (!text.trim()) return
    setQ(text)
    setBusy(true)
    try {
      setA(await post('/api/ask', { question: text }))
    } catch (e) {
      setA({ answer: e.message, citations: [] })
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="ask-panel">
      <form onSubmit={e => { e.preventDefault(); ask() }}>
        <label htmlFor="ask-q">Ask Arbiter</label>
        <div className="ask-row">
          <input id="ask-q" value={q} onChange={e => setQ(e.target.value)} placeholder="How have we ruled on…" />
          <button className="btn primary" disabled={busy || !q.trim()}>{busy ? 'Searching…' : 'Ask'}</button>
        </div>
        <div className="examples">
          {EXAMPLES.map(x => <button type="button" key={x} onClick={() => ask(x)}>{x}</button>)}
        </div>
      </form>
      {a && <AskAnswer a={a} inline />}
      <small className="fine">Answers are retrieved from the governed record and cite it. No model writes them, and Arbiter says so when nothing covers a question.</small>
    </section>
  )
}

function Detail({ d }) {
  const p = d.precedent
  const matched = d.matched_contracts || []
  return (
    <article className="panel">
      <div className="pattern-top">
        <span className={`tag ${STATE_TONE[p.state] || 'slate'}`}>{p.state}</span>
        <span className="mono muted small">{p.precedent_id}</span>
        <span className="muted small">decided {(p.decided_at || '').slice(0, 10)} by {p.decided_by}</span>
      </div>
      <blockquote className="ruling">“{p.selection}”</blockquote>
      {p.state === 'overruled' && <div className="callout warn"><strong>Overruled by {p.overruled_by}.</strong><span>{p.overrule_reason}</span></div>}
      <dl className="facts wide">
        {p.governing_rule && <div><dt>Governing rule</dt><dd>{p.governing_rule}</dd></div>}
        <div><dt>Question</dt><dd>{p.question}</dd></div>
        <div><dt>Reasoning</dt><dd>{p.rationale}</dd></div>
      </dl>

      {(p.clauses || []).length > 0 && (
        <>
          <h3 className="sub">Clauses ruled on</h3>
          {p.clauses.map(c => <q className="clause" key={c.normalized}>{c.text}</q>)}
        </>
      )}

      <div className="two-col">
        <div>
          <h3 className="sub">Decided contracts <span className="muted">{(p.contracts || []).length}</span></h3>
          <ContractList contracts={p.contracts || []} />
        </div>
        <div>
          <h3 className="sub">Applied since <span className="muted">{matched.length}</span></h3>
          {matched.length === 0 ? (
            <p className="muted small">No new contract has matched yet. Every venue sync checks.</p>
          ) : (
            <ul className="plain">
              {matched.slice(0, 12).map(m => (
                <li key={m.contract_id}><span className="mono">{m.contract_id}</span><span className="tag tier small">{TIER[m.tier]} · {Number(m.score).toFixed(2)}</span></li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <Appeal contracts={[...(p.contracts || []).map(c => c.contract_id), ...matched.map(m => m.contract_id)]} />
    </article>
  )
}

function ContractList({ contracts }) {
  const [all, setAll] = useState(false)
  const shown = all ? contracts : contracts.slice(0, 5)
  return (
    <>
      <ul className="plain">
        {shown.map(c => (
          <li key={c.contract_id} title={c.title}>
            <span className="t">{c.title}</span>
            <span className="mono muted">{c.market_id || c.contract_id}</span>
          </li>
        ))}
      </ul>
      {contracts.length > 5 && (
        <button className="link more" onClick={() => setAll(v => !v)}>{all ? 'Show fewer' : `Show all ${contracts.length}`}</button>
      )}
    </>
  )
}

function Appeal({ contracts }) {
  const [contract, setContract] = useState(contracts[0] || '')
  const [requested, setRequested] = useState('')
  const [grounds, setGrounds] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  if (!contracts.length) return null
  async function run(e) {
    e.preventDefault()
    setBusy(true)
    try {
      setResult(await post('/api/appeals/check', { contract_id: contract, requested_selection: requested, grounds }))
    } catch (err) {
      setResult({ verdict: 'error', note: err.message })
    } finally {
      setBusy(false)
    }
  }
  const tone = { matches_ruling: 'ok', contradicts_ruling: 'warn', no_ruling: '', error: 'bad' }[result?.verdict] || ''
  return (
    <details className="appeal">
      <summary>Check an appeal against this ruling</summary>
      <form onSubmit={run}>
        <label className="field">
          <span>Contract</span>
          <select value={contract} onChange={e => setContract(e.target.value)}>
            {Array.from(new Set(contracts)).map(c => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Outcome the appellant wants</span>
          <input value={requested} onChange={e => setRequested(e.target.value)} placeholder="e.g. Death does not count as leaving office" />
        </label>
        <label className="field">
          <span>Grounds <em>optional</em></span>
          <input value={grounds} onChange={e => setGrounds(e.target.value)} />
        </label>
        <button className="btn" disabled={busy || !requested.trim()}>{busy ? 'Checking…' : 'Check appeal'}</button>
      </form>
      {result && (
        <div className={`callout ${tone}`}>
          <strong>{label(result.verdict)}</strong>
          <span>{result.note}</span>
          {result.options && <span className="muted small">Options: {result.options.join(' · ')}</span>}
        </div>
      )}
    </details>
  )
}
