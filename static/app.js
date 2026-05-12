const STATUSES = ['Not Triaged', 'Backlog', 'Blocked', 'In Progress', 'Needs Review', 'Ready Playback', 'On Standby', 'Done'];

const DAY_W  = 38;   // px per day column
const ROW_H  = 46;   // px per task row
const PILL_W = 156;  // px pill width
const PILL_H = 28;   // px pill height
const PILL_R = 14;   // corner radius (full pill shape)

const STATUS_COLOR = {
  'Not Triaged':    '#9ca3af',
  'Backlog':        '#6366f1',
  'In Progress':    '#3b82f6',
  'Needs Review':   '#f59e0b',
  'Ready Playback': '#a855f7',
  'On Standby':     '#ececec',
  'Done':           '#22c55e',
  'Blocked':        '#ef4444',
};

const PRI_COLOR = { Low: '#22c55e', Medium: '#f59e0b', High: '#ef4444' };

const state = {
  sprints: [],
  currentSprintId: null,
  cards: [],
  deps: [],          // [{card_id, depends_on}] for current sprint
  view: 'kanban',    // 'kanban' | 'gantt'
  editingCardId: null,
  sprintModalMode: null,
};

// Ephemeral set of card IDs hidden from the Gantt chart; resets on page reload
const ganttHiddenCards = new Set();

// ── API ──────────────────────────────────────────────────────────────────────

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body != null ? { 'Content-Type': 'application/json' } : {},
    body: body != null ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

// ── Sprints ──────────────────────────────────────────────────────────────────

async function loadSprints() {
  state.sprints = await api('GET', '/api/sprints');
  renderSprintSelect();
  if (state.sprints.length > 0) {
    await selectSprint(state.sprints[0].id);
  }
}

async function createSprint(name) {
  const sprint = await api('POST', '/api/sprints', { name });
  state.sprints.unshift(sprint);
  renderSprintSelect();
  await selectSprint(sprint.id);
}

async function renameSprint(id, name) {
  const sprint = await api('PUT', `/api/sprints/${id}`, { name });
  const idx = state.sprints.findIndex(s => s.id === id);
  if (idx !== -1) state.sprints[idx] = sprint;
  renderSprintSelect();
}

async function deleteSprint(id) {
  await api('DELETE', `/api/sprints/${id}`);
  state.sprints = state.sprints.filter(s => s.id !== id);
  state.currentSprintId = null;
  state.cards = [];
  renderSprintSelect();
  renderBoard();
}

async function selectSprint(id) {
  state.currentSprintId = id;
  document.getElementById('sprint-select').value = id ?? '';
  const has = !!id;
  document.getElementById('btn-add-card').disabled = !has;
  document.getElementById('btn-rename-sprint').disabled = !has;
  document.getElementById('btn-delete-sprint').disabled = !has;
  document.getElementById('btn-toggle-view').disabled = !has;
  if (has) {
    [state.cards, state.deps] = await Promise.all([
      api('GET', `/api/sprints/${id}/cards`),
      api('GET', `/api/sprints/${id}/dependencies`),
    ]);
  } else {
    state.cards = [];
    state.deps = [];
  }
  if (state.view === 'kanban') renderBoard();
  else renderGantt();
}

// ── Cards ─────────────────────────────────────────────────────────────────────

async function createCard(data) {
  const sprintId = data.sprint_id ?? state.currentSprintId;
  const card = await api('POST', `/api/sprints/${sprintId}/cards`, data);
  if (card.sprint_id === state.currentSprintId) state.cards.push(card);
  if (state.view === 'kanban') renderBoard();
  else renderGantt();
}

async function updateCard(id, data) {
  const card = await api('PUT', `/api/cards/${id}`, data);
  const idx = state.cards.findIndex(c => c.id === id);
  if (card.sprint_id !== state.currentSprintId) {
    if (idx !== -1) state.cards.splice(idx, 1);
  } else {
    if (idx !== -1) state.cards[idx] = card;
  }
  if (state.view === 'kanban') renderBoard();
  else renderGantt();
}

async function deleteCard(id) {
  await api('DELETE', `/api/cards/${id}`);
  state.cards = state.cards.filter(c => c.id !== id);
  renderBoard();
}

// ── Render ───────────────────────────────────────────────────────────────────

function renderSprintSelect() {
  const sel = document.getElementById('sprint-select');
  sel.innerHTML = '<option value="">— select sprint —</option>';
  state.sprints.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = s.name;
    if (s.id === state.currentSprintId) opt.selected = true;
    sel.appendChild(opt);
  });
}

function renderBoard() {
  const board = document.getElementById('board');
  if (!state.currentSprintId) {
    board.innerHTML = '<div class="empty-state">Select or create a sprint to get started.</div>';
    return;
  }
  board.innerHTML = '';

  STATUSES.forEach(status => {
    const cards = state.cards
      .filter(c => c.status === status)
      .sort((a, b) => a.position - b.position);

    const col = document.createElement('div');
    col.className = 'column';
    col.dataset.status = status;
    col.innerHTML = `
      <div class="col-header">
        <span>${esc(status)}</span>
        <span class="count">${cards.length}</span>
      </div>
      <div class="col-cards" data-status="${esc(status)}"></div>
    `;

    const zone = col.querySelector('.col-cards');
    cards.forEach(card => zone.appendChild(buildCard(card)));

    zone.addEventListener('dragover', e => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', e => {
      if (!zone.contains(e.relatedTarget)) zone.classList.remove('drag-over');
    });
    zone.addEventListener('drop', async e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const cardId = parseInt(e.dataTransfer.getData('card-id'));
      if (!cardId) return;
      const card = state.cards.find(c => c.id === cardId);
      if (!card || card.status === status) return;
      await updateCard(cardId, { ...card, status });
    });

    board.appendChild(col);
  });
}

function buildCard(card) {
  const el = document.createElement('div');
  el.className = 'card';
  el.draggable = true;
  el.dataset.id = card.id;
  const ganttVisible = !ganttHiddenCards.has(card.id);
  el.innerHTML = `
    <span class="card-title">${esc(card.title)}</span>
    <div class="card-meta">
      <input type="checkbox" class="gantt-check" ${ganttVisible ? 'checked' : ''} title="Show in Gantt">
      <span class="pri-dot ${card.priority}" title="${card.priority} priority"></span>
    </div>
  `;

  el.addEventListener('dragstart', e => {
    e.dataTransfer.setData('card-id', card.id);
    requestAnimationFrame(() => el.classList.add('dragging'));
  });
  el.addEventListener('dragend', () => el.classList.remove('dragging'));
  el.addEventListener('click', () => openCardModal(card));

  const check = el.querySelector('.gantt-check');
  check.addEventListener('click', e => e.stopPropagation());
  check.addEventListener('change', () => {
    if (check.checked) ganttHiddenCards.delete(card.id);
    else ganttHiddenCards.add(card.id);
    if (state.view === 'gantt') renderGantt();
  });

  return el;
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Card modal ───────────────────────────────────────────────────────────────

// Staged dependency deletions — committed only on Save, discarded on Cancel
let modalDeps = { predecessors: [], successors: [] };
let pendingDepDeletions = [];

async function openCardModal(card) {
  state.editingCardId = card?.id ?? null;
  modalDeps = { predecessors: [], successors: [] };
  pendingDepDeletions = [];

  document.getElementById('card-modal-title').textContent = card ? 'Edit Card' : 'New Card';
  document.getElementById('card-title').value = card?.title ?? '';
  document.getElementById('card-description').value = card?.description ?? '';
  document.getElementById('card-status').value = card?.status ?? 'Not Triaged';
  document.getElementById('card-priority').value = card?.priority ?? 'Medium';
  document.getElementById('card-notes').value = card?.notes ?? '';
  document.getElementById('card-created-at').value = card?.created_at ?? '';
  document.getElementById('card-due-on').value = card?.due_on ?? '';
  document.getElementById('card-delivered-on').value = card?.delivered_on ?? '';

  const sprintSel = document.getElementById('card-sprint');
  sprintSel.innerHTML = '';
  const cardSprintId = card?.sprint_id ?? state.currentSprintId;
  state.sprints.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = s.name;
    if (s.id === cardSprintId) opt.selected = true;
    sprintSel.appendChild(opt);
  });

  const deleteBtn = document.getElementById('card-delete');
  deleteBtn.style.visibility = card ? 'visible' : 'hidden';

  // Dependencies section — only for existing cards
  const depsSection = document.getElementById('card-deps-section');
  const depsContent = document.getElementById('card-deps-content');
  if (card) {
    depsSection.style.display = 'flex';
    depsContent.innerHTML = '<span class="dep-loading">Loading…</span>';
  } else {
    depsSection.style.display = 'none';
  }

  document.getElementById('card-overlay').classList.remove('hidden');
  document.getElementById('card-title').focus();

  if (card) {
    const fetched = await api('GET', `/api/cards/${card.id}/dependencies`);
    modalDeps = fetched;
    renderCardDeps(card.id, depsContent);
  }
}

function renderCardDeps(cardId, container) {
  const deps = modalDeps;
  if (!deps.predecessors.length && !deps.successors.length) {
    container.innerHTML = '<span class="dep-none">None</span>';
    return;
  }

  const section = (label, items, makeCardId, makeDependsOn) => {
    if (!items.length) return '';
    const rows = items.map(c => `
      <div class="dep-item">
        <span class="dep-item-title">${esc(c.title)}</span>
        <button class="dep-del"
                data-cid="${makeCardId(c.id)}"
                data-did="${makeDependsOn(c.id)}"
                title="Remove dependency">×</button>
      </div>`).join('');
    return `<div class="dep-group">
      <span class="dep-group-label">${label}</span>${rows}
    </div>`;
  };

  container.innerHTML =
    section('Predecessors', deps.predecessors,
      ()  => cardId,
      pid => pid
    ) +
    section('Successors', deps.successors,
      sid => sid,
      ()  => cardId
    );

  container.querySelectorAll('.dep-del').forEach(btn => {
    btn.addEventListener('click', () => {
      const cid = parseInt(btn.dataset.cid);
      const did = parseInt(btn.dataset.did);
      pendingDepDeletions.push({ card_id: cid, depends_on: did });
      // Remove from local view — predecessor if cid===cardId, successor otherwise
      if (cid === cardId) {
        modalDeps.predecessors = modalDeps.predecessors.filter(p => p.id !== did);
      } else {
        modalDeps.successors = modalDeps.successors.filter(s => s.id !== cid);
      }
      renderCardDeps(cardId, container);
    });
  });
}

function closeCardModal() {
  document.getElementById('card-overlay').classList.add('hidden');
  state.editingCardId = null;
  pendingDepDeletions = [];
  modalDeps = { predecessors: [], successors: [] };
}

async function saveCard() {
  const title = document.getElementById('card-title').value.trim();
  if (!title) { document.getElementById('card-title').focus(); return; }
  const selectedSprintId = parseInt(document.getElementById('card-sprint').value) || state.currentSprintId;
  const data = {
    title,
    description: document.getElementById('card-description').value,
    status: document.getElementById('card-status').value,
    priority: document.getElementById('card-priority').value,
    notes: document.getElementById('card-notes').value,
    due_on: document.getElementById('card-due-on').value || null,
    delivered_on: document.getElementById('card-delivered-on').value || null,
    sprint_id: selectedSprintId,
  };
  if (state.editingCardId) {
    await updateCard(state.editingCardId, data);
  } else {
    await createCard(data);
  }
  if (pendingDepDeletions.length) {
    await Promise.all(
      pendingDepDeletions.map(({ card_id, depends_on }) =>
        api('DELETE', `/api/dependencies/${card_id}/${depends_on}`)
      )
    );
    if (state.view === 'gantt' && state.currentSprintId) {
      state.deps = await api('GET', `/api/sprints/${state.currentSprintId}/dependencies`);
      renderGantt();
    }
  }
  closeCardModal();
}

// ── Sprint modal ─────────────────────────────────────────────────────────────

function openSprintModal(mode) {
  state.sprintModalMode = mode;
  document.getElementById('sprint-modal-title').textContent =
    mode === 'create' ? 'New Sprint' : 'Rename Sprint';
  const current = state.sprints.find(s => s.id === state.currentSprintId);
  document.getElementById('sprint-name-input').value =
    mode === 'rename' && current ? current.name : '';
  document.getElementById('sprint-overlay').classList.remove('hidden');
  document.getElementById('sprint-name-input').focus();
}

function closeSprintModal() {
  document.getElementById('sprint-overlay').classList.add('hidden');
}

async function saveSprintModal() {
  const name = document.getElementById('sprint-name-input').value.trim();
  if (!name) return;
  if (state.sprintModalMode === 'create') {
    await createSprint(name);
  } else {
    await renameSprint(state.currentSprintId, name);
  }
  closeSprintModal();
}

// ── Dependency drag state ────────────────────────────────────────────────────

const drag = {
  active:     false,
  hasMoved:   false,
  fromCardId: null,
  fromX:      0,
  fromY:      0,
  side:       null,  // 'left' | 'right'
  rubberBand: null,
};

function svgPoint(svg, e) {
  const r = svg.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}

function getPillAtPoint(x, y) {
  const el = document.elementFromPoint(x, y);
  const pill = el?.closest('[data-card-id]');
  return pill ? parseInt(pill.dataset.cardId) : null;
}

function cancelDrag() {
  drag.active = false;
  drag.hasMoved = false;
  if (drag.rubberBand) { drag.rubberBand.remove(); drag.rubberBand = null; }
  document.body.classList.remove('dragging-dep');
  document.querySelector('.pill[data-dragging]')?.removeAttribute('data-dragging');
  drag.fromCardId = null;
}

async function createDependency(cardId, dependsOn) {
  const result = await api('POST', '/api/dependencies', { card_id: cardId, depends_on: dependsOn });
  if (result.error) { alert(result.error); return; }
  state.deps = await api('GET', `/api/sprints/${state.currentSprintId}/dependencies`);
  renderGantt();
}

async function deleteDependency(cardId, dependsOn) {
  await api('DELETE', `/api/dependencies/${cardId}/${dependsOn}`);
  state.deps = await api('GET', `/api/sprints/${state.currentSprintId}/dependencies`);
  renderGantt();
}

// ── View toggle ──────────────────────────────────────────────────────────────

function switchView(v) {
  state.view = v;
  const isGantt = v === 'gantt';
  document.getElementById('board').classList.toggle('hidden', isGantt);
  document.getElementById('gantt').classList.toggle('hidden', !isGantt);
  document.getElementById('btn-toggle-view').textContent = isGantt ? 'Board' : 'Gantt';
  if (isGantt) renderGantt();
  else renderBoard();
}

// ── Gantt ─────────────────────────────────────────────────────────────────────

function topoSort(cards, deps) {
  const ids = new Set(cards.map(c => c.id));
  const inDeg = new Map(cards.map(c => [c.id, 0]));
  const adj   = new Map(cards.map(c => [c.id, []]));

  for (const d of deps) {
    if (ids.has(d.card_id) && ids.has(d.depends_on)) {
      inDeg.set(d.card_id, inDeg.get(d.card_id) + 1);
      adj.get(d.depends_on).push(d.card_id);
    }
  }

  const queue  = cards.filter(c => inDeg.get(c.id) === 0).map(c => c.id);
  const result = [];
  const cardMap = new Map(cards.map(c => [c.id, c]));

  while (queue.length) {
    const id = queue.shift();
    result.push(cardMap.get(id));
    for (const nxt of adj.get(id) || []) {
      const deg = inDeg.get(nxt) - 1;
      inDeg.set(nxt, deg);
      if (deg === 0) queue.push(nxt);
    }
  }

  // defensive: append any cards not reached (shouldn't happen without cycles)
  const seen = new Set(result.map(c => c.id));
  for (const c of cards) if (!seen.has(c.id)) result.push(c);

  return result;
}

function ganttDateRange(cards) {
  const dated = cards.filter(c => c.due_on).map(c => parseDate(c.due_on));
  if (!dated.length) {
    const t = today();
    return { start: t, totalDays: 30 };
  }
  const minMs = Math.min(...dated.map(d => d.getTime()));
  const maxMs = Math.max(...dated.map(d => d.getTime()));
  const start = new Date(minMs);
  const end   = new Date(maxMs);
  start.setDate(start.getDate() - 3);
  end.setDate(end.getDate() + 4);
  const span = Math.ceil((end - start) / 86400000);
  return { start, totalDays: Math.max(span, 30) };
}

function today() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function parseDate(str) {
  const [y, m, d] = str.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function dayIndex(dateStr, startDate) {
  return Math.round((parseDate(dateStr) - startDate) / 86400000);
}

function fmtDay(date) {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function fmtDayName(date) {
  return date.toLocaleDateString('en-US', { weekday: 'short' });
}

function isWeekend(date) {
  const d = date.getDay();
  return d === 0 || d === 6;
}

function trunc(str, n) {
  return str.length > n ? str.slice(0, n - 1) + '…' : str;
}

function renderGantt() {
  if (!state.currentSprintId) return;

  const sorted  = topoSort(state.cards, state.deps);
  const visible = sorted.filter(c => !ganttHiddenCards.has(c.id));
  const { start, totalDays } = ganttDateRange(state.cards);
  const todayMs = today().getTime();

  const totalW = totalDays * DAY_W;
  const schedH = visible.length * ROW_H;

  const isEmpty = !visible.some(c => c.due_on);
  document.getElementById('gantt-empty').classList.toggle('hidden', !isEmpty);
  document.querySelector('.g-wrap').style.display = isEmpty ? 'none' : 'grid';

  if (isEmpty) return;

  // Date header
  const gHead = document.getElementById('g-head');
  let headHtml = `<div class="g-head-inner" style="width:${totalW}px">`;
  for (let i = 0; i < totalDays; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const isToday   = d.getTime() === todayMs;
    const weekend   = isWeekend(d);
    const cls = [isToday && 'today', weekend && 'weekend'].filter(Boolean).join(' ');
    headHtml += `<div class="g-day ${cls}" style="width:${DAY_W}px; min-width:${DAY_W}px">
      <span class="g-day-name">${fmtDayName(d)}</span>
      <span>${fmtDay(d)}</span>
    </div>`;
  }
  headHtml += '</div>';
  gHead.innerHTML = headHtml;

  // Label sidebar (simple — Gantt visibility is controlled from the Kanban checkboxes)
  const gLabels = document.getElementById('g-labels');
  let labelsHtml = `<div class="g-labels-inner">`;
  for (const card of visible) {
    const color = STATUS_COLOR[card.status] || '#9ca3af';
    labelsHtml += `
      <div class="g-label" data-card-id="${card.id}" style="height:${ROW_H}px">
        <span class="g-label-title" title="${esc(card.title)}">${esc(card.title)}</span>
        <span class="g-label-badge" style="background:${color}">${esc(card.status)}</span>
      </div>`;
  }
  labelsHtml += '</div>';
  gLabels.innerHTML = labelsHtml;

  gLabels.querySelectorAll('.g-label').forEach(el => {
    el.addEventListener('click', () => {
      const card = state.cards.find(c => c.id === parseInt(el.dataset.cardId));
      if (card) openCardModal(card);
    });
  });

  // ── Body rows (zebra stripe backgrounds + today/weekend col highlights) ────
  const gRows = document.getElementById('g-rows');
  let rowsHtml = `<div style="position:relative; width:${totalW}px; height:${schedH}px">`;

  // column highlights
  for (let i = 0; i < totalDays; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const isToday = d.getTime() === todayMs;
    const weekend = isWeekend(d);
    if (isToday || weekend) {
      const cls = isToday ? 'today-col' : 'weekend';
      rowsHtml += `<div class="g-col-bg ${cls}" style="left:${i * DAY_W}px; width:${DAY_W}px"></div>`;
    }
  }

  // row backgrounds
  for (let i = 0; i < visible.length; i++) {
    rowsHtml += `<div class="g-row" style="position:absolute; top:${i * ROW_H}px; left:0; right:0; height:${ROW_H}px"></div>`;
  }
  rowsHtml += '</div>';
  gRows.innerHTML = rowsHtml;

  // ── SVG: pills + dependency arrows ────────────────────────────────────────
  const svg = document.getElementById('g-svg');
  svg.setAttribute('width',  totalW);
  svg.setAttribute('height', schedH);
  svg.style.width  = totalW  + 'px';
  svg.style.height = schedH  + 'px';

  // Map card id → {row, colX} for arrow routing
  const pillPos = new Map(); // card.id → { cx, cy, left, right }

  // Build row-index map from visible cards only
  const rowIndex = new Map(visible.map((c, i) => [c.id, i]));

  let svgContent = `
    <defs>
      <marker id="arrowhead" viewBox="0 0 10 8" refX="9" refY="4"
              markerWidth="6" markerHeight="6" orient="auto">
        <path d="M0 0 L10 4 L0 8 Z" fill="#9ca3af"/>
      </marker>
    </defs>`;

  // Pills — only for visible cards that have a due date
  for (const card of visible) {
    if (!card.due_on) continue;
    const row  = rowIndex.get(card.id);
    const col  = dayIndex(card.due_on, start);
    const cx   = col * DAY_W + DAY_W / 2;
    const cy   = row * ROW_H + ROW_H / 2;
    const px   = cx - PILL_W / 2;
    const py   = cy - PILL_H / 2;
    const color = STATUS_COLOR[card.status] || '#9ca3af';
    const priColor = PRI_COLOR[card.priority] || '#f59e0b';
    const label = trunc(card.title, 20);

    pillPos.set(card.id, { cx, cy, left: px, right: px + PILL_W });

    svgContent += `
      <g class="pill" data-card-id="${card.id}">
        <rect x="${px}" y="${py}" width="${PILL_W}" height="${PILL_H}" rx="${PILL_R}"
              fill="${color}22" stroke="${color}" stroke-width="1.5"/>
        <circle cx="${px + 14}" cy="${cy}" r="4" fill="${priColor}"/>
        <text x="${px + 24}" y="${cy + 4.5}" font-size="11.5"
              font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
              fill="${color === '#f59e0b' ? '#92620a' : color}"
              font-weight="500">${esc(label)}</text>
        <circle class="dep-handle" data-side="left"  cx="${px}"          cy="${cy}" r="6"
                fill="white" stroke="${color}" stroke-width="2"/>
        <circle class="dep-handle" data-side="right" cx="${px + PILL_W}" cy="${cy}" r="6"
                fill="white" stroke="${color}" stroke-width="2"/>
      </g>`;
  }

  // Dependency arrows — only between cards that both have pills
  const depPairs = state.deps.filter(
    d => pillPos.has(d.card_id) && pillPos.has(d.depends_on)
  );

  for (const d of depPairs) {
    const from = pillPos.get(d.depends_on); // predecessor
    const to   = pillPos.get(d.card_id);    // dependent

    const sx = from.right;
    const sy = from.cy;
    const ex = to.left;
    const ey = to.cy;
    const dx = Math.max(48, Math.abs(ex - sx) * 0.45);
    const pathD = `M ${sx} ${sy} C ${sx + dx} ${sy}, ${ex - dx} ${ey}, ${ex} ${ey}`;

    svgContent += `
      <g class="dep-arrow" data-from="${d.depends_on}" data-to="${d.card_id}">
        <path class="dep-arrow-hit" d="${pathD}"
              fill="none" stroke="transparent" stroke-width="12"/>
        <path class="dep-arrow-vis" d="${pathD}"
              fill="none" stroke="#9ca3af" stroke-width="1.5" stroke-dasharray="4 3"
              marker-end="url(#arrowhead)"/>
      </g>`;
  }

  svg.innerHTML = svgContent;

  // arrow clicks → delete dependency
  svg.querySelectorAll('.dep-arrow').forEach(el => {
    el.addEventListener('click', async () => {
      if (drag.active) return;
      const fromId = parseInt(el.dataset.from); // predecessor (depends_on)
      const toId   = parseInt(el.dataset.to);   // dependent  (card_id)
      const from   = state.cards.find(c => c.id === fromId);
      const to     = state.cards.find(c => c.id === toId);
      if (confirm(`Remove dependency:\n"${from?.title}" → "${to?.title}"?`)) {
        await deleteDependency(toId, fromId);
      }
    });
  });

  // pill clicks → open card modal (suppressed during/after drag)
  svg.querySelectorAll('.pill').forEach(el => {
    el.addEventListener('click', () => {
      if (drag.hasMoved) return; // swallow click that follows a drag gesture
      const card = state.cards.find(c => c.id === parseInt(el.dataset.cardId));
      if (card) openCardModal(card);
    });
  });

  // drag handle → initiate dependency draw
  svg.querySelectorAll('.dep-handle').forEach(handle => {
    handle.addEventListener('click', e => e.stopPropagation()); // never open modal from handle
    handle.addEventListener('mousedown', e => {
      e.preventDefault();
      e.stopPropagation();
      const pillGroup = handle.closest('.pill');
      const cardId = parseInt(pillGroup.dataset.cardId);
      const pos = pillPos.get(cardId);
      if (!pos) return;

      const side = handle.dataset.side;
      drag.active     = true;
      drag.hasMoved   = false;
      drag.fromCardId = cardId;
      drag.side       = side;
      drag.fromX      = side === 'left' ? pos.left : pos.right;
      drag.fromY      = pos.cy;

      drag.rubberBand = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      drag.rubberBand.setAttribute('stroke', 'var(--accent)');
      drag.rubberBand.setAttribute('stroke-width', '2');
      drag.rubberBand.setAttribute('stroke-dasharray', '5 3');
      drag.rubberBand.setAttribute('fill', 'none');
      drag.rubberBand.setAttribute('marker-end', 'url(#arrowhead)');
      drag.rubberBand.setAttribute('pointer-events', 'none');
      svg.appendChild(drag.rubberBand);

      document.body.classList.add('dragging-dep');
      pillGroup.setAttribute('data-dragging', '');
    });
  });

  // scroll sync: g-body drives g-head (X) and g-labels (Y)
  const gBody = document.getElementById('g-body');
  gBody.onscroll = () => {
    gHead.scrollLeft  = gBody.scrollLeft;
    gLabels.scrollTop = gBody.scrollTop;
  };
}

// ── Boot ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  await loadSprints();

  // Sprint controls
  document.getElementById('sprint-select').addEventListener('change', e => {
    selectSprint(parseInt(e.target.value) || null);
  });
  document.getElementById('btn-toggle-view').addEventListener('click', () => {
    switchView(state.view === 'kanban' ? 'gantt' : 'kanban');
  });
  document.getElementById('btn-new-sprint').addEventListener('click', () => openSprintModal('create'));
  document.getElementById('btn-rename-sprint').addEventListener('click', () => openSprintModal('rename'));
  document.getElementById('btn-delete-sprint').addEventListener('click', async () => {
    const sprint = state.sprints.find(s => s.id === state.currentSprintId);
    if (!sprint) return;
    if (confirm(`Delete sprint "${sprint.name}" and all its cards? This cannot be undone.`)) {
      await deleteSprint(state.currentSprintId);
    }
  });

  // Add card
  document.getElementById('btn-add-card').addEventListener('click', () => openCardModal(null));

  // Card modal
  document.getElementById('card-modal-close').addEventListener('click', closeCardModal);
  document.getElementById('card-cancel').addEventListener('click', closeCardModal);
  document.getElementById('card-save').addEventListener('click', saveCard);
  document.getElementById('card-delete').addEventListener('click', async () => {
    if (confirm('Delete this card?')) {
      await deleteCard(state.editingCardId);
      closeCardModal();
    }
  });
  document.getElementById('card-overlay').addEventListener('click', e => {
    if (e.target === document.getElementById('card-overlay')) closeCardModal();
  });

  // Sprint modal
  document.getElementById('sprint-modal-close').addEventListener('click', closeSprintModal);
  document.getElementById('sprint-cancel').addEventListener('click', closeSprintModal);
  document.getElementById('sprint-save').addEventListener('click', saveSprintModal);
  document.getElementById('sprint-overlay').addEventListener('click', e => {
    if (e.target === document.getElementById('sprint-overlay')) closeSprintModal();
  });

  // Dependency drag — global handlers (set up once, check drag.active internally)
  document.addEventListener('mousemove', e => {
    if (!drag.active || !drag.rubberBand) return;
    drag.hasMoved = true;
    const svg = document.getElementById('g-svg');
    if (!svg) return;
    const pt = svgPoint(svg, e);
    const dx = Math.max(50, Math.abs(pt.x - drag.fromX) * 0.45);
    if (drag.side === 'left') {
      // cursor → pill left edge (arrowhead arrives at left of source pill)
      drag.rubberBand.setAttribute('d',
        `M ${pt.x} ${pt.y} C ${pt.x + dx} ${pt.y}, ${drag.fromX - dx} ${drag.fromY}, ${drag.fromX} ${drag.fromY}`
      );
    } else {
      // pill right edge → cursor (arrowhead follows cursor toward target)
      drag.rubberBand.setAttribute('d',
        `M ${drag.fromX} ${drag.fromY} C ${drag.fromX + dx} ${drag.fromY}, ${pt.x - dx} ${pt.y}, ${pt.x} ${pt.y}`
      );
    }
  });

  document.addEventListener('mouseup', async e => {
    if (!drag.active) return;
    if (drag.hasMoved) {
      const targetId = getPillAtPoint(e.clientX, e.clientY);
      if (targetId && targetId !== drag.fromCardId) {
        const fromId = drag.fromCardId;
        const side   = drag.side;
        cancelDrag();
        // left:  fromId is the dependent,   targetId is the predecessor
        // right: fromId is the predecessor, targetId is the dependent
        await createDependency(
          side === 'left' ? fromId    : targetId,
          side === 'left' ? targetId  : fromId
        );
        return;
      }
    } else {
      // stationary click on handle — open modal for the source card
      const card = state.cards.find(c => c.id === drag.fromCardId);
      if (card) openCardModal(card);
    }
    cancelDrag();
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (drag.active) { cancelDrag(); return; }
      closeCardModal(); closeSprintModal();
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      if (!document.getElementById('card-overlay').classList.contains('hidden')) {
        if (document.activeElement.tagName !== 'TEXTAREA') saveCard();
      }
      if (!document.getElementById('sprint-overlay').classList.contains('hidden')) {
        saveSprintModal();
      }
    }
  });
});
