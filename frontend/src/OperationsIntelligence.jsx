import React from 'react'
import './operations-intelligence.css'

function money(n) {
  if (n === 0) return '$0'
  if (!n) return '—'
  return `$${(Number(n) / 1e6).toFixed(Number(n) >= 1e7 ? 0 : 1)}M`
}

function labelize(value) {
  return String(value || '—').replaceAll('_', ' ').replace(/\b\w/g, m => m.toUpperCase())
}

export default function OperationsIntelligence({ intelligence, onSelectCase }) {
  if (!intelligence) return null
  const summary = intelligence.summary || {}
  const clusters = (intelligence.clusters || []).filter(c => c.count >= 2).slice(0, 4)
  const sequence = (intelligence.recommended_sequence || []).slice(0, 5)

  return (
    <section className="ops-intel">
      <div className="ops-intel-head">
        <div>
          <span className="ops-intel-kicker">Arbiter Operations Intelligence</span>
          <h2>{summary.active_cases || 0} cases → {summary.distinct_work_patterns || 0} meaningful work patterns</h2>
          <p>Arbiter groups repeated blockers, separates ready work from external dependencies, and recommends the fastest path through the queue.</p>
        </div>
        <span className="ops-intel-boundary">Advisory only</span>
      </div>

      <div className="ops-intel-stats">
        <div><strong>{summary.ready_for_review ?? 0}</strong><span>Ready now</span></div>
        <div><strong>{summary.waiting_on_external_data ?? 0}</strong><span>Waiting on data</span></div>
        <div><strong>{summary.policy_interpretation ?? 0}</strong><span>Policy judgment</span></div>
        <div><strong>{summary.repeated_patterns ?? 0}</strong><span>Repeated patterns</span></div>
        <div><strong>{summary.compression_ratio || 1}×</strong><span>Queue compression</span></div>
      </div>

      <div className="ops-intel-grid">
        <div className="ops-intel-panel">
          <div className="ops-intel-panel-head"><span>Shared root causes</span><b>{clusters.length ? `${clusters.length} surfaced` : 'No repeats'}</b></div>
          {clusters.length ? clusters.map(cluster => (
            <button className="ops-cluster" key={cluster.cluster_id} onClick={() => cluster.case_ids?.[0] && onSelectCase?.(cluster.case_ids[0])}>
              <div>
                <strong>{cluster.count} cases · {labelize(cluster.blocker_type)}</strong>
                <span>{cluster.example_title || 'Repeated resolution pattern'}</span>
              </div>
              <div className="ops-cluster-meta">
                <b>{money(cluster.notional)}</b>
                <span>priority {cluster.max_priority_score}</span>
              </div>
            </button>
          )) : <p className="ops-intel-empty">No repeated root-cause pattern currently spans multiple cases.</p>}
        </div>

        <div className="ops-intel-panel">
          <div className="ops-intel-panel-head"><span>Recommended work sequence</span><b>Next actions</b></div>
          <ol className="ops-sequence">
            {sequence.map(step => (
              <li key={`${step.type}-${step.id}`}>
                <button onClick={() => step.type === 'case' && onSelectCase?.(step.id)}>
                  <span>{step.label}</span>
                  <small>{step.case_count > 1 ? `${step.case_count} cases` : '1 case'}{step.notional ? ` · ${money(step.notional)}` : ''}</small>
                </button>
              </li>
            ))}
            {!sequence.length && <p className="ops-intel-empty">No active recommended actions.</p>}
          </ol>
        </div>
      </div>
    </section>
  )
}
