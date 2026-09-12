/* Arbiter v0.31 governed page actions.
 *
 * Adds page-level interactivity to the console without weakening the governed
 * boundary. Read-only pages get drill-down, refresh, export, and Ask Arbiter.
 * Pages with existing governed write APIs get explicit create/run/advance actions.
 */

(() => {
  const page = { title: '', observer: null }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    })
    let payload = {}
    try { payload = await response.json() } catch {}
    if (!response.ok) {
      const detail = payload?.detail
      throw new Error(typeof detail === 'string' ? detail : `${path} returned ${response.status}`)
    }
    return payload
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[ch]))
  }

  function toast(message, tone = 'neutral') {
    let host = document.getElementById('arbiter-governed-toast-host')
    if (!host) {
      host = document.createElement('div')
      host.id = 'arbiter-governed-toast-host'
      document.body.appendChild(host)
    }
    const el = document.createElement('div')
    el.className = `arbiter-governed-toast ${tone}`
    el.textContent = message
    host.appendChild(el)
    setTimeout(() => el.remove(), 3200)
  }

  function openModal({ eyebrow = 'Governed action', title, body = '', footer = '' }) {
    closeModal()
    const backdrop = document.createElement('div')
    backdrop.id = 'arbiter-governed-modal'
    backdrop.className = 'arbiter-governed-modal-backdrop'
    backdrop.innerHTML = `
      <section class="arbiter-governed-modal">
        <header><div><span>${esc(eyebrow)}</span><h2>${esc(title)}</h2></div><button type="button" data-close aria-label="Close">×</button></header>
        <div class="arbiter-governed-modal-body">${body}</div>
        ${footer ? `<footer>${footer}</footer>` : ''}
      </section>`
    document.body.appendChild(backdrop)
    backdrop.addEventListener('click', event => { if (event.target === backdrop) closeModal() })
    backdrop.querySelector('[data-close]')?.addEventListener('click', closeModal)
    return backdrop.querySelector('.arbiter-governed-modal')
  }

  function closeModal() {
    document.getElementById('arbiter-governed-modal')?.remove()
  }

  function downloadJson(filename, value) {
    const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function clickAsk(prefill = '') {
    const button = [...document.querySelectorAll('button')].find(el => el.textContent?.includes('Ask Arbiter'))
    button?.click()
    if (prefill) {
      let tries = 0
      const timer = setInterval(() => {
        const input = document.querySelector('#arbiter-ask-input')
        if (input) {
          input.value = prefill
          input.focus()
          clearInterval(timer)
        } else if (++tries > 10) clearInterval(timer)
      }, 80)
    }
  }

  const pageEndpoints = {
    'Executive overview': ['/api/overview'],
    'Resolution operations': ['/api/work-queue', '/api/overview'],
    'Case registry': ['/api/cases', '/api/templates'],
    'Resolution docket': ['/api/markets'],
    'Portfolio intelligence': ['/api/portfolio', '/api/executive'],
    'Benchmark assurance': ['/api/benchmark', '/api/real-benchmark'],
    'Controls & authorities': ['/api/infrastructure', '/api/authorities', '/api/audit?limit=50'],
    'Validation lab': ['/api/deployment/posture', '/api/resilience-lab/posture', '/api/external-assurance/posture', '/api/shadow-pilots/posture', '/api/reference-exchange'],
    'Policy governance': ['/api/policy', '/api/policy/drafts'],
  }

  async function exportCurrentPage(title) {
    const endpoints = pageEndpoints[title] || []
    const result = {}
    for (const endpoint of endpoints) {
      try { result[endpoint] = await api(endpoint) } catch (err) { result[endpoint] = { error: err.message } }
    }
    downloadJson(`arbiter-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.json`, result)
    toast('Snapshot exported.', 'good')
  }

  function installToolbar(title) {
    const main = document.querySelector('.console-main')
    const header = main?.querySelector('.console-page-header') || main?.querySelector('header')
    if (!main || !header) return
    let bar = main.querySelector('.arbiter-page-actions')
    if (!bar) {
      bar = document.createElement('div')
      bar.className = 'arbiter-page-actions'
      header.insertAdjacentElement('afterend', bar)
    }

    const specific = []
    if (title === 'Case registry') specific.push('<button type="button" data-page-action="new-case" class="primary">+ New case</button>')
    if (title === 'Benchmark assurance') specific.push('<button type="button" data-page-action="run-benchmark" class="primary">Run benchmark</button>')
    if (title === 'Policy governance') specific.push('<button type="button" data-page-action="new-policy-draft" class="primary">+ New policy draft</button>')
    if (title === 'Resolution docket') specific.push('<button type="button" data-page-action="filter-docket">Search docket</button>')

    bar.innerHTML = `
      <div><strong>Operator tools</strong><span>Interactive where governance allows; binding state remains protected.</span></div>
      <div class="arbiter-page-action-buttons">
        ${specific.join('')}
        <button type="button" data-page-action="ask">Ask Arbiter about this page</button>
        <button type="button" data-page-action="export">Export snapshot</button>
        <button type="button" data-page-action="refresh">Refresh</button>
      </div>`

    bar.querySelector('[data-page-action="refresh"]')?.addEventListener('click', () => window.location.reload())
    bar.querySelector('[data-page-action="export"]')?.addEventListener('click', () => exportCurrentPage(title))
    bar.querySelector('[data-page-action="ask"]')?.addEventListener('click', () => clickAsk(`Summarize the ${title} page and tell me what needs attention next.`))
    bar.querySelector('[data-page-action="new-case"]')?.addEventListener('click', openNewCase)
    bar.querySelector('[data-page-action="run-benchmark"]')?.addEventListener('click', runBenchmark)
    bar.querySelector('[data-page-action="new-policy-draft"]')?.addEventListener('click', openPolicyDraft)
    bar.querySelector('[data-page-action="filter-docket"]')?.addEventListener('click', installDocketFilter)
  }

  function openNewCase() {
    const modal = openModal({
      eyebrow: 'Case registry',
      title: 'Create governed analysis case',
      body: `
        <form id="arbiter-new-case-form" class="arbiter-governed-form">
          <label><span>Market / contract question</span><input name="question" required placeholder="Will the governed condition be satisfied?" /></label>
          <label><span>Resolution criteria</span><textarea name="criteria" rows="8" required placeholder="Paste the governing rules or criteria…"></textarea></label>
          <label class="check"><input type="checkbox" name="use_llm" /><span>Also request model triage (advisory only)</span></label>
          <div class="arbiter-governed-boundary">Creating a case analyzes and stores the contract record. It does not authorize settlement or alter evidence.</div>
          <button type="submit" class="primary">Create case</button>
        </form>`
    })
    modal.querySelector('#arbiter-new-case-form')?.addEventListener('submit', async event => {
      event.preventDefault()
      const fd = new FormData(event.currentTarget)
      const payload = {
        question: String(fd.get('question') || '').trim(),
        criteria: String(fd.get('criteria') || '').trim(),
        use_llm: fd.get('use_llm') === 'on',
        exchange_profile: 'generic',
        actor: 'operator:console',
      }
      try {
        await api('/api/analyze', { method: 'POST', body: JSON.stringify(payload) })
        toast('Case created and stored.', 'good')
        closeModal()
        setTimeout(() => window.location.reload(), 250)
      } catch (err) { toast(err.message, 'bad') }
    })
  }

  async function runBenchmark() {
    if (!window.confirm('Run the development benchmark now? This does not change settlement state.')) return
    try {
      const result = await api('/api/benchmark/run', { method: 'POST' })
      toast(`Benchmark completed${result?.benchmark ? `: ${result.benchmark}` : ''}.`, 'good')
      setTimeout(() => window.location.reload(), 300)
    } catch (err) { toast(err.message, 'bad') }
  }

  async function openPolicyDraft() {
    let current = {}
    try { current = await api('/api/policy') } catch {}
    const weights = current?.weights || {}
    const thresholds = current?.thresholds || {}
    const modal = openModal({
      eyebrow: 'Policy governance',
      title: 'Create policy draft',
      body: `
        <form id="arbiter-policy-draft-form" class="arbiter-governed-form">
          <label><span>Weights JSON</span><textarea name="weights" rows="6">${esc(JSON.stringify(weights, null, 2))}</textarea></label>
          <label><span>Thresholds JSON</span><textarea name="thresholds" rows="6">${esc(JSON.stringify(thresholds, null, 2))}</textarea></label>
          <label><span>Change note</span><textarea name="note" rows="3" required placeholder="Why is this policy change being proposed?"></textarea></label>
          <div class="arbiter-governed-boundary">This creates a draft only. Activation still requires the governed review / approval workflow.</div>
          <button type="submit" class="primary">Create draft</button>
        </form>`
    })
    modal.querySelector('#arbiter-policy-draft-form')?.addEventListener('submit', async event => {
      event.preventDefault()
      const fd = new FormData(event.currentTarget)
      try {
        const payload = {
          weights: JSON.parse(String(fd.get('weights') || '{}')),
          thresholds: JSON.parse(String(fd.get('thresholds') || '{}')),
          actor: 'operator:console',
          note: String(fd.get('note') || '').trim(),
        }
        await api('/api/policy/drafts', { method: 'POST', body: JSON.stringify(payload) })
        toast('Policy draft created.', 'good')
        closeModal()
        setTimeout(() => window.location.reload(), 250)
      } catch (err) { toast(err.message, 'bad') }
    })
  }

  function installDocketFilter() {
    const table = document.querySelector('.resolution-table') || document.querySelector('.console-table')
    if (!table || document.getElementById('arbiter-docket-filter')) return
    const wrap = document.createElement('div')
    wrap.id = 'arbiter-docket-filter'
    wrap.className = 'arbiter-inline-filter'
    wrap.innerHTML = '<input placeholder="Filter contracts by title, ticker, category…" /><button type="button">Clear</button>'
    table.parentElement?.insertAdjacentElement('beforebegin', wrap)
    const input = wrap.querySelector('input')
    const apply = () => {
      const q = input.value.toLowerCase().trim()
      table.querySelectorAll('tbody tr').forEach(row => { row.style.display = !q || row.textContent.toLowerCase().includes(q) ? '' : 'none' })
    }
    input.addEventListener('input', apply)
    wrap.querySelector('button').addEventListener('click', () => { input.value = ''; apply(); input.focus() })
    input.focus()
  }

  function installCaseRows() {
    if (page.title !== 'Case registry') return
    const card = [...document.querySelectorAll('.console-card')].find(el => el.textContent?.includes('Cases ·'))
    card?.querySelectorAll('.console-list-row').forEach(row => {
      if (row.dataset.arbiterInteractive) return
      row.dataset.arbiterInteractive = '1'
      row.classList.add('arbiter-clickable-row')
      row.addEventListener('click', async () => {
        const span = row.querySelector('span')?.textContent || ''
        const caseId = span.split('·')[0].trim()
        if (!caseId) return
        const modal = openModal({ eyebrow: 'Case workspace', title: row.querySelector('strong')?.textContent || caseId, body: '<div class="arbiter-governed-loading">Loading case…</div>' })
        try {
          const result = await api(`/api/cases/${encodeURIComponent(caseId)}`)
          const c = result.case || result
          modal.querySelector('.arbiter-governed-modal-body').innerHTML = `
            <div class="arbiter-detail-grid">
              <div><span>Case ID</span><strong>${esc(caseId)}</strong></div>
              <div><span>Compiler state</span><strong>${esc(c.compiler_status || c.latest_run?.compilation?.status || c.status || '—')}</strong></div>
            </div>
            <h3>Resolution criteria</h3><pre>${esc(c.criteria || 'No criteria text available.')}</pre>
            <h3>Latest governed record</h3><details><summary>View full record</summary><pre>${esc(JSON.stringify(c, null, 2))}</pre></details>
            <div class="arbiter-modal-actions"><button type="button" class="primary" data-case-ask>Ask Arbiter about this case</button></div>`
          modal.querySelector('[data-case-ask]')?.addEventListener('click', () => { closeModal(); clickAsk(`Explain case ${caseId}, its current blockers, and the next governed action.`) })
        } catch (err) { modal.querySelector('.arbiter-governed-modal-body').innerHTML = `<p>${esc(err.message)}</p>` }
      })
    })
  }

  function installDocketRows() {
    if (page.title !== 'Resolution docket') return
    document.querySelectorAll('.resolution-table tbody tr').forEach(row => {
      if (row.dataset.arbiterInteractive) return
      row.dataset.arbiterInteractive = '1'
      row.classList.add('arbiter-clickable-row')
      row.addEventListener('click', async () => {
        const ticker = row.querySelector('td span')?.textContent?.trim()
        const title = row.querySelector('td strong')?.textContent?.trim() || ticker
        if (!ticker) return
        const modal = openModal({ eyebrow: 'Resolution docket', title, body: '<div class="arbiter-governed-loading">Loading governed resolution trail…</div>' })
        try {
          const result = await api(`/api/markets/${encodeURIComponent(ticker)}`)
          modal.querySelector('.arbiter-governed-modal-body').innerHTML = `
            <div class="arbiter-detail-grid"><div><span>Ticker</span><strong>${esc(ticker)}</strong></div><div><span>Current state</span><strong>${esc(result?.resolution?.outcome || result?.report?.verdict?.key || '—')}</strong></div></div>
            <details open><summary>Governed resolution record</summary><pre>${esc(JSON.stringify(result, null, 2))}</pre></details>
            <div class="arbiter-modal-actions"><button type="button" class="primary" data-market-ask>Ask Arbiter about this contract</button></div>`
          modal.querySelector('[data-market-ask]')?.addEventListener('click', () => { closeModal(); clickAsk(`Explain contract ${ticker}, its resolution state, evidence risks, and what an operator should review next.`) })
        } catch (err) { modal.querySelector('.arbiter-governed-modal-body').innerHTML = `<p>${esc(err.message)}</p>` }
      })
    })
  }

  async function installAuthorityRows() {
    if (page.title !== 'Controls & authorities') return
    let records = []
    try { records = (await api('/api/authorities')).authorities || [] } catch {}
    const byId = new Map(records.map(x => [String(x.authority_id || x.id), x]))
    document.querySelectorAll('.console-list-row').forEach(row => {
      if (row.dataset.arbiterInteractive) return
      const span = row.querySelector('span')?.textContent || ''
      const id = span.split('·')[0].trim()
      if (!byId.has(id)) return
      row.dataset.arbiterInteractive = '1'
      row.classList.add('arbiter-clickable-row')
      row.addEventListener('click', () => {
        const record = byId.get(id)
        openModal({ eyebrow: 'Governed authority', title: record.name || id, body: `<details open><summary>Authority record</summary><pre>${esc(JSON.stringify(record, null, 2))}</pre></details><div class="arbiter-governed-boundary">Authority changes should be versioned and approved through the governed control workflow; this console does not silently overwrite an authority.</div>` })
      })
    })
  }

  async function installPolicyRows() {
    if (page.title !== 'Policy governance') return
    let drafts = []
    try { drafts = (await api('/api/policy/drafts')).drafts || [] } catch {}
    const byId = new Map(drafts.map(x => [String(x.draft_id || x.id), x]))
    document.querySelectorAll('.console-list-row').forEach(row => {
      if (row.dataset.arbiterInteractive) return
      const strong = row.querySelector('strong')?.textContent?.trim() || ''
      const draft = byId.get(strong) || drafts.find(d => strong.includes(String(d.draft_id || d.id)))
      if (!draft) return
      row.dataset.arbiterInteractive = '1'
      row.classList.add('arbiter-clickable-row')
      row.addEventListener('click', () => openDraftWorkflow(draft))
    })
  }

  function openDraftWorkflow(draft) {
    const id = draft.draft_id || draft.id
    const status = String(draft.status || 'draft').toLowerCase()
    let next = null
    if (status === 'draft') next = ['submit', 'Submit for review']
    else if (status === 'submitted' || status === 'review') next = ['approve', 'Approve draft']
    else if (status === 'approved') next = ['activate', 'Activate policy']
    const modal = openModal({
      eyebrow: 'Policy workflow',
      title: id,
      body: `<div class="arbiter-detail-grid"><div><span>Status</span><strong>${esc(status)}</strong></div></div><details open><summary>Draft record</summary><pre>${esc(JSON.stringify(draft, null, 2))}</pre></details>${next ? `<label class="arbiter-note-label"><span>Governance note</span><textarea id="arbiter-draft-note" rows="3" placeholder="Reason for this action…"></textarea></label><div class="arbiter-modal-actions"><button type="button" class="primary" data-draft-next>${esc(next[1])}</button></div>` : '<div class="arbiter-governed-boundary">No further workflow action is available from this state.</div>'}`
    })
    modal.querySelector('[data-draft-next]')?.addEventListener('click', async () => {
      const note = modal.querySelector('#arbiter-draft-note')?.value?.trim() || ''
      if (!note) { toast('Add a governance note before advancing the draft.', 'bad'); return }
      try {
        await api(`/api/policy/drafts/${encodeURIComponent(id)}/${next[0]}`, { method: 'POST', body: JSON.stringify({ actor: 'operator:console', note }) })
        toast(`Policy draft ${next[0]} action recorded.`, 'good')
        closeModal()
        setTimeout(() => window.location.reload(), 250)
      } catch (err) { toast(err.message, 'bad') }
    })
  }

  function currentTitle() {
    return document.querySelector('.console-main h1')?.textContent?.trim() || ''
  }

  function install() {
    const title = currentTitle()
    if (!title) return
    if (title !== page.title) page.title = title
    installToolbar(title)
    installCaseRows()
    installDocketRows()
    installAuthorityRows()
    installPolicyRows()
  }

  const observer = new MutationObserver(() => install())
  observer.observe(document.documentElement, { childList: true, subtree: true })
  window.addEventListener('load', () => setTimeout(install, 120))
  setInterval(install, 1000)
})()
