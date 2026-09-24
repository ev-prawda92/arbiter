import { useMemo } from 'react'

export function useDecisionOrder(clusters, items) {
  // Patterns with an applicable precedent first (fastest to clear), then by size and money.
  return useMemo(() => {
    const byId = Object.fromEntries((items || []).map(i => [i.id, i]))
    return [...(clusters || [])]
      .map(c => {
        const cases = (c.case_ids || []).map(id => byId[id]).filter(Boolean)
        const precedent = cases.find(i => i.precedent)?.precedent || null
        return { ...c, cases, precedent }
      })
      .sort((a, b) => (b.precedent ? 1 : 0) - (a.precedent ? 1 : 0) || b.count - a.count || b.notional - a.notional)
  }, [clusters, items])
}
