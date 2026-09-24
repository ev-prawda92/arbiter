import React, { useEffect, useState } from 'react'
import { api, post, since } from './api'
import { Loading } from './Today'

const TABS = [
  ['overview', 'Overview'],
  ['lineage', 'Lineage'],
  ['log', 'Audit log'],
  ['exceptions', 'Exceptions'],
  ['package', 'Evidence package'],
]
const STAGE_NAME = {
  intake: 'Intake', work: 'Casework', decision: 'Decision', appeal: 'Appeal', resolution: 'Resolution',
  settlement: 'Approval & settlement', audit: 'Audit', governance: 'Governance', system: 'System',
}
const SEV = { critical: 'red', high: 'red', medium: 'amber', low: 'slate' }

export default function Audit({ arg }) {
  const [tab, ...rest] = String(arg || 'overview').split('/')
  const sub = rest.join('/')
  return (
    <div className="audit">
      <header className="page-head">
        <div>
          <span className="eyebrow">Audit</span>
          <h1>The governed record, verifiable by anyone.</h1>
          <p className="lede">Every action is written to a hash-linked chain. Trace any contract end to end, review the exceptions, and export a package an outside auditor verifies on their own machine.</p>
        </div>
      </header>
      <nav className="tabs">
        {TABS.map(([k, l]) => <a key={k} href={`#/audit/${k}`} className={tab === k ? 'on' : ''}>{l}</a>)}
      </nav>
      {tab === 'overview' && <Overview />}
      {tab === 'lineage' && <Lineage contractId={sub} />}
      {tab === 'log' && <Log />}
      {tab === 'exceptions' && <Exceptions />}
      {tab === 'package' && <Package />}
    </div>
  )
}

function Overview() {
  const [o, setO] = useState(null)
  useEffect(() => { api('/api/audit/overview').then(setO) }, [])
  if (!o) return <Loading />
  return (
    <div className="today-grid">
      <section className="panel">
        <div className="panel-head"><h2>Chain integrity</h2><span className={`chip ${o.chain.ok ? 'ok' : 'bad'}`}>{o.chain.ok ? 'Verified' : 'Broken'}</span></div>
        <dl className="facts">
          <div><dt>Events on record</dt><dd>{o.events}</dd></div>
          <div><dt>First event</dt><dd>{(o.first_event_at || '').slice(0, 19).replace('T', ' ')}</dd></div>
          <div><dt>Head</dt><dd className="mono small">{(o.chain.head || '').slice(0, 26)}…</dd></div>
          <div><dt>Governed decisions</dt><dd>{o.decisions}</dd></div>
          <div><dt>Distinct actors</dt><dd>{o.actors}</dd></div>
          <div><dt>Events since last anchor</dt><dd className={o.events_since_anchor > 0 && !o.anchors.length ? 'bad-text' : ''}>{o.events_since_anchor}</dd></div>
        </dl>
        <div className="hero-actions">
          <a className="btn primary" href="#/audit/package">Anchor &amp; export</a>
          <a className="btn ghost" href="#/audit/lineage">Trace a contract</a>
        </div>
      </section>
      <section className="panel">
        <div className="panel-head"><h2>Needs an auditor’s eye</h2><a className="link" href="#/audit/exceptions">All {o.exceptions_total} →</a></div>
        {Object.keys(o.exception_counts).length === 0 ? <p className="empty">No exceptions. Every case was closed by a governed decision and precedent was followed.</p> : (
          <ul className="plain">{Object.entries(o.exception_counts).map(([k, n]) => <li key={k}><span>{k.replaceAll('_', ' ')}</span><b>{n}</b></li>)}</ul>
        )}
        <h3 className="sub">Anchors</h3>
        {o.anchors.length === 0 ? <p className="muted small">Never anchored. Anchor the chain and give the receipt to your auditor.</p> : (
          <ul className="plain">{o.anchors.map(a => <li key={a.anchor_id}><span>#{a.sequence} · {a.anchored_by}</span><span className="muted">{since(a.anchored_at)}</span></li>)}</ul>
        )}
      </section>
    </div>
  )
}

function Lineage({ contractId }) {
  const [q, setQ] = useState('')
  const [list, setList] = useState(null)
  const [l, setL] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api(`/api/audit/contracts?q=${encodeURIComponent(q)}`).then(setList) }, [q])
  useEffect(() => {
    setL(null); setErr('')
    if (contractId) api(`/api/audit/lineage/${contractId}`).then(setL).catch(e => setErr(e.message))
  }, [contractId])
  return (
    <div className="split-view">
      <div className="p-list">
        <input className="search" value={q} onChange={e => setQ(e.target.value)} placeholder="Find a contract…" />
        {(list?.contracts || []).slice(0, 60).map(c => (
          <a key={c.contract_id} href={`#/audit/lineage/${c.contract_id}`} className={`p-card ${c.contract_id === contractId ? 'on' : ''}`}>
            <div className="pattern-top">{c.flagged && <span className="tag amber">Needed judgment</span>}<span className="mono muted small">{c.contract_id}</span></div>
            <strong>{c.title}</strong>
          </a>
        ))}
      </div>
      <div>
        {!contractId && <div className="panel empty-state"><h2>Pick a contract</h2><p>See everything that happened to it, each step tied to its audit event.</p></div>}
        {err && <div className="callout bad">{err}</div>}
        {contractId && !l && !err && <Loading />}
        {l && <LineageView l={l} />}
      </div>
    </div>
  )
}

function LineageView({ l }) {
  const g = l.governing_decision
  const c = l.contract
  return (
    <article className="panel">
      <div className="pattern-top"><span className="tag slate">{c.venue}</span><span className="mono muted small">{c.contract_id}</span>
        <span className={`chip ${l.chain.ok ? 'ok' : 'bad'}`}>{l.chain.ok ? 'Chain verified' : 'Chain broken'}</span></div>
      <h2 className="lin-title">{c.title}</h2>
      {g ? (
        <div className="callout ok">
          <strong>Governed by {g.decision_id}: “{g.selection}”</strong>
          <span>{g.actor} · {(g.created_at || '').slice(0, 19).replace('T', ' ')} · precedent: {g.precedent_consistency?.status || '—'}{g.precedent_consistency?.distinguish ? ` (distinguished: ${g.precedent_consistency.distinguish})` : ''}{g.authoritative ? '' : ' · superseded'}</span>
          <span className="muted small">{g.rationale}</span>
        </div>
      ) : <div className="callout">No governed decision on this contract yet.</div>}
      <ol className="timeline">
        {l.events.map(e => (
          <li key={e.event_id} className={`st-${e.stage}`}>
            <span className="tl-stage">{STAGE_NAME[e.stage] || e.stage}</span>
            <div>
              <strong>{e.label}</strong>
              {e.summary && <p>{e.summary}</p>}
              <small className="muted">{e.actor} · {e.occurred_at.slice(0, 19).replace('T', ' ')} · <span className="mono">#{e.sequence} {e.event_hash.slice(7, 19)}</span></small>
            </div>
          </li>
        ))}
      </ol>
      <p className="fine">Lineage fingerprint <span className="mono">{l.lineage_hash}</span>, the hash of these {l.events.length} event hashes in order. Cite it in workpapers.</p>
    </article>
  )
}

function Log() {
  const [f, setF] = useState({ q: '', stage: '', actor: '' })
  const [d, setD] = useState(null)
  const [offset, setOffset] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ ...f, limit: 50, offset })
      api(`/api/audit/log?${p}`).then(setD)
    }, 200)
    return () => clearTimeout(t)
  }, [f, offset])
  const set = (k, v) => { setOffset(0); setF(x => ({ ...x, [k]: v })) }
  return (
    <section className="panel">
      <div className="filters">
        <input className="search" value={f.q} onChange={e => set('q', e.target.value)} placeholder="Search actions, actors, contracts, details…" />
        <select value={f.stage} onChange={e => set('stage', e.target.value)}>
          <option value="">All stages</option>
          {Object.entries(STAGE_NAME).map(([k, v]) => <option key={k} value={k}>{v} {d?.facets?.stages?.[k] ? `(${d.facets.stages[k]})` : ''}</option>)}
        </select>
        <select value={f.actor} onChange={e => set('actor', e.target.value)}>
          <option value="">All actors</option>
          {Object.keys(d?.facets?.actors || {}).sort().map(a => <option key={a}>{a}</option>)}
        </select>
      </div>
      {!d ? <Loading /> : (
        <>
          <table className="log">
            <thead><tr><th>#</th><th>When</th><th>Event</th><th>Actor</th><th>Object</th><th>Hash</th></tr></thead>
            <tbody>
              {d.events.map(e => (
                <tr key={e.event_id}>
                  <td className="mono">{e.sequence}</td>
                  <td>{e.occurred_at.slice(0, 19).replace('T', ' ')}</td>
                  <td><strong>{e.label}</strong>{e.summary && <small>{e.summary}</small>}</td>
                  <td className="mono small">{e.actor}</td>
                  <td className="mono small">{e.object_id}</td>
                  <td className="mono small">{e.event_hash.slice(7, 17)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pager">
            <span className="muted small">{d.total} events</span>
            <button className="btn ghost" disabled={offset === 0} onClick={() => setOffset(o => Math.max(0, o - 50))}>Newer</button>
            <button className="btn ghost" disabled={offset + 50 >= d.total} onClick={() => setOffset(o => o + 50)}>Older</button>
          </div>
        </>
      )}
    </section>
  )
}

function Exceptions() {
  const [d, setD] = useState(null)
  useEffect(() => { api('/api/audit/exceptions').then(setD) }, [])
  if (!d) return <Loading />
  return (
    <section className="panel">
      {d.items.length === 0 && <p className="empty">Nothing to flag: no departures, overrules, reversals, manual closures or self-approvals, and the chain verifies.</p>}
      {d.items.map((i, n) => (
        <div className={`exc sev-${i.severity}`} key={n}>
          <span className={`tag ${SEV[i.severity]}`}>{i.severity}</span>
          <div>
            <strong>{i.title}</strong>
            {i.detail && <p>{i.detail}</p>}
            <small className="muted">{i.kind.replaceAll('_', ' ')}{i.actor ? ` · ${i.actor}` : ''}{i.sequence ? ` · event #${i.sequence}` : ''}{i.occurred_at ? ` · ${since(i.occurred_at)}` : ''}</small>
          </div>
        </div>
      ))}
    </section>
  )
}

function Package() {
  const [note, setNote] = useState('')
  const [receipt, setReceipt] = useState(null)
  const [err, setErr] = useState('')
  async function anchor() {
    setErr('')
    try { setReceipt(await post('/api/audit/anchor', { note })) } catch (e) { setErr(e.message) }
  }
  const receiptText = receipt ? JSON.stringify(receipt, null, 2) : ''
  const [busy, setBusy] = useState(false)
  const [exported, setExported] = useState('')
  async function download() {
    setBusy(true)
    setErr('')
    try {
      const res = await fetch('/api/audit/package', { method: 'POST' })
      if (!res.ok) throw new Error(`${res.status} export failed`)
      const blob = await res.blob()
      const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'arbiter-audit-package.zip'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = name
      a.click()
      URL.revokeObjectURL(url)
      setExported(res.headers.get('X-Arbiter-Manifest-Hash') || 'done')
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="today-grid">
      <section className="panel">
        <div className="panel-head"><h2><span className="step-n">1</span>Anchor the chain</h2></div>
        <p className="muted">Records the current chain head as a receipt. Give the receipt to your auditor, or keep it anywhere outside Arbiter. Later it proves the record up to this point was never rebuilt.</p>
        <label className="field"><span>Note <em>optional</em></span><input value={note} onChange={e => setNote(e.target.value)} placeholder="e.g. Q3 close, sent to Acme LLP" /></label>
        <button className="btn primary" onClick={anchor}>Create receipt</button>
        {err && <div className="callout bad">{err}</div>}
        {receipt && (
          <div className="receipt">
            <div className="panel-head"><strong>Receipt · event #{receipt.sequence}</strong>
              <button className="link" onClick={() => navigator.clipboard?.writeText(receiptText).catch(() => {})}>Copy</button></div>
            <pre>{receiptText}</pre>
          </div>
        )}
      </section>
      <section className="panel">
        <div className="panel-head"><h2><span className="step-n">2</span>Export the evidence package</h2></div>
        <p className="muted">Every event, contract version, evidence record, decision and precedent, with hashes and a manifest. The export is itself recorded in the chain.</p>
        <button className="btn primary" onClick={download} disabled={busy}>{busy ? 'Building package…' : 'Download package (.zip)'}</button>
        {exported && <p className="muted small">Exported. Manifest <span className="mono">{exported.slice(0, 23)}…</span> is recorded in the chain.</p>}
        <h3 className="sub"><span className="step-n">3</span>Verify independently</h3>
        <p className="muted small">On the auditor’s machine, with their own copy of the verifier (Python standard library only):</p>
        <pre className="cmd">python3 verify.py arbiter-audit-package.zip --anchor receipt.json</pre>
        <p className="muted small">It recomputes every hash, checks each record is committed to by the chain, and checks your receipts. Format: <span className="mono">docs/audit/PACKAGE_SPEC.md</span>. Verifier: <span className="mono">tools/arbiter-verify/verify.py</span>.</p>
      </section>
    </div>
  )
}
