import React from 'react'

const GROUPS = [
  {
    label: 'Operations',
    items: [
      ['overview', 'Overview', '⌂'],
      ['work', 'Work Queue', '◎'],
      ['cases', 'Cases', '▤'],
      ['resolution', 'Resolution Docket', '◇'],
      ['portfolio', 'Portfolio', '◫'],
    ],
  },
  {
    label: 'Assurance',
    items: [
      ['benchmark', 'Benchmark', '◉'],
      ['controls', 'Controls', '⌘'],
      ['validation', 'Validation', '✓'],
      ['policy', 'Policy', '≡'],
    ],
  },
]

export function ConsoleRail({ view, onViewChange, onRefresh }) {
  return (
    <aside className="console-rail">
      <div className="console-brand">
        <div className="console-mark">A</div>
        <div>
          <strong>Arbiter</strong>
          <span>Resolution infrastructure</span>
        </div>
      </div>

      <button className="console-primary" onClick={() => onViewChange('work')}>
        <span>◎</span>
        <span>Open work queue</span>
      </button>

      <nav className="console-nav" aria-label="Arbiter console">
        {GROUPS.map(group => (
          <div className="console-nav-group" key={group.label}>
            <div className="console-nav-label">{group.label}</div>
            {group.items.map(([key, label, icon]) => (
              <button
                key={key}
                className={`console-nav-item ${view === key ? 'active' : ''}`}
                onClick={() => onViewChange(key)}
              >
                <span className="console-nav-icon">{icon}</span>
                <span>{label}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="console-rail-footer">
        <button onClick={onRefresh}>↻ Refresh governed state</button>
        <div className="console-system-label">Governed decision boundary</div>
        <p>AI interprets. Policy governs.<br />Evidence proves. Logic resolves.</p>
      </div>
    </aside>
  )
}

export function ConsolePageHeader({ eyebrow, title, description, action, actionLabel = 'Ask Arbiter' }) {
  return (
    <header className="console-page-header">
      <div>
        <p className="console-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description && <p className="console-description">{description}</p>}
      </div>
      {action && (
        <button className="console-ai-button" onClick={action} title="Advisory interpretation only — governed resolution remains deterministic">
          <span className="console-ai-spark">✦</span>
          <span>{actionLabel}</span>
          <small>Advisory</small>
        </button>
      )}
    </header>
  )
}

export function ConsoleMetric({ value, label, tone = 'default' }) {
  return (
    <div className={`console-metric ${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  )
}
