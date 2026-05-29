class ActionsEditor {
  constructor() {
    this.triggers = [];
    this.selectedIndex = -1;
    this.isDirty = false;
    this.rawContent = '';
    this.activeTab = 'visual';
    this.gifts = [];
    this.giftSearch = '';

    this.el = document.getElementById('actions-editor');
    this.tableBody = document.getElementById('actions-table-body');
    this.detailPanel = document.getElementById('actions-detail');
    this.rawTextarea = document.getElementById('actions-raw-text');
    this.rawDiag = document.getElementById('actions-raw-diag');
    this.rawDiagList = document.getElementById('actions-raw-diag-list');
    this.rawSaveBtn = document.getElementById('actions-raw-save-btn');
    this.rawStatus = document.getElementById('actions-raw-status');
    this.addBtn = document.getElementById('actions-add-trigger');
    this.visualTab = document.getElementById('actions-tab-visual');
    this.rawTab = document.getElementById('actions-tab-raw');
    this.closeBtn = document.getElementById('actions-editor-close');
    this.saveBtn = document.getElementById('actions-editor-save');

    // Add modal elements
    this.addModal = document.getElementById('actions-add-modal');
    this.addModalTitle = document.getElementById('actions-add-title');
    this.addTypeSelect = document.getElementById('actions-add-type');
    this.addGiftPanel = document.getElementById('actions-add-gift-panel');
    this.addEventPanel = document.getElementById('actions-add-event-panel');
    this.addEventName = document.getElementById('actions-add-event-name');
    this.addGiftSearch = document.getElementById('actions-add-gift-search');
    this.addGiftList = document.getElementById('actions-add-gift-list');
    this.addGiftConfirm = document.getElementById('actions-add-gift-confirm');
    this.addGiftCancel = document.getElementById('actions-add-gift-cancel');
    this.addEventConfirm = document.getElementById('actions-add-event-confirm');
    this.addEventCancel = document.getElementById('actions-add-event-cancel');
    this.addError = document.getElementById('actions-add-error');
    this.selectedGiftId = null;

    this._bindEvents();
  }

  _bindEvents() {
    this.closeBtn?.addEventListener('click', () => this.close());
    this.saveBtn?.addEventListener('click', () => this.save());
    this.addBtn?.addEventListener('click', () => this.openAddModal());
    this.visualTab?.addEventListener('click', () => this.switchTab('visual'));
    this.rawTab?.addEventListener('click', () => this.switchTab('raw'));

    this.addTypeSelect?.addEventListener('change', () => this._onAddTypeChange());
    this.addGiftSearch?.addEventListener('input', () => this._renderGiftList());
    this.addGiftConfirm?.addEventListener('click', () => this._confirmAddGift());
    this.addGiftCancel?.addEventListener('click', () => this._closeAddModal());
    this.addEventConfirm?.addEventListener('click', () => this._confirmAddEvent());
    this.addEventCancel?.addEventListener('click', () => this._closeAddModal());
  }

  /* ── Open / Close ── */

  async open() {
    this.el.classList.remove('hidden');
    this.selectedIndex = -1;
    this.isDirty = false;
    this.activeTab = 'visual';
    this.switchTab('visual');
    await this.load();
  }

  async close() {
    if (this.isDirty) {
      const confirmed = await showConfirmDialog('Unsaved Changes', 'You have unsaved changes. Close anyway?', 'Close', 'btn-danger');
      if (!confirmed) return;
    }
    this.el.classList.add('hidden');
  }

  /* ── Data Loading ── */

  async load() {
    try {
      const data = await fetchJSON('/actions');
      this.triggers = data.triggers || [];
      this.isDirty = false;
      this.renderTable();
    } catch (e) {
      showToast('Failed to load actions: ' + e.message, 'error');
    }
  }

  async loadGifts() {
    try {
      const data = await fetchJSON('/gifts');
      this.gifts = data.gifts || [];
      this.gifts.sort((a, b) => (a.coins || 0) - (b.coins || 0) || (a.name || '').localeCompare(b.name || ''));
    } catch (e) {
      showToast('Failed to load gifts: ' + e.message, 'error');
      this.gifts = [];
    }
  }

  async loadRaw() {
    try {
      const data = await fetchJSON('/actions/raw');
      this.rawContent = data.content || '';
      this.rawTextarea.value = this.rawContent;
      this.rawTextarea.disabled = false;
      this._renderRawDiagnostics(data.diagnostics || []);
      this._updateRawStatus(data.diagnostics || []);
    } catch (e) {
      showToast('Failed to load raw actions: ' + e.message, 'error');
    }
  }

  /* ── Tab Switching ── */

  switchTab(tab) {
    this.activeTab = tab;
    this.visualTab?.classList.toggle('active', tab === 'visual');
    this.rawTab?.classList.toggle('active', tab === 'raw');
    document.getElementById('actions-visual-panel')?.classList.toggle('hidden', tab !== 'visual');
    document.getElementById('actions-raw-panel')?.classList.toggle('hidden', tab !== 'raw');
    if (tab === 'raw') this.loadRaw();
  }

  /* ── Table Rendering ── */

  renderTable() {
    if (!this.tableBody) return;
    if (!this.triggers.length) {
      this.tableBody.innerHTML = '<tr><td colspan="4" class="muted" style="text-align:center;padding:2rem;">No triggers defined. Click "Add Event" to create one.</td></tr>';
      this.detailPanel.classList.add('hidden');
      return;
    }

    this.tableBody.innerHTML = this.triggers.map((t, i) => {
      const typeLabel = t.type || 'Custom';
      const cmdSummary = (t.commands || []).length
        ? t.commands.map(c => {
            const prefix = { vanilla: '/', rcon: '!', script: '$', overlay: '>>', named_overlay: `@${c.overlay_name}>>` }[c.type] || '/';
            return prefix + (c.command || '').substring(0, 30);
          }).join('; ')
        : 'No commands';
      return `<tr class="actions-row ${i === this.selectedIndex ? 'selected' : ''} ${t.enabled ? '' : 'disabled'}" data-index="${i}" onclick="actionsEditor.selectTrigger(${i})">
        <td><span class="trigger-type-badge trigger-type-${(t.type || 'custom').toLowerCase()}">${escapeHtml(typeLabel)}</span></td>
        <td>${escapeHtml(t.name)}</td>
        <td>${t.enabled ? '<span class="status-enabled" style="font-size:0.8rem;">Enabled</span>' : '<span class="status-disabled" style="font-size:0.8rem;">Disabled</span>'}</td>
        <td style="font-size:0.85rem;color:var(--text-secondary);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(cmdSummary)}</td>
      </tr>`;
    }).join('');

    if (this.selectedIndex >= 0 && this.selectedIndex < this.triggers.length) {
      this.renderDetail(this.selectedIndex);
    } else if (this.triggers.length > 0) {
      this.selectTrigger(0);
    }
  }

  selectTrigger(index) {
    this.selectedIndex = index;
    this.renderTable();
    this.renderDetail(index);
  }

  /* ── Detail Panel ── */

  renderDetail(index) {
    const t = this.triggers[index];
    if (!t) {
      this.detailPanel.classList.add('hidden');
      return;
    }
    this.detailPanel.classList.remove('hidden');

    let html = `<div class="detail-header">
      <h3>${escapeHtml(t.name)}</h3>
      <div style="display:flex;align-items:center;gap:0.75rem;">
        <button class="detail-delete-btn" onclick="actionsEditor.confirmDeleteTrigger(${index})" title="Delete trigger">Delete</button>
        <label class="detail-toggle">
          <input type="checkbox" class="toggle" ${t.enabled ? 'checked' : ''} onchange="actionsEditor.toggleEnabled(${index})">
          <span>Enabled</span>
        </label>
      </div>
    </div>`;

    html += `<div class="detail-commands"><h4>Commands</h4>`;

    (t.commands || []).forEach((cmd, ci) => {
      const typeOpts = ['vanilla', 'rcon', 'script', 'overlay', 'named_overlay'].map(ot =>
        `<option value="${ot}" ${ot === cmd.type ? 'selected' : ''}>${ot}</option>`
      ).join('');

      html += `<div class="detail-command" data-cmd-index="${ci}">
        <div class="cmd-row">
          <select class="cmd-type" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'type', this.value)">${typeOpts}</select>
          <input class="cmd-input" type="text" value="${escapeHtml(cmd.command)}" placeholder="/command" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'command', this.value)">
          <label class="cmd-mult">x <input type="number" min="1" value="${cmd.multiplier || 1}" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'multiplier', parseInt(this.value) || 1)" style="width:50px;"></label>
          <button class="btn-icon" onclick="actionsEditor.removeCmd(${index}, ${ci})" title="Remove command">&times;</button>
        </div>`;

      if (cmd.type === 'overlay' || cmd.type === 'named_overlay') {
        html += `<div class="cmd-overlay-fields">
          <input type="text" value="${escapeHtml(cmd.title || '')}" placeholder="Title" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'title', this.value)">
          <input type="text" value="${escapeHtml(cmd.subtitle || '')}" placeholder="Subtitle" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'subtitle', this.value)">
          <input type="number" min="1" max="30" value="${cmd.duration || 3}" placeholder="Duration (s)" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'duration', parseInt(this.value) || 3)" style="width:90px;">`;
        if (cmd.type === 'named_overlay') {
          html += `<input type="text" value="${escapeHtml(cmd.overlay_name || 'default')}" placeholder="Overlay name" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'overlay_name', this.value)" style="width:120px;">`;
        }
        html += `</div>`;
      }

      html += `</div>`;
    });

    html += `</div>`;
    html += `<button class="btn btn-secondary" onclick="actionsEditor.addCmd(${index})" style="margin-top:0.5rem;font-size:0.85rem;">+ Add Command</button>`;

    this.detailPanel.innerHTML = html;
  }

  async confirmDeleteTrigger(index) {
    if (index < 0 || index >= this.triggers.length) return;
    const trigger = this.triggers[index];
    const name = trigger.name || 'unnamed';
    const confirmed = await showConfirmDialog(
      'Delete Trigger',
      `Are you sure you want to delete the trigger "${name}"?`,
      'Delete',
      'btn-danger'
    );
    if (!confirmed) return;
    this.removeTrigger(index);
  }

  removeTrigger(index) {
    if (index < 0 || index >= this.triggers.length) return;
    this.triggers.splice(index, 1);
    this.isDirty = true;
    if (this.triggers.length === 0) {
      this.selectedIndex = -1;
      this.renderTable();
      return;
    }
    // Select the same index (now the next item) or the last one
    const nextIndex = Math.min(index, this.triggers.length - 1);
    this.selectedIndex = nextIndex;
    this.renderTable();
  }

  /* ── Trigger mutations ── */

  toggleEnabled(index) {
    if (this.triggers[index]) {
      this.triggers[index].enabled = !this.triggers[index].enabled;
      this.isDirty = true;
      this.renderTable();
    }
  }

  updateCmd(ti, ci, field, value) {
    const cmd = this.triggers[ti]?.commands?.[ci];
    if (cmd) {
      cmd[field] = value;
      this.isDirty = true;
      this.renderTable();
    }
  }

  addCmd(ti) {
    const t = this.triggers[ti];
    if (!t) return;
    if (!t.commands) t.commands = [];
    t.commands.push({ type: 'vanilla', command: '', multiplier: 1, title: '', subtitle: '', duration: 3, overlay_name: 'default' });
    this.isDirty = true;
    this.renderDetail(ti);
    this.renderTable();
  }

  removeCmd(ti, ci) {
    const t = this.triggers[ti];
    if (!t) return;
    t.commands.splice(ci, 1);
    this.isDirty = true;
    this.renderDetail(ti);
    this.renderTable();
  }

  /* ── Add Event Modal (replaces prompt) ── */

  async openAddModal() {
    await this.loadGifts();
    this.selectedGiftId = null;
    this._hideAddError();
    this.addModal.classList.remove('hidden');
    this.addTypeSelect.value = 'event';
    this._onAddTypeChange();
  }

  _closeAddModal() {
    this.addModal.classList.add('hidden');
  }

  _onAddTypeChange() {
    const type = this.addTypeSelect.value;
    const isGift = type === 'gift';
    this.addGiftPanel.classList.toggle('hidden', !isGift);
    this.addEventPanel.classList.toggle('hidden', isGift);
    this.addGiftConfirm.classList.toggle('hidden', !isGift);
    this.addEventConfirm.classList.toggle('hidden', isGift);
    this._hideAddError();

    if (isGift) {
      this.giftSearch = '';
      this.addGiftSearch.value = '';
      this.selectedGiftId = null;
      this.addGiftConfirm.disabled = true;
      if (!this.gifts.length) this.loadGifts().then(() => this._renderGiftList());
      else this._renderGiftList();
    }
  }

  _renderGiftList() {
    if (!this.addGiftList) return;
    const q = (this.addGiftSearch.value || '').toLowerCase().trim();

    const filtered = q
      ? this.gifts.filter(g => g.name.toLowerCase().includes(q) || String(g.id).includes(q))
      : this.gifts;

    if (!filtered.length) {
      this.addGiftList.innerHTML = '<div class="gift-empty">No gifts match your search.</div>';
      return;
    }

    this.addGiftList.innerHTML = filtered.map(g => {
      const imgPath = g.image_url || '';
      const selected = this.selectedGiftId === g.id ? ' gift-item-selected' : '';
      return `<div class="gift-item${selected}" data-gift-id="${g.id}" onclick="actionsEditor._selectGift(${g.id})">
        <img src="${imgPath}" alt="${escapeHtml(g.name)}" class="gift-item-img" loading="lazy" onerror="this.style.display='none'">
        <div class="gift-item-info">
          <div class="gift-item-name">${escapeHtml(g.name)}</div>
          <div class="gift-item-meta">ID: ${g.id} &middot; ${g.coins} coins</div>
        </div>
      </div>`;
    }).join('');
  }

  _selectGift(id) {
    this.selectedGiftId = id;
    this.addGiftConfirm.disabled = false;
    // Update visual selection
    this.addGiftList.querySelectorAll('.gift-item').forEach(el => {
      el.classList.toggle('gift-item-selected', parseInt(el.dataset.giftId) === id);
    });
  }

  _confirmAddGift() {
    if (!this.selectedGiftId) return;
    const gift = this.gifts.find(g => g.id === this.selectedGiftId);
    if (!gift) return;
    const name = gift.name || String(gift.id);
    this._addTrigger(name, 'Gift');
  }

  _confirmAddEvent() {
    const type = this.addTypeSelect.value;
    if (type === 'gift') return;
    if (type !== 'event') {
      this._addTrigger(type, 'Custom');
    } else {
      const eventName = this.addEventName?.value || type;
      this._addTrigger(eventName, 'Event');
    }
  }

  _addTrigger(name, type) {
    if (!name || !name.trim()) return;
    const normalized = name.trim().replace(/^'|'$/g, '').toLowerCase();
    const exists = this.triggers.some(t => {
      const existing = (t.name || '').replace(/^'|'$/g, '').toLowerCase();
      return existing === normalized;
    });
    if (exists) {
      this._showAddError(`A trigger named "${name.trim()}" already exists.`);
      return;
    }
    this._hideAddError();
    this.triggers.push({
      name: name.trim(),
      enabled: true,
      type: type,
      commands: [{ type: 'vanilla', command: '', multiplier: 1, title: '', subtitle: '', duration: 3, overlay_name: 'default' }]
    });
    this.isDirty = true;
    this.renderTable();
    this.selectTrigger(this.triggers.length - 1);
    this._closeAddModal();
  }

  _showAddError(msg) {
    if (!this.addError) return;
    this.addError.textContent = msg;
    this.addError.classList.remove('hidden');
  }

  _hideAddError() {
    if (!this.addError) return;
    this.addError.classList.add('hidden');
  }

  /* ── Save ── */

  async save() {
    if (this.activeTab === 'raw') {
      await this._saveRaw();
    } else {
      await this._saveVisual();
    }
  }

  async _saveVisual() {
    try {
      for (const t of this.triggers) {
        for (const cmd of (t.commands || [])) {
          if (!cmd.command.trim()) {
            showToast('All commands must have a value.', 'error');
            return;
          }
        }
      }

      const body = { triggers: this.triggers };
      await putJSON('/actions', body);
      this.isDirty = false;
      showToast('Actions saved successfully.', 'success');
      await this.load();
    } catch (e) {
      showToast('Failed to save: ' + e.message, 'error');
    }
  }

  /* ── Raw Editor ── */

  async _onRawInput() {
    // Live validation on input, debounced
    if (this._rawInputTimer) clearTimeout(this._rawInputTimer);
    this._rawInputTimer = setTimeout(() => this._validateRawContent(), 400);
  }

  async _validateRawContent() {
    const content = this.rawTextarea?.value || '';
    try {
      const resp = await fetch(API + '/actions/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      if (!resp.ok) return;
      const data = await resp.json();
      this._renderRawDiagnostics(data.diagnostics || []);
      this._updateRawStatus(data.diagnostics || []);
    } catch (_) {}
  }

  _renderRawDiagnostics(diags) {
    if (!this.rawDiagList) return;
    if (!diags.length) {
      this.rawDiagList.innerHTML = '<div class="raw-diag-item raw-diag-ok">No issues found.</div>';
      return;
    }
    this.rawDiagList.innerHTML = diags.map(d => {
      const cls = d.severity === 'ERROR' ? 'raw-diag-error'
        : d.severity === 'WARNING' ? 'raw-diag-warning' : 'raw-diag-info';
      const loc = d.line != null ? `Line ${d.line + 1}` : '';
      return `<div class="raw-diag-item ${cls}">${loc}: ${escapeHtml(d.message)}</div>`;
    }).join('');
  }

  _updateRawStatus(diags) {
    if (!this.rawStatus) return;
    const errors = diags.filter(d => d.severity === 'ERROR').length;
    const warnings = diags.filter(d => d.severity === 'WARNING').length;
    if (errors > 0) {
      this.rawStatus.innerHTML = `<span class="raw-status-error">${errors} error(s) — save blocked</span>`;
      this.rawSaveBtn.disabled = true;
    } else {
      this.rawStatus.innerHTML = warnings > 0
        ? `<span class="raw-status-warn">${warnings} warning(s)</span>`
        : '<span class="raw-status-ok">No errors — can save</span>';
      this.rawSaveBtn.disabled = false;
    }
  }

  async _saveRaw() {
    try {
      const content = this.rawTextarea.value;
      const resp = await fetch(API + '/actions/raw', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      const result = await resp.json();

      if (!resp.ok) {
        // Server rejected (likely 422 due to syntax errors)
        const diags = result.diagnostics || [];
        this._renderRawDiagnostics(diags);
        this._updateRawStatus(diags);
        showToast('Save blocked — fix syntax errors first.', 'error');
        return;
      }

      this.rawContent = content;
      this.isDirty = false;
      this._renderRawDiagnostics(result.diagnostics || []);
      this._updateRawStatus(result.diagnostics || []);
      showToast('Raw actions saved.', 'success');
    } catch (e) {
      showToast('Failed to save raw: ' + e.message, 'error');
    }
  }
}
