import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, post } from './api'
import Today from './Today'
import Queue from './Queue'
import Decide from './Decide'
import Precedents from './Precedents'
import Audit from './Audit'
import { LegacyViews } from '../legacy/LegacyViews'

// Hash routes: #/today, #/queue, #/decide/<cluster>, #/precedents/<id>, #/markets ...
function parseHash() {
  const [page = 'today', ...rest] = window.location.hash.replace(/^#\/?/, '').split('/')
  return { page: page || 'today', arg: rest.length ? decodeURIComponent(rest.join('/')) : null }
}

export function go(page, arg) {
  window.location.hash = `/${page}${arg ? `/${encodeURIComponent(arg)}` : ''}`
}

const NAV = [
  {
    group: 'Operate',
    items: [
      { page: 'today', label: 'Today', icon: 'M3 12l9-8 9 8v8a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z' },
      { page: 'queue', label: 'Queue', icon: 'M4 6h16M4 12h16M4 18h10', count: 'cases' },
      { page: 'decide', label: 'Decide', icon: 'M12 4v16M8 20h8M5 7h14M5 7l-3 7a3 3 0 006 0zM19 7l-3 7a3 3 0 006 0z', count: 'patterns', tone: 'hot' },
      { page: 'precedents', label: 'Precedents', icon: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5', count: 'precedents' },
    ],
  },
  {
    group: 'Resolve',
    items: [
      { page: 'markets', label: 'Markets', legacy: 'markets', icon: 'M4 19V9M10 19V5M16 19v-7M22 19H2' },
      { page: 'cases', label: 'Contract review', legacy: 'cases', icon: 'M5 4h14v16H5zM9 8h6M9 12h6M9 16h3' },
    ],
  },
  {
    group: 'Audit',
    items: [
      { page: 'audit', label: 'Audit trail', icon: 'M9 12l2 2 4-4M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z' },
    ],
  },
  {
    group: 'Assure',
    items: [
      { page: 'portfolio', label: 'Portfolio', legacy: 'monitoring', icon: 'M12 3a9 9 0 109 9h-9z M14 3.5A9 9 0 0120.5 10H14z' },
      { page: 'benchmark', label: 'Benchmark', legacy: 'benchmark', icon: 'M4 20h16M7 16V9M12 16V5M17 16v-4' },
      { page: 'controls', label: 'Controls & audit', legacy: 'infrastructure', icon: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z' },
      { page: 'validation', label: 'Validation', legacy: 'validation', icon: 'M5 12l4 4 10-10' },
      { page: 'policy', label: 'Policy', legacy: 'policy', icon: 'M4 7h10M4 17h6M14 17h6M18 7h2M14 4v6M10 14v6' },
    ],
  },
]
const LEGACY = Object.fromEntries(NAV.flatMap(g => g.items).filter(i => i.legacy).map(i => [i.page, i.legacy]))
const TITLES = Object.fromEntries(NAV.flatMap(g => g.items).map(i => [i.page, i.label]))

function Icon({ d }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

export default function App() {
  const [route, setRoute] = useState(parseHash)
  const [overview, setOverview] = useState(null)
  const [queue, setQueue] = useState(null)
  const [precedents, setPrecedents] = useState(null)
  const [error, setError] = useState('')
  const [navOpen, setNavOpen] = useState(false)

  useEffect(() => {
    const onHash = () => {
      setRoute(parseHash())
      setNavOpen(false)
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const reload = useCallback(async () => {
    try {
      const [o, q, p] = await Promise.all([api('/api/overview'), api('/api/work-queue'), api('/api/precedents?include_inactive=true')])
      setOverview(o)
      setQueue(q)
      setPrecedents(p)
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const clusters = overview?.agent_brief?.operations_intelligence?.clusters || []
  const items = queue?.items || []
  const active = items.filter(i => i.status !== 'resolved')
  const livePrecedents = (precedents?.precedents || []).filter(p => p.state === 'active')
  const counts = { cases: active.length, patterns: clusters.length, precedents: livePrecedents.length }
  const ctx = { overview, queue, precedents, clusters, items, active, reload, go }

  const page = route.page
  let body
  if (page === 'today') body = <Today {...ctx} />
  else if (page === 'queue') body = <Queue {...ctx} mode={route.arg} />
  else if (page === 'decide') body = <Decide {...ctx} clusterId={route.arg} />
  else if (page === 'audit') body = <Audit arg={route.arg} />
  else if (page === 'precedents') body = <Precedents {...ctx} precedentId={route.arg} />
  else if (LEGACY[page]) body = <div className="legacy-frame"><LegacyViews view={LEGACY[page]} onNavigate={v => go(Object.keys(LEGACY).find(k => LEGACY[k] === v) || 'today')} /></div>
  else body = <Today {...ctx} />

  const audit = overview?.health?.audit_chain_ok

  return (
    <div className={`shell ${navOpen ? 'nav-open' : ''}`}>
      <aside className="side">
        <a className="brand" href="#/today">
          <span className="brand-mark" aria-hidden="true">A</span>
          <span>
            <strong>Arbiter</strong>
            <small>Market ops &amp; resolution</small>
          </span>
        </a>
        <nav>
          {NAV.map(g => (
            <div className="nav-group" key={g.group}>
              <span className="nav-label">{g.group}</span>
              {g.items.map(i => (
                <a key={i.page} href={`#/${i.page}`} className={`nav-item ${page === i.page ? 'active' : ''}`}>
                  <Icon d={i.icon} />
                  <span>{i.label}</span>
                  {i.count && counts[i.count] > 0 && <b className={`nav-count ${i.tone || ''}`}>{counts[i.count]}</b>}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <span className={`chip ${audit === false ? 'bad' : 'ok'}`}>{audit === false ? 'Audit chain broken' : 'Audit chain verified'}</span>
          <small>Humans decide. Arbiter remembers, checks and proves.</small>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="menu" onClick={() => setNavOpen(o => !o)} aria-label="Menu">
            <Icon d="M4 7h16M4 12h16M4 17h16" />
          </button>
          <span className="crumb">{TITLES[page] || 'Today'}</span>
          <AskBar />
          <button className="icon-btn" onClick={reload} title="Refresh" aria-label="Refresh">
            <Icon d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7" />
          </button>
        </header>
        {error && <div className="banner bad">Could not load governed state: {error}</div>}
        <main className="page" key={page}>
          {body}
        </main>
      </div>
      {navOpen && <div className="scrim" onClick={() => setNavOpen(false)} />}
    </div>
  )
}

export function AskBar() {
  const [q, setQ] = useState('')
  const [a, setA] = useState(null)
  const [busy, setBusy] = useState(false)
  const ref = useRef(null)
  const box = useRef(null)

  useEffect(() => {
    const onKey = e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        ref.current?.focus()
      }
      if (e.key === 'Escape') setA(null)
    }
    const onClick = e => {
      if (box.current && !box.current.contains(e.target)) setA(null)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onClick)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onClick)
    }
  }, [])

  async function ask(e) {
    e.preventDefault()
    if (!q.trim()) return
    setBusy(true)
    try {
      setA(await post('/api/ask', { question: q }))
    } catch (err) {
      setA({ answer: err.message, citations: [] })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="askbar" ref={box}>
      <form onSubmit={ask}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        <input ref={ref} value={q} onChange={e => setQ(e.target.value)} placeholder="Ask Arbiter about past rulings…" aria-label="Ask Arbiter" />
        <kbd>⌘K</kbd>
        <button disabled={busy || !q.trim()}>{busy ? '…' : 'Ask'}</button>
      </form>
      {a && <AskAnswer a={a} onClose={() => setA(null)} />}
    </div>
  )
}

export function AskAnswer({ a, onClose, inline = false }) {
  return (
    <div className={`answer ${inline ? 'inline' : 'pop'} ${a.grounded ? '' : 'ungrounded'}`}>
      <div className="answer-head">
        <span className={`chip ${a.grounded ? 'ok' : ''}`}>{a.grounded ? `Grounded in ${a.citations.length} precedent${a.citations.length === 1 ? '' : 's'}` : 'Not covered yet'}</span>
        {onClose && <button className="link" onClick={onClose}>Close</button>}
      </div>
      <p>{a.answer}</p>
      {(a.citations || []).map(c => (
        <a className="cite" key={c.precedent_id} href={`#/precedents/${c.precedent_id}`} onClick={onClose}>
          <b className="mono">{c.precedent_id}</b>
          <span>“{c.selection}”</span>
          <small>{c.why} · {c.contract_count} decided{c.matched_contracts ? ` · applied to ${c.matched_contracts} since` : ''}</small>
        </a>
      ))}
      <small className="method">{a.method}</small>
    </div>
  )
}
