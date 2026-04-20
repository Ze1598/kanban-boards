const STATUSES = ['Not Triaged', 'Backlog', 'In Progress', 'Needs Review', 'Ready Playback', 'Done'];

const state = {
  sprints: [],
  currentSprintId: null,
  cards: [],
  editingCardId: null,
  sprintModalMode: null, // 'create' | 'rename'
};

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
  state.cards = has ? await api('GET', `/api/sprints/${id}/cards`) : [];
  renderBoard();
}

// ── Cards ─────────────────────────────────────────────────────────────────────

async function createCard(data) {
  const card = await api('POST', `/api/sprints/${state.currentSprintId}/cards`, data);
  state.cards.push(card);
  renderBoard();
}

async function updateCard(id, data) {
  const card = await api('PUT', `/api/cards/${id}`, data);
  const idx = state.cards.findIndex(c => c.id === id);
  if (idx !== -1) state.cards[idx] = card;
  renderBoard();
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
  el.innerHTML = `
    <span class="card-title">${esc(card.title)}</span>
    <span class="pri-dot ${card.priority}" title="${card.priority} priority"></span>
  `;

  el.addEventListener('dragstart', e => {
    e.dataTransfer.setData('card-id', card.id);
    requestAnimationFrame(() => el.classList.add('dragging'));
  });
  el.addEventListener('dragend', () => el.classList.remove('dragging'));
  el.addEventListener('click', () => openCardModal(card));
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

function openCardModal(card) {
  state.editingCardId = card?.id ?? null;
  document.getElementById('card-modal-title').textContent = card ? 'Edit Card' : 'New Card';
  document.getElementById('card-title').value = card?.title ?? '';
  document.getElementById('card-description').value = card?.description ?? '';
  document.getElementById('card-status').value = card?.status ?? 'Not Triaged';
  document.getElementById('card-priority').value = card?.priority ?? 'Medium';
  document.getElementById('card-notes').value = card?.notes ?? '';
  document.getElementById('card-created-at').value = card?.created_at ?? '';
  document.getElementById('card-due-on').value = card?.due_on ?? '';
  document.getElementById('card-delivered-on').value = card?.delivered_on ?? '';

  const deleteBtn = document.getElementById('card-delete');
  deleteBtn.style.visibility = card ? 'visible' : 'hidden';

  document.getElementById('card-overlay').classList.remove('hidden');
  document.getElementById('card-title').focus();
}

function closeCardModal() {
  document.getElementById('card-overlay').classList.add('hidden');
  state.editingCardId = null;
}

async function saveCard() {
  const title = document.getElementById('card-title').value.trim();
  if (!title) { document.getElementById('card-title').focus(); return; }
  const data = {
    title,
    description: document.getElementById('card-description').value,
    status: document.getElementById('card-status').value,
    priority: document.getElementById('card-priority').value,
    notes: document.getElementById('card-notes').value,
    due_on: document.getElementById('card-due-on').value || null,
    delivered_on: document.getElementById('card-delivered-on').value || null,
  };
  if (state.editingCardId) {
    await updateCard(state.editingCardId, data);
  } else {
    await createCard(data);
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

// ── Boot ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  await loadSprints();

  // Sprint controls
  document.getElementById('sprint-select').addEventListener('change', e => {
    selectSprint(parseInt(e.target.value) || null);
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

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeCardModal(); closeSprintModal(); }
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
