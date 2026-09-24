import React, { useEffect, useState } from 'react'
import { api, post, since } from './api'
import { Loading } from './Today'

const TABS = [
  ['overview', 'Overview'],
  ['lineage', 'Lineage'],
  ['log', 'Audit log'],
  ['exceptions', 'Exceptions'],
  ['engagements', 'Engagements'],
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
      {tab === 'engagements' && (sub ? <Engagement id={sub} /> : <EngagementList />)}
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

const RESULT = { no_exception: ['No exception', 'ok'], exception: ['Exception', 'red'], not_testable: ['Not testable', 'slate'] }

function EngagementList() {
  const [d, setD] = useState(null)
  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({ name: '', period_from: `${today.slice(0, 4)}-01-01`, period_to: today, auditor_public_key: '' })
  const [err, setErr] = useState('')
  const load = () => api('/api/audit/engagements').then(setD)
  useEffect(() => { load() }, [])
  async function open(e) {
    e.preventDefault()
    setErr('')
    try {
      const s = await post('/api/audit/engagements', form)
      window.location.hash = `/audit/engagements/${s.engagement_id}`
    } catch (x) { setErr(x.message) }
  }
  return (
    <div className="today-grid">
      <section className="panel">
        <div className="panel-head"><h2>Engagements</h2></div>
        {!d ? <Loading /> : d.engagements.length === 0 ? <p className="empty">No engagements yet. Open one to sample, test and sign off a period.</p> : d.engagements.map(e => (
          <a key={e.engagement_id} className="p-card" href={`#/audit/engagements/${e.engagement_id}`}>
            <div className="pattern-top"><span className={`tag ${e.state === 'signed' ? 'ok' : 'amber'}`}>{e.state}</span><span className="muted small">{e.period_from} → {e.period_to}</span></div>
            <strong>{e.name}</strong>
            <small>{e.auditor} · {e.progress.tested}/{e.progress.sampled} tested · {e.findings} finding{e.findings === 1 ? '' : 's'}</small>
          </a>
        ))}
      </section>
      <section className="panel">
        <div className="panel-head"><h2>Open an engagement</h2></div>
        <p className="muted small">Only you can change it. Every step is recorded in its own hash chain, committed to Arbiter’s record.</p>
        <form onSubmit={open}>
          <label className="field"><span>Name</span><input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Q3 resolution controls review" /></label>
          <div className="two-col">
            <label className="field"><span>Period from</span><input type="date" value={form.period_from} onChange={e => setForm({ ...form, period_from: e.target.value })} /></label>
            <label className="field"><span>Period to</span><input type="date" value={form.period_to} onChange={e => setForm({ ...form, period_to: e.target.value })} /></label>
          </div>
          <label className="field"><span>Your public key</span><input className="mono" value={form.auditor_public_key} onChange={e => setForm({ ...form, auditor_public_key: e.target.value.trim() })} placeholder="64 hex characters" /></label>
          <p className="muted small">Generate a key on your own machine. The secret never leaves it, and sign-off needs its signature, so nobody else (the exchange included) can sign your report.</p>
          <pre className="cmd">python3 tools/arbiter-verify/sign.py keygen auditor.key</pre>
          <button className="btn primary" disabled={!form.name.trim() || form.auditor_public_key.length !== 64}>Open engagement</button>
        </form>
        {err && <div className="callout bad">{err}</div>}
      </section>
    </div>
  )
}

function Engagement({ id }) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  const [pop, setPop] = useState({ population: 'decisions', size: 25 })
  const [notes, setNotes] = useState({})
  const [fnd, setFnd] = useState({ title: '', severity: 'medium', description: '', item_ids: [] })
  const [opinion, setOpinion] = useState('')
  const [draft, setDraft] = useState(null)
  const [signature, setSignature] = useState('')
  async function prepare() {
    setErr('')
    try { setDraft(await post(`/api/audit/engagements/${id}/prepare`, { opinion })) } catch (e) { setErr(e.message) }
  }
  async function signOff() {
    await run('sign', { opinion, report_hash: draft.report.report_hash, signature })
    setDraft(null)
  }
  const load = () => api(`/api/audit/engagements/${id}`).then(setS).catch(e => setErr(e.message))
  useEffect(() => { load() }, [id])
  async function run(path, body) {
    setErr('')
    try { await post(`/api/audit/engagements/${id}/${path}`, body); await load() } catch (e) { setErr(e.message) }
  }
  if (!s) return err ? <div className="callout bad">{err}</div> : <Loading />
  const locked = s.state === 'signed'
  const items = s.sample?.items || []
  const pv = s.preview || {}
  return (
    <div className="engagement">
      <section className="panel">
        <div className="pattern-top">
          <span className={`tag ${locked ? 'ok' : 'amber'}`}>{s.state}</span>
          <span className="muted small">{s.auditor} · {s.period_from} → {s.period_to}</span>
          <span className={`chip ${s.log_verified?.ok ? 'ok' : 'bad'}`}>{s.log_verified?.ok ? `Working papers verified · ${s.log_entries} entries` : 'Working papers do not verify'}</span>
        </div>
        <h2 className="lin-title">{s.name}</h2>
        <div className="outcome-grid">
          <div><small>Decisions in period</small><strong>{pv.decisions ?? '—'}</strong><span>{(pv.deciders || []).length} decider(s)</span></div>
          <div><small>Followed precedent</small><strong>{pv.followed_when_precedent_applied == null ? '—' : `${Math.round(pv.followed_when_precedent_applied * 100)}%`}</strong><span>when one applied</span></div>
          <div><small>Departures · overrules</small><strong>{pv.departures ?? 0} · {pv.overrules ?? 0}</strong><span>each needs a reason</span></div>
          <div><small>Manual closes</small><strong>{pv.manual_closes ?? 0}</strong><span>without a ruling</span></div>
        </div>
      </section>
      {err && <div className="callout bad">{err}</div>}

      <section className="panel">
        <div className="panel-head"><h2><span className="step-n">1</span>Sample</h2>
          {s.sample && <span className="muted small">{s.sample.size} of {s.sample.population_size} · seed <span className="mono">{s.sample.seed.slice(0, 12)}…</span></span>}</div>
        {!locked && !s.sample && (
          <div className="filters">
            <select value={pop.population} onChange={e => setPop({ ...pop, population: e.target.value })}>
              <option value="decisions">Governed decisions</option>
              <option value="departures">Departures from precedent</option>
              <option value="manual_closes">Manual closes</option>
            </select>
            <input className="search narrow" type="number" min="1" value={pop.size} onChange={e => setPop({ ...pop, size: Number(e.target.value) })} />
            <button className="btn" onClick={() => run('sample', pop)}>Draw sample (once)</button>
          </div>
        )}
        <p className="fine">Reproducible: items are ranked by sha256(seed | id), and the seed derives from this engagement and the chain head at the moment of sampling. Anyone with the evidence package can recompute it.</p>
        {items.map(i => {
          const t = s.tests[i.item_id]
          return (
            <div className="sample-item" key={i.item_id}>
              <div className="si-head">
                <span className="mono small">{i.item_id}</span>
                <strong>{i.label}</strong>
                <span className="muted small">{i.actor} · {(i.at || '').slice(0, 10)}</span>
                {t && <span className={`tag ${RESULT[t.result][1]}`}>{RESULT[t.result][0]}</span>}
              </div>
              {t?.checks && <ul className="checks">{t.checks.map(c => <li key={c.check} className={c.ok ? 'ok' : 'bad'}>{c.ok ? '✓' : '✗'} {c.check}</li>)}</ul>}
              {t?.note && <p className="muted small">Note: {t.note}</p>}
              {!locked && (
                <div className="si-actions">
                  <input value={notes[i.item_id] || ''} onChange={e => setNotes({ ...notes, [i.item_id]: e.target.value })} placeholder="Working-paper note" />
                  {Object.entries(RESULT).map(([k, [label]]) => (
                    <button key={k} className={`btn ${t?.result === k ? 'primary' : 'ghost'}`} onClick={() => run('test', { item_id: i.item_id, result: k, note: notes[i.item_id] || '' })}>{label}</button>
                  ))}
                  <a className="link small" href={`#/audit/log`}>Log</a>
                </div>
              )}
            </div>
          )
        })}
      </section>

      <section className="panel">
        <div className="panel-head"><h2><span className="step-n">2</span>Findings</h2><span className="muted small">{s.findings.length}</span></div>
        {s.findings.map(f => (
          <div className="exc" key={f.finding_id}><span className={`tag ${f.severity === 'high' ? 'red' : f.severity === 'medium' ? 'amber' : 'slate'}`}>{f.severity}</span>
            <div><strong>{f.title}</strong><p>{f.description}</p><small className="muted">{f.item_ids.join(', ')}</small></div></div>
        ))}
        {!locked && (
          <div className="finding-form">
            <label className="field"><span>Title</span><input value={fnd.title} onChange={e => setFnd({ ...fnd, title: e.target.value })} /></label>
            <label className="field"><span>Description</span><textarea value={fnd.description} onChange={e => setFnd({ ...fnd, description: e.target.value })} /></label>
            <div className="filters">
              <select value={fnd.severity} onChange={e => setFnd({ ...fnd, severity: e.target.value })}><option>high</option><option>medium</option><option>low</option></select>
              <button className="btn" disabled={!fnd.title.trim()} onClick={() => run('findings', { ...fnd, item_ids: items.filter(i => s.tests[i.item_id]?.result === 'exception').map(i => i.item_id) }).then(() => setFnd({ title: '', severity: 'medium', description: '', item_ids: [] }))}>Record finding (linked to exceptions)</button>
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head"><h2><span className="step-n">3</span>Sign off</h2><span className="muted small">{s.progress.tested}/{s.progress.sampled} tested</span></div>
        {locked ? <Report report={s.report} signedAt={s.signed_at} signature={s.signature} /> : (
          <>
            <label className="field"><span>Opinion</span><textarea value={opinion} onChange={e => { setOpinion(e.target.value); setDraft(null) }} placeholder="e.g. Resolution controls operated effectively for the period, except as noted in the findings." /></label>
            {!draft ? (
              <button className="btn primary" disabled={!opinion.trim() || s.progress.tested < s.progress.sampled} onClick={prepare}>Prepare report to sign</button>
            ) : (
              <div className="receipt">
                <p className="muted small">Sign this exact report on your machine, then paste the signature.</p>
                <pre className="cmd">python3 tools/arbiter-verify/sign.py sign auditor.key {draft.report.report_hash}</pre>
                <label className="field"><span>Signature</span><input className="mono" value={signature} onChange={e => setSignature(e.target.value.trim())} placeholder="128 hex characters" /></label>
                <button className="btn primary big" disabled={signature.length !== 128} onClick={signOff}>Sign off and lock</button>
              </div>
            )}
            <p className="fine">Signing locks the engagement. The report is checked by the standalone verifier against the evidence package and your public key.</p>
          </>
        )}
      </section>
    </div>
  )
}

function Report({ report, signedAt, signature }) {
  const text = JSON.stringify(report, null, 2)
  function save() {
    const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `arbiter-audit-report-${report.engagement_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div className="report">
      <div className="callout ok"><strong>Signed {(signedAt || '').slice(0, 19).replace('T', ' ')} by {report.auditor}</strong><span>{report.opinion}</span></div>
      <dl className="facts">
        <div><dt>Results</dt><dd>{Object.entries(report.results).map(([k, n]) => `${n} ${RESULT[k]?.[0].toLowerCase()}`).join(' · ')}</dd></div>
        <div><dt>Findings</dt><dd>{report.findings.length}</dd></div>
        <div><dt>Attests to chain head</dt><dd className="mono small">#{report.chain.sequence} {report.chain.event_hash.slice(7, 19)}</dd></div>
        <div><dt>Report hash</dt><dd className="mono small">{report.report_hash.slice(0, 26)}…</dd></div>
        <div><dt>Auditor key</dt><dd className="mono small">{report.auditor_public_key.slice(0, 16)}…</dd></div>
        <div><dt>Signature</dt><dd className="mono small">{(signature || '').slice(0, 16)}…</dd></div>
      </dl>
      <div className="hero-actions"><button className="btn primary" onClick={save}>Download report (.json)</button></div>
      <pre className="cmd">python3 verify.py arbiter-audit-package.zip --report {`arbiter-audit-report-${report.engagement_id}.json`} --auditor-key {report.auditor_public_key}</pre>
    </div>
  )
}
