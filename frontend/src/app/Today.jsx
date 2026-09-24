import React, { useEffect, useState } from 'react'
import { api, blocker, money, plural, since, splitTitle } from './api'
import { useDecisionOrder } from './hooks'

const ACTIVITY = {
  'decision.recorded': ['Decision recorded', 'ok'],
  'precedent.created': ['New precedent', 'violet'],
  'precedent.matched': ['Precedent matched a new contract', 'violet'],
  'precedent.distinguished': ['Precedent distinguished', 'amber'],
  'precedent.overruled': ['Precedent overruled', 'amber'],
  'precedent.superseded': ['Precedent superseded', 'amber'],
  'appeal.checked': ['Appeal checked', 'blue'],
  'evidence.exception.opened': ['New case from venue intake', 'blue'],
  'evidence.exception.reopened': ['Case reopened', 'amber'],
  'evidence.exception.retriaged': ['Case closed by re-triage', 'slate'],
  'decision.reevaluation.requested': ['Cases re-evaluated', 'ok'],
}

export default function Today({ overview, clusters, items, active, precedents, go }) {
  const [audit, setAudit] = useState(null)
  useEffect(() => {
    api('/api/audit?limit=60').then(setAudit).catch(() => setAudit(null))
  }, [overview])

  const ordered = useDecisionOrder(clusters, items)
  if (!overview) return <Loading />

  const h = overview.health || {}
  const att = overview.attention || {}
  const oi = overview.agent_brief?.operations_intelligence?.summary || {}
  const live = (precedents?.precedents || []).filter(p => p.state === 'active')
  const matched = live.reduce((n, p) => n + (p.matched_contracts || 0), 0)
  const fromVenues = active.filter(i => i.source === 'venue_intake').length
  const covered = ordered.filter(c => c.precedent).length
  const decisions = clusters.length
  const events = groupEvents((audit?.events || []).filter(e => ACTIVITY[e.action])).slice(0, 8)
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })

  return (
    <div className="today">
      <section className="hero">
        <span className="eyebrow">Resolution desk · {today}</span>
        {decisions ? (
          <h1>
            {plural(decisions, 'decision')} stand{decisions === 1 ? 's' : ''} between the queue and settlement.
          </h1>
        ) : (
          <h1>The queue is clear.</h1>
        )}
        <p className="lede">
          {plural(active.length, 'open case')} compress into {plural(decisions, 'work pattern')}.
          {covered > 0 && <> {covered} {covered === 1 ? 'is' : 'are'} already covered by precedent.</>} {money(h.resolution_risk_notional)} carries resolution risk and {money(h.held_notional)} is held before payout.
        </p>
        {ordered[0] && (
          <div className="hero-actions">
            <a className="btn primary" href={`#/decide/${ordered[0].cluster_id}`}>
              Start with the {ordered[0].precedent ? 'precedent-covered' : 'largest'} pattern →
            </a>
            <a className="btn ghost" href="#/queue">See the whole queue</a>
          </div>
        )}
      </section>

      <section className="flow" aria-label="How work moves through Arbiter">
        <FlowStep n="1" title="Intake" value={fromVenues} unit="flagged" caption="Live Kalshi & Polymarket markets that need a human judgment" href="#/queue" />
        <FlowStep n="2" title="Queue" value={`${active.length} → ${decisions}`} unit="cases → patterns" caption={`Shared root causes grouped. ${oi.human_decisions_avoided || 0} touches avoided.`} href="#/queue" />
        <FlowStep n="3" title="Decide" value={decisions} unit={decisions === 1 ? 'decision left' : 'decisions left'} caption={`One ruling clears a whole pattern. ${att.cleared_by_decision || 0} cases cleared so far.`} href="#/decide" hot />
        <FlowStep n="4" title="Precedent" value={live.length} unit={live.length === 1 ? 'ruling on record' : 'rulings on record'} caption={`Checked against every new contract. ${plural(matched, 'match', 'matches')} so far.`} href="#/precedents" last />
      </section>

      <div className="today-grid">
        <section className="panel">
          <div className="panel-head">
            <h2>Decide next</h2>
            <a className="link" href="#/queue">All {decisions} patterns →</a>
          </div>
          {ordered.length === 0 && <p className="empty">Nothing needs a human judgment right now.</p>}
          {ordered.slice(0, 4).map(c => (
            <PatternRow key={c.cluster_id} c={c} />
          ))}
        </section>

        <aside className="stack">
          <section className="panel">
            <div className="panel-head"><h2>Controls</h2></div>
            <dl className="facts">
              <div><dt>Audit chain</dt><dd><span className={`chip ${h.audit_chain_ok ? 'ok' : 'bad'}`}>{h.audit_chain_ok ? `Verified · ${audit?.chain?.events ?? '—'} events` : 'Broken'}</span></dd></div>
              <div><dt>Held before payout</dt><dd className={h.held_notional ? 'bad-text' : ''}>{money(h.held_notional)} <small>{plural(h.held_contracts || 0, 'contract')}</small></dd></div>
              <div><dt>Resolution-risk exposure</dt><dd>{money(h.resolution_risk_notional)} <small>of {money(h.total_notional)}</small></dd></div>
              <div><dt>Primary risk driver</dt><dd>{h.primary_risk_driver || '—'}</dd></div>
            </dl>
            <a className="link" href="#/controls">Controls &amp; audit log →</a>
          </section>

          <section className="panel">
            <div className="panel-head"><h2>Activity</h2></div>
            {events.length === 0 && <p className="empty">No activity yet.</p>}
            <ol className="feed">
              {events.map(g => {
                const [text, tone] = ACTIVITY[g.action]
                return (
                  <li key={g.first.event_id}>
                    <i className={`dot ${tone}`} />
                    <div>
                      <strong>{text}{g.count > 1 && <b className="times">×{g.count}</b>}</strong>
                      <span className="mono">{g.label}</span>
                    </div>
                    <time>{since(g.first.occurred_at)}</time>
                  </li>
                )
              })}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  )
}

// Collapse the same action on the same event ("7 new cases from
// KXG7LEADEROUT-27JAN20") into one line, in order of first appearance.
function groupEvents(events) {
  const out = []
  for (const e of events) {
    const d = e.details || {}
    const obj = String(d.contract_id || d.subject || e.object_id || '')
    const family = obj.includes('-') ? obj.slice(0, obj.lastIndexOf('-')) : obj
    const key = `${e.action}|${d.precedent_id || ''}|${family}`
    const seen = out.find(g => g.key === key)
    if (seen) {
      seen.count += 1
      continue
    }
    out.push({ key, action: e.action, first: e, count: 1, obj, family, precedent: d.precedent_id })
  }
  return out.map(g => ({
    ...g,
    label: `${g.precedent ? `${g.precedent} → ` : ''}${g.count > 1 ? `${g.family} · ${g.count} contracts` : g.obj}`,
  }))
}

function FlowStep({ n, title, value, unit, caption, href, hot, last }) {
  return (
    <a className={`flow-step ${hot ? 'hot' : ''}`} href={href}>
      <span className="flow-n">{n}</span>
      <span className="flow-title">{title}</span>
      <strong>{value}</strong>
      <span className="flow-unit">{unit}</span>
      <p>{caption}</p>
      {!last && <span className="flow-arrow" aria-hidden="true">→</span>}
    </a>
  )
}

export function PatternRow({ c, compact = false }) {
  const b = blocker(c.blocker_type)
  const { question } = splitTitle(c.example_title || c.cases?.[0]?.title)
  return (
    <a className={`pattern tone-${b.tone} ${compact ? 'compact' : ''}`} href={`#/decide/${c.cluster_id}`}>
      <span className="pattern-bar" />
      <div className="pattern-body">
        <div className="pattern-top">
          <span className={`tag ${b.tone}`}>{b.name}</span>
          {c.precedent && <span className="tag precedent">Precedent applies</span>}
          <span className="pattern-meta">{plural(c.count, 'case')}{c.notional ? ` · ${money(c.notional)}` : ''}</span>
        </div>
        <strong>{c.count > 1 ? `${question.replace(/\?$/, '')} + ${c.count - 1} more` : question}</strong>
        {!compact && <p>{c.precedent ? `Ruled before: “${c.precedent.selection}”` : c.why_human || c.root_cause}</p>}
      </div>
      <span className="pattern-cta">{c.precedent ? 'Follow →' : `${b.verb} →`}</span>
    </a>
  )
}

export function Loading() {
  return (
    <div className="loading">
      <span />
      <span />
      <span />
    </div>
  )
}
