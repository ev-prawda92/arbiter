import React, { useMemo, useState } from 'react'
import { blocker, money, plural, splitTitle } from './api'
import { useDecisionOrder } from './hooks'
import { Loading } from './Today'
import { LegacyViews } from '../legacy/LegacyViews'

export default function Queue({ overview, clusters, items, active, mode }) {
  const [filter, setFilter] = useState('all')
  const [open, setOpen] = useState(null)
  const ordered = useDecisionOrder(clusters, items)

  const families = useMemo(() => {
    const m = {}
    for (const c of ordered) m[c.blocker_type] = (m[c.blocker_type] || 0) + 1
    return Object.entries(m).sort((a, b) => b[1] - a[1])
  }, [ordered])

  if (!overview) return <Loading />
  const shown = ordered.filter(c => filter === 'all' || (filter === 'precedent' ? c.precedent : c.blocker_type === filter))
  const covered = ordered.filter(c => c.precedent).length

  return (
    <div className="queue">
      <header className="page-head">
        <div>
          <span className="eyebrow">Queue</span>
          <h1>{plural(active.length, 'open case')}, {plural(ordered.length, 'decision')}.</h1>
          <p className="lede">Cases that share a root cause are grouped, so one governed ruling answers all of them. Open a pattern to decide it.</p>
        </div>
        <div className="seg" role="tablist">
          <a role="tab" className={mode !== 'cases' ? 'on' : ''} href="#/queue">By pattern</a>
          <a role="tab" className={mode === 'cases' ? 'on' : ''} href="#/queue/cases">Every case</a>
        </div>
      </header>

      {mode === 'cases' ? (
        <div className="legacy-frame flush">
          <LegacyViews view="work" />
        </div>
      ) : (
        <>
          <div className="filters" role="toolbar" aria-label="Filter patterns">
            <button className={filter === 'all' ? 'on' : ''} onClick={() => setFilter('all')}>All <b>{ordered.length}</b></button>
            {covered > 0 && <button className={`precedent ${filter === 'precedent' ? 'on' : ''}`} onClick={() => setFilter('precedent')}>Precedent applies <b>{covered}</b></button>}
            {families.map(([t, n]) => (
              <button key={t} className={filter === t ? 'on' : ''} onClick={() => setFilter(t)}>
                <i className={`dot ${blocker(t).tone}`} />{blocker(t).name} <b>{n}</b>
              </button>
            ))}
          </div>

          <div className="table">
            <div className="thead">
              <span>Pattern</span>
              <span>Cases</span>
              <span>Exposure</span>
              <span>State</span>
              <span />
            </div>
            {shown.map(c => {
              const b = blocker(c.blocker_type)
              const { question } = splitTitle(c.example_title)
              const isOpen = open === c.cluster_id
              return (
                <div className={`trow tone-${b.tone} ${isOpen ? 'open' : ''}`} key={c.cluster_id}>
                  <button className="trow-main" onClick={() => setOpen(isOpen ? null : c.cluster_id)} aria-expanded={isOpen}>
                    <span className="cell-pattern">
                      <span className="pattern-top">
                        <span className={`tag ${b.tone}`}>{b.name}</span>
                        {c.precedent && <span className="tag precedent">Precedent applies</span>}
                      </span>
                      <strong>{question}</strong>
                      <small>{c.root_cause}</small>
                    </span>
                    <span className="cell-num">{c.count}</span>
                    <span className="cell-num">{c.notional ? money(c.notional) : '—'}</span>
                    <span><span className="state">{String(c.dominant_state || '').replaceAll('_', ' ').toLowerCase()}</span></span>
                    <span className="chev" aria-hidden="true">{isOpen ? '−' : '+'}</span>
                  </button>
                  {isOpen && (
                    <div className="trow-detail">
                      {c.precedent && (
                        <div className="callout precedent">
                          <strong>{c.precedent.tier === 'same_clause' ? 'The same clause was ruled on before.' : 'A ruling on the same template exists.'}</strong>
                          <span>“{c.precedent.selection}” · <span className="mono">{c.precedent.precedent_id}</span></span>
                        </div>
                      )}
                      <ul className="cases">
                        {c.cases.map(i => {
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
                      <div className="trow-actions">
                        <p>{c.why_human}</p>
                        <a className="btn primary" href={`#/decide/${c.cluster_id}`}>{c.precedent ? 'Review and follow precedent' : `Decide ${c.count > 1 ? `all ${c.count}` : 'this case'}`} →</a>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
            {shown.length === 0 && <p className="empty">No patterns match this filter.</p>}
          </div>
        </>
      )}
    </div>
  )
}
