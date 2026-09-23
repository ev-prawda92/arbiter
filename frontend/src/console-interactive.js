/* Arbiter v0.31 progressive interaction layer.
 *
 * This keeps the governed React console intact while adding operator actions:
 * queue editing, filtering, console-native workspaces, and a conversational
 * Ask Arbiter surface. All mutations use existing governed APIs; the advisory
 * assistant never changes resolution state by itself.
 */

const state = {
  queue: null,
  overview: null,
  selectedId: null,
  workspaceOpen: false,
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  let payload = null
  try { payload = await response.json() } catch { payload = {} }
  if (!response.ok) {
    const detail = payload?.detail
    throw new Error(typeof detail === 'string' ? detail : `${path} returned ${response.status}`)
  }
  return payload
}

async function refreshData() {
  const [queue, overview] = await Promise.all([api('/api/work-queue'), api('/api/overview')])
  state.queue = queue
  state.overview = overview
  syncSelectedFromDom()
  return { queue, overview }
}

function activeItems() {
  return (state.queue?.items || []).filter(item => item.status !== 'resolved')
}

function syncSelectedFromDom() {
  const selectedRow = document.querySelector('.console-table tbody tr.selected')
  const title = selectedRow?.querySelector('td strong')?.textContent?.trim()
  if (title) {
    const match = (state.queue?.items || []).find(item => item.title === title)
    if (match) state.selectedId = match.id
  }
  if (!state.selectedId) state.selectedId = activeItems()[0]?.id || null
  renderQueueEditor()
}

function selectedItem() {
  return (state.queue?.items || []).find(item => item.id === state.selectedId) || null
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[ch]))
}

function ensureToastHost() {
  let host = document.getElementById('arbiter-toast-host')
  if (!host) {
    host = document.createElement('div')
    host.id = 'arbiter-toast-host'
    document.body.appendChild(host)
  }
  return host
}

function toast(message, tone = 'neutral') {
  const host = ensureToastHost()
  const el = document.createElement('div')
  el.className = `arbiter-toast ${tone}`
  el.textContent = message
  host.appendChild(el)
  setTimeout(() => el.remove(), 3200)
}

function installQueueTools() {
  const tableCard = document.querySelector('.console-workspace .console-table-card')
  if (!tableCard || tableCard.querySelector('.arbiter-queue-tools')) return
  const header = tableCard.querySelector('.console-section-head')
  if (!header) return

  const tools = document.createElement('div')
  tools.className = 'arbiter-queue-tools'
  tools.innerHTML = `
    <div class="arbiter-filter-row">
      <label><span>Search queue</span><input id="arbiter-queue-search" placeholder="Case, owner, blocker…" /></label>
      <label><span>State</span><select id="arbiter-queue-state"><option value="all">All active</option><option value="critical">Critical</option><option value="high">High</option><option value="in_progress">In progress</option></select></label>
      <button type="button" id="arbiter-clear-filters">Clear</button>
    </div>`
  header.insertAdjacentElement('afterend', tools)

  const apply = () => {
    const q = document.getElementById('arbiter-queue-search')?.value?.toLowerCase().trim() || ''
    const filter = document.getElementById('arbiter-queue-state')?.value || 'all'
    document.querySelectorAll('.console-table-card .console-table tbody tr').forEach(row => {
      const title = row.querySelector('td strong')?.textContent?.trim()
      const item = (state.queue?.items || []).find(i => i.title === title)
      if (!item) return
      const matchesText = !q || `${item.title} ${item.detail} ${item.owner_role} ${item.owner} ${item.kind}`.toLowerCase().includes(q)
      const matchesFilter = filter === 'all' || item.severity === filter || item.status === filter
      row.style.display = matchesText && matchesFilter ? '' : 'none'
    })
  }
  tools.querySelector('#arbiter-queue-search').addEventListener('input', apply)
  tools.querySelector('#arbiter-queue-state').addEventListener('change', apply)
  tools.querySelector('#arbiter-clear-filters').addEventListener('click', () => {
    tools.querySelector('#arbiter-queue-search').value = ''
    tools.querySelector('#arbiter-queue-state').value = 'all'
    apply()
  })
}

function renderQueueEditor() {
  const inspector = document.querySelector('.console-inspector')
  if (!inspector) return
  let editor = inspector.querySelector('.arbiter-case-editor')
  if (!editor) {
    editor = document.createElement('section')
    editor.className = 'arbiter-case-editor'
    inspector.appendChild(editor)
  }
  const item = selectedItem()
  if (!item) {
    editor.innerHTML = ''
    return
  }
  editor.innerHTML = `
    <div class="arbiter-editor-head"><span>Operator actions</span><strong>Work this case</strong></div>
    <label><span>Status</span><select data-field="status">
      <option value="open" ${item.status === 'open' ? 'selected' : ''}>Open</option>
      <option value="in_progress" ${item.status === 'in_progress' ? 'selected' : ''}>In progress</option>
      <option value="resolved" ${item.status === 'resolved' ? 'selected' : ''}>Resolved</option>
    </select></label>
    <label><span>Owner</span><input data-field="owner" value="${escapeHtml(item.owner || '')}" placeholder="operator@team" /></label>
    <label><span>Operator note</span><textarea data-field="note" rows="3" placeholder="Why this state changed…">${escapeHtml(item.note || '')}</textarea></label>
    <div class="arbiter-editor-actions">
      <button type="button" data-action="save">Save governed work state</button>
      <button type="button" class="secondary" data-action="workspace">Open workspace</button>
    </div>
    <p class="arbiter-editor-boundary">This changes queue ownership/status only. It does not alter evidence, policy, or the binding resolution.</p>`

  editor.querySelector('[data-action="save"]').addEventListener('click', async () => {
    const payload = {
      status: editor.querySelector('[data-field="status"]').value,
      owner: editor.querySelector('[data-field="owner"]').value.trim(),
      note: editor.querySelector('[data-field="note"]').value.trim(),
      actor: 'operator:console',
    }
    try {
      const result = await api(`/api/work-queue/${encodeURIComponent(item.id)}`, { method: 'POST', body: JSON.stringify(payload) })
      state.queue = result.queue || state.queue
      toast('Work item updated and audited.', 'good')
      setTimeout(() => window.location.reload(), 350)
    } catch (err) {
      toast(err.message || 'Unable to update work item', 'bad')
    }
  })
  editor.querySelector('[data-action="workspace"]').addEventListener('click', () => openWorkspace(item))
}

async function loadWorkspaceContext(item) {
  const context = { item }
  if (!item) return context
  if (item.subject) {
    try { context.market = await api(`/api/markets/${encodeURIComponent(item.subject)}`) } catch {}
    try { context.case = await api(`/api/cases/${encodeURIComponent(item.subject)}`) } catch {}
  }
  return context
}

async function openWorkspace(item = selectedItem()) {
  if (!item) return
  closeWorkspace()
  state.workspaceOpen = true
  const backdrop = document.createElement('div')
  backdrop.className = 'arbiter-workspace-backdrop'
  backdrop.id = 'arbiter-workspace-backdrop'
  backdrop.innerHTML = `<section class="arbiter-workspace-modal"><div class="arbiter-workspace-loading">Loading governed case context…</div></section>`
  document.body.appendChild(backdrop)
  backdrop.addEventListener('click', event => { if (event.target === backdrop) closeWorkspace() })

  const context = await loadWorkspaceContext(item)
  const market = context.market?.market || context.market?.report || context.market
  const savedCase = context.case?.case
  const modal = backdrop.querySelector('.arbiter-workspace-modal')
  modal.innerHTML = `
    <header class="arbiter-workspace-head">
      <div><span>Console-native case workspace</span><h2>${escapeHtml(item.title)}</h2><p>${escapeHtml(item.subject || item.id)}</p></div>
      <button type="button" aria-label="Close workspace">×</button>
    </header>
    <div class="arbiter-workspace-grid">
      <section><h3>Contract / issue</h3><p>${escapeHtml(item.detail || 'No additional description.')}</p><dl><dt>Type</dt><dd>${escapeHtml(item.kind)}</dd><dt>Severity</dt><dd>${escapeHtml(item.severity)}</dd><dt>Notional</dt><dd>${item.notional ? `$${Number(item.notional).toLocaleString()}` : '—'}</dd></dl></section>
      <section><h3>Governed state</h3><dl><dt>Status</dt><dd>${escapeHtml(item.status)}</dd><dt>Owner role</dt><dd>${escapeHtml(item.owner_role || 'Resolution Ops')}</dd><dt>Owner</dt><dd>${escapeHtml(item.owner || 'Unassigned')}</dd></dl><p>${escapeHtml(item.recommended_action || '')}</p></section>
      <section><h3>Authority & evidence</h3><p>${escapeHtml(market?.title || savedCase?.title || 'Use the governed source and evidence record attached to this work item.')}</p><details><summary>View source context</summary><pre>${escapeHtml(JSON.stringify(market || savedCase || item, null, 2))}</pre></details></section>
      <section><h3>Operator record</h3><p>${escapeHtml(item.note || 'No operator note yet.')}</p><button type="button" class="arbiter-workspace-ask">Ask Arbiter about this case</button></section>
    </div>`
  modal.querySelector('header button').addEventListener('click', closeWorkspace)
  modal.querySelector('.arbiter-workspace-ask').addEventListener('click', () => {
    closeWorkspace()
    clickAskArbiter()
    setTimeout(() => focusAskInput(`Why is ${item.title} on hold and what should I do next?`), 150)
  })
}

function closeWorkspace() {
  document.getElementById('arbiter-workspace-backdrop')?.remove()
  state.workspaceOpen = false
}

function clickAskArbiter() {
  const button = [...document.querySelectorAll('button')].find(el => el.textContent?.includes('Ask Arbiter'))
  button?.click()
}

function focusAskInput(prefill = '') {
  const input = document.querySelector('#arbiter-ask-input')
  if (!input) return
  if (prefill) input.value = prefill
  input.focus()
}

function installAskArbiter() {
  const drawer = document.querySelector('.console-drawer')
  if (!drawer || drawer.querySelector('.arbiter-chat')) return
  const boundaryButton = drawer.querySelector('.console-dark-button')
  const chat = document.createElement('section')
  chat.className = 'arbiter-chat'
  chat.innerHTML = `
    <div class="arbiter-chat-context"><span>Conversation context</span><strong id="arbiter-chat-context-label">Whole queue</strong></div>
    <div class="arbiter-chat-messages" id="arbiter-chat-messages">
      <div class="arbiter-message assistant"><span>Arbiter</span><p>Ask me about this queue, a selected case, repeated blockers, evidence gaps, or what to work next. My guidance is advisory and cannot change a governed resolution.</p></div>
    </div>
    <div class="arbiter-prompt-chips">
      <button type="button">What should I work first?</button>
      <button type="button">Why are these cases grouped?</button>
      <button type="button">What is blocking the selected case?</button>
    </div>
    <form class="arbiter-chat-form">
      <textarea id="arbiter-ask-input" rows="3" placeholder="Ask Arbiter about the queue or selected case…"></textarea>
      <button type="submit">Send</button>
    </form>`
  boundaryButton?.insertAdjacentElement('beforebegin', chat)

  const updateContext = () => {
    const item = selectedItem()
    chat.querySelector('#arbiter-chat-context-label').textContent = item ? `Selected case · ${item.title}` : 'Whole queue'
  }
  updateContext()

  chat.querySelectorAll('.arbiter-prompt-chips button').forEach(btn => btn.addEventListener('click', () => {
    chat.querySelector('#arbiter-ask-input').value = btn.textContent
    chat.querySelector('.arbiter-chat-form').requestSubmit()
  }))
  chat.querySelector('.arbiter-chat-form').addEventListener('submit', async event => {
    event.preventDefault()
    const input = chat.querySelector('#arbiter-ask-input')
    const question = input.value.trim()
    if (!question) return
    appendMessage(chat, 'user', 'You', question)
    input.value = ''
    const thinking = appendMessage(chat, 'assistant thinking', 'Arbiter', 'Analyzing governed queue state…')
    try {
      const answer = await answerQuestion(question)
      thinking.remove()
      appendMessage(chat, 'assistant', 'Arbiter', answer.answer, answer.meta)
    } catch (err) {
      thinking.remove()
      appendMessage(chat, 'assistant error', 'Arbiter', err.message || 'Unable to answer right now.')
    }
  })
}

function appendMessage(chat, cls, label, text, meta = '') {
  const messages = chat.querySelector('#arbiter-chat-messages')
  const el = document.createElement('div')
  el.className = `arbiter-message ${cls}`
  el.innerHTML = `<span>${escapeHtml(label)}</span><p>${escapeHtml(text)}</p>${meta ? `<small>${escapeHtml(meta)}</small>` : ''}`
  messages.appendChild(el)
  messages.scrollTop = messages.scrollHeight
  return el
}

async function answerQuestion(question) {
  await refreshData()
  const item = selectedItem()

  // If the selected subject is a saved analysis case, use the governed model
  // gateway. If no provider is configured or the subject is not a saved case,
  // fall back to deterministic queue intelligence rather than fabricate an AI answer.
  if (item?.subject) {
    try {
      const response = await api(`/api/cases/${encodeURIComponent(item.subject)}/copilot`, {
        method: 'POST',
        body: JSON.stringify({ question, model_tier: 'default' }),
      })
      if (response?.answer) {
        const actions = (response.next_actions || []).slice(0, 3)
        return {
          answer: `${response.answer}${actions.length ? ` Next: ${actions.join(' · ')}` : ''}`,
          meta: `Model-assisted · ${response.confidence || 'confidence n/a'} · advisory only`,
        }
      }
    } catch (err) {
      if (!/404|not found|provider|disabled|503/i.test(String(err.message))) throw err
    }
  }

  return deterministicAnswer(question, item)
}

function deterministicAnswer(question, item) {
  const q = question.toLowerCase()
  const intelligence = state.overview?.agent_brief?.operations_intelligence || {}
  const summary = intelligence.summary || {}
  const clusters = intelligence.clusters || []
  const sequence = intelligence.recommended_sequence || []
  const active = activeItems()

  if (/first|priority|work next|what should i work/.test(q)) {
    const next = sequence.slice(0, 3).map((x, i) => `${i + 1}) ${x.label}${x.case_count > 1 ? ` (${x.case_count} cases)` : ''}`).join(' ')
    return { answer: next || 'No recommended sequence is currently available.', meta: 'Deterministic operations intelligence · advisory only' }
  }
  if (/group|cluster|pattern|same/.test(q)) {
    const repeated = clusters.filter(c => c.count > 1).slice(0, 4)
    const text = repeated.map(c => `${c.count} cases share ${String(c.blocker_type).replaceAll('_', ' ')}`).join('; ')
    return { answer: text ? `Arbiter grouped repeated root causes: ${text}. Work the shared rule or evidence issue before processing each case independently.` : 'No repeated root-cause clusters are currently detected.', meta: 'Deterministic clustering · advisory only' }
  }
  if (item && /why|block|hold|missing|evidence|authority|next|resolve/.test(q)) {
    const cluster = clusters.find(c => (c.case_ids || []).includes(item.id))
    const blocker = cluster?.blocker_type || item.kind || 'operator review'
    return {
      answer: `${item.title} is in the queue because of ${String(blocker).replaceAll('_', ' ')}. ${item.detail || ''} Recommended next action: ${item.recommended_action || 'inspect the governed evidence and authority before settlement.'}${cluster?.count > 1 ? ` This root cause affects ${cluster.count} cases, so resolving the shared issue may clear the group.` : ''}`,
      meta: 'Grounded in governed work-queue state · advisory only',
    }
  }
  return {
    answer: `The current queue has ${summary.active_cases ?? active.length} active cases across ${summary.distinct_work_patterns ?? clusters.length} work patterns. ${summary.ready_for_review ?? 0} are marked ready for operator review, ${summary.waiting_on_external_data ?? 0} are waiting on external data, and ${summary.policy_interpretation ?? 0} require policy interpretation. Ask about a blocker, cluster, selected case, or recommended work sequence for a more specific answer.`,
    meta: 'Deterministic operations intelligence · advisory only',
  }
}

function installRowInteractions() {
  document.querySelectorAll('.console-table tbody tr').forEach(row => {
    if (row.dataset.arbiterInteractive) return
    row.dataset.arbiterInteractive = '1'
    row.addEventListener('click', () => setTimeout(() => {
      syncSelectedFromDom()
      const item = selectedItem()
      if (item) document.dispatchEvent(new CustomEvent('arbiter:selected-work-item', { detail: item }))
    }, 0))
  })
}

function installCaseWorkspaceButton() {
  const buttons = [...document.querySelectorAll('.console-next-action button')]
  buttons.forEach(button => {
    if (button.dataset.arbiterWorkspaceBound) return
    button.dataset.arbiterWorkspaceBound = '1'
    button.addEventListener('click', event => {
      event.preventDefault()
      event.stopImmediatePropagation()
      openWorkspace(selectedItem())
    }, true)
  })
}

function installPageInteractions() {
  document.querySelectorAll('.console-list-row, .resolution-table tbody tr').forEach(row => {
    if (row.dataset.arbiterInspectBound) return
    row.dataset.arbiterInspectBound = '1'
    row.title = row.title || 'Click to inspect'
    row.classList.add('arbiter-clickable-row')
  })
}

async function boot() {
  try { await refreshData() } catch (err) { console.warn('Arbiter interaction layer could not preload data', err) }

  const observer = new MutationObserver(() => {
    installQueueTools()
    installRowInteractions()
    installCaseWorkspaceButton()
    installAskArbiter()
    installPageInteractions()
    syncSelectedFromDom()
  })
  observer.observe(document.body, { childList: true, subtree: true })

  installQueueTools()
  installRowInteractions()
  installCaseWorkspaceButton()
  installAskArbiter()
  installPageInteractions()
  syncSelectedFromDom()

  const params = new URLSearchParams(window.location.search)
  const requested = params.get('case')
  if (requested) {
    const item = (state.queue?.items || []).find(x => x.subject === requested || x.id === requested)
    if (item) {
      state.selectedId = item.id
      setTimeout(() => openWorkspace(item), 120)
    }
  }
}

boot()
