class ActionsEditor {
  constructor() {
    this.triggers = [];
    this.selectedIndex = -1;
    this.isDirty = false;
    this.gifts = [];
    this.giftSearch = '';
    this.availableScripts = [];
    this.diagnostics = [];
    this._validateTimer = null;

    this.el = document.getElementById('actions-editor');
    this.tableBody = document.getElementById('actions-table-body');
    this.detailPanel = document.getElementById('actions-detail');
    this.addBtn = document.getElementById('actions-add-trigger');
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
    this.saveBtn?.addEventListener('click', () => this.save());
    this.addBtn?.addEventListener('click', () => this.openAddModal());
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
    await this.load();
    this._updateSaveButton();
  }

  async close() {
    if (this.isDirty) {
      const confirmed = await showConfirmDialog(I18N.t('dialog.unsavedTitle'), I18N.t('dialog.unsavedClose'), I18N.t('common.close'), 'btn-danger');
      if (!confirmed) return;
      this.isDirty = false;
      this._updateSaveButton();
    }
    this.el.classList.add('hidden');
  }

  _updateSaveButton() {
    const btn = document.getElementById('actions-editor-save');
    if (!btn) return;
    const hasErrors = (this.diagnostics || []).some(d => d.severity === 'ERROR');
    const canSave = this.isDirty && !hasErrors;
    btn.disabled = !canSave;
    btn.style.opacity = canSave ? '1' : '0.5';
    btn.style.cursor = canSave ? 'pointer' : 'not-allowed';
    btn.title = hasErrors ? I18N.t('actions.saveBlockedErrors') : '';
  }

  /* ── Validation ── */

  async _validate() {
    try {
      const data = await postJSON('/actions/validate-triggers', { triggers: this.triggers });
      this.diagnostics = data.diagnostics || [];
    } catch (e) {
      this.diagnostics = [];
      console.error(I18N.t('actions.validateFailed', { msg: e.message }));
    }
    this._renderDiagnostics();
    this._updateSaveButton();
  }

  _scheduleValidate() {
    if (this._validateTimer) clearTimeout(this._validateTimer);
    this._validateTimer = setTimeout(() => this._validate(), 400);
  }

  _renderDiagnostics() {
    const panel = document.getElementById('actions-diagnostics');
    if (!panel) return;
    const diags = this.diagnostics || [];
    if (!diags.length) {
      panel.style.display = 'none';
      panel.innerHTML = '';
      return;
    }
    panel.style.display = 'block';
    const errors = diags.filter(d => d.severity === 'ERROR');
    const warnings = diags.filter(d => d.severity === 'WARNING');
    let html = '<div class="actions-diag-summary">';
    if (errors.length) html += `<span class="diag-count diag-errors">${errors.length} ${I18N.t('actions.errors')}</span>`;
    if (warnings.length) html += `<span class="diag-count diag-warnings">${warnings.length} ${I18N.t('actions.warnings')}</span>`;
    html += '</div><ul class="actions-diag-list">';
    diags.forEach(d => {
      const name = this.triggers[d.line] ? (this.triggers[d.line].name || '') : '';
      html += `<li class="diag-${d.severity === 'ERROR' ? 'error' : 'warning'}">
        <span class="diag-badge">${d.severity === 'ERROR' ? I18N.t('actions.error') : I18N.t('actions.warning')}</span>
        <span class="diag-msg">${escapeHtml(d.message)}</span>
        ${name ? `<span class="diag-trigger">(${escapeHtml(name)})</span>` : ''}
      </li>`;
    });
    html += '</ul>';
    panel.innerHTML = html;
  }

  async load() {
    try {
      const data = await fetchJSON('/actions');
      this.triggers = data.triggers || [];
      this.isDirty = false;
      this._updateSaveButton();
      this.renderTable();
    } catch (e) {
      showToast(I18N.t('actions.loadFailed', { msg: e.message }), 'error');
    }
    this._populateScriptDropdowns();
    await this._validate();
  }

  async loadGifts() {
    try {
      const data = await fetchJSON('/gifts');
      this.gifts = data.gifts || [];
      this.gifts.sort((a, b) => (a.coins || 0) - (b.coins || 0) || (a.name || '').localeCompare(b.name || ''));
    } catch (e) {
      showToast(I18N.t('actions.loadGiftsFailed', { msg: e.message }), 'error');
      this.gifts = [];
    }
  }

  /* ── Tab Switching ── */

  /* ── Table Rendering ── */

  renderTable() {
    if (!this.tableBody) return;
    if (!this.triggers.length) {
      this.tableBody.innerHTML = '<tr><td colspan="4" class="muted" style="text-align:center;padding:2rem;">' + I18N.t('actions.noTriggers') + '</td></tr>';
      this.detailPanel.classList.add('hidden');
      return;
    }

    this.tableBody.innerHTML = this.triggers.map((t, i) => {
      const typeLabel = t.type || I18N.t('actions.customOption');
      const cmdSummary = (t.commands || []).length
        ? t.commands.map(c => {
            const prefix = { vanilla: '/', rcon: '!', script: '$', overlay: '>>', named_overlay: `@${c.overlay_name}>>`, shell: '&' }[c.type] || '/';
            let summary = prefix + (c.command || '').substring(0, 30);
            if (c.type === 'vanilla' && c.dynamic_vanilla) summary += ' !rc';
            return summary;
          }).join('; ')
        : I18N.t('actions.noCommands');
      return `<tr class="actions-row ${i === this.selectedIndex ? 'selected' : ''} ${t.enabled ? '' : 'disabled'}" data-index="${i}" onclick="actionsEditor.selectTrigger(${i})">
        <td><span class="trigger-type-badge trigger-type-${(t.type || 'custom').toLowerCase()}">${escapeHtml(typeLabel)}</span></td>
        <td>${escapeHtml(t.name)}</td>
        <td>${t.enabled ? '<span class="status-enabled" style="font-size:0.8rem;">' + I18N.t('actions.enabled') + '</span>' : '<span class="status-disabled" style="font-size:0.8rem;">' + I18N.t('actions.disabled') + '</span>'}</td>
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
        <button class="detail-delete-btn" onclick="actionsEditor.confirmDeleteTrigger(${index})" title="${I18N.t('actions.deleteTrigger')}">${I18N.t('actions.delete')}</button>
        <label class="detail-toggle">
          <input type="checkbox" class="toggle" ${t.enabled ? 'checked' : ''} onchange="actionsEditor.toggleEnabled(${index})">
          <span>${I18N.t('actions.enabled')}</span>
        </label>
      </div>
    </div>`;

    html += `<div class="detail-commands"><h4>${I18N.t('actions.commands')}</h4>`;

    (t.commands || []).forEach((cmd, ci) => {
      const typeLabels = { vanilla: I18N.t('actions.typeVanilla'), rcon: I18N.t('actions.typeRcon'), script: I18N.t('actions.typeScript'), overlay: I18N.t('actions.typeOverlay'), named_overlay: I18N.t('actions.typeNamedOverlay'), shell: I18N.t('actions.typeShell') };
      const typeOpts = ['vanilla', 'rcon', 'script', 'overlay', 'named_overlay', 'shell'].map(ot =>
        `<option value="${ot}" ${ot === cmd.type ? 'selected' : ''}>${typeLabels[ot] || ot}</option>`
      ).join('');

      html += `<div class="detail-command" data-cmd-index="${ci}">
        <div class="cmd-row">
          <select class="cmd-type" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'type', this.value)">${typeOpts}</select>`;

      // For overlay actions, show only overlay-specific fields
      if (cmd.type === 'overlay' || cmd.type === 'named_overlay') {
        html += '<span style="flex:1"></span>';
      } else if (cmd.type === 'script') {
        const currentScript = cmd.command || '';
        html += `<div class="cmd-input-container" style="flex:1;position:relative;display:flex;align-items:center;">
          <input class="cmd-input cmd-script-search" type="text" style="width:100%;"
            value="${escapeHtml(currentScript)}" 
            placeholder="${I18N.t('actions.searchScripts')}"
            data-trigger-idx="${index}"
            data-cmd-idx="${ci}"
            onchange="actionsEditor.updateCmd(${index}, ${ci}, 'command', this.value)"
            onfocus="actionsEditor._showScriptDropdown(event, ${index}, ${ci})"
            oninput="actionsEditor._filterScriptDropdown(event)">
          <div class="cmd-script-dropdown" style="display:none;position:absolute;top:100%;left:0;right:0;">
            <div class="cmd-script-list"></div>
          </div>
        </div>`;
      } else {
        // For vanilla, rcon, shell: show command input
        const placeholders = { 'vanilla': I18N.t('actions.command'), 'rcon': I18N.t('actions.command'), 'shell': I18N.t('actions.shellCommand') };
        const placeholder = placeholders[cmd.type] || I18N.t('actions.command');
        html += `<input class="cmd-input" type="text" value="${escapeHtml(cmd.command)}" placeholder="${placeholder}" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'command', this.value)">`;
      }

      if (cmd.type !== 'overlay' && cmd.type !== 'named_overlay') {
        html += `<label class="cmd-mult">x <input type="number" min="1" value="${cmd.multiplier || 1}" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'multiplier', parseInt(this.value) || 1)" style="width:50px;"></label>`;
      }

      if (cmd.type === 'vanilla') {
        html += `<label class="cmd-rc" title="${I18N.t('actions.dynamicVanillaHint')}">
          <input type="checkbox" ${cmd.dynamic_vanilla ? 'checked' : ''} onchange="actionsEditor.updateCmd(${index}, ${ci}, 'dynamic_vanilla', this.checked)">
          <span>${I18N.t('actions.dynamicVanilla')}</span>
        </label>`;
      }

      html += `<button class="btn-icon" onclick="actionsEditor.removeCmd(${index}, ${ci})" title="${I18N.t('actions.removeCommand')}">&times;</button>
        </div>`;

      if (cmd.type === 'overlay' || cmd.type === 'named_overlay') {
        html += `<div class="cmd-overlay-fields">
          <input type="text" value="${escapeHtml(cmd.title || '')}" placeholder="${I18N.t('actions.titleField')}" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'title', this.value)">
          <input type="text" value="${escapeHtml(cmd.subtitle || '')}" placeholder="${I18N.t('actions.subtitleField')}" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'subtitle', this.value)">
          <input type="number" min="1" max="30" value="${cmd.duration || 3}" placeholder="${I18N.t('actions.durationField')}" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'duration', parseInt(this.value) || 3)" style="width:90px;">`;
        if (cmd.type === 'named_overlay') {
          html += `<input type="text" value="${escapeHtml(cmd.overlay_name || 'default')}" placeholder="${I18N.t('actions.overlayNameField')}" onchange="actionsEditor.updateCmd(${index}, ${ci}, 'overlay_name', this.value)" style="width:120px;">`;
        }
        html += `</div>`;
      }

      html += `</div>`;
    });

    html += `</div>`;
    html += `<button class="btn btn-secondary" onclick="actionsEditor.addCmd(${index})" style="margin-top:0.5rem;font-size:0.85rem;">${I18N.t('actions.addCommand')}</button>`;

    this.detailPanel.innerHTML = html;

    // Populate script dropdowns after rendering
    this._populateScriptDropdowns();
  }

  async _populateScriptDropdowns() {
    try {
      const data = await fetchJSON('/actions/scripts');
      this.availableScripts = data.scripts || [];
    } catch (e) {
      console.error(I18N.t('actions.loadScriptsFailed', { msg: e.message }));
      this.availableScripts = [];
    }
  }

  _showScriptDropdown(event, triggerIdx, cmdIdx) {
    const input = event.target;
    const dropdown = input.nextElementSibling;

    const listContainer = dropdown.querySelector('.cmd-script-list');
    if (!listContainer) return;

    const query = input.value.toLowerCase().trim();
    const scripts = this.availableScripts || [];

    // Filter scripts
    const filtered = query
      ? scripts.filter(s => s.name.toLowerCase().includes(query))
      : scripts;

    // Render filtered list
    if (filtered.length === 0) {
      listContainer.innerHTML = '<div style="padding:0.5rem;color:var(--text-secondary);font-size:0.85rem;">' + I18N.t('actions.noScripts') + '</div>';
    } else {
      listContainer.innerHTML = filtered.map(script => `
        <div class="cmd-script-option" data-script-name="${escapeHtml(script.name)}"
          onclick="actionsEditor._selectScript(event, '${escapeHtml(script.name)}')">
          ${escapeHtml(script.name)}
        </div>
      `).join('');
    }

    dropdown.style.display = 'block';

    // Close dropdown when clicking outside. Installed once per editor
    // instance — NOT per rendered input (renderDetail() recreates the
    // inputs on every keystroke, which would leak document listeners).
    this._ensureDropdownCloseHandler();
  }

  _ensureDropdownCloseHandler() {
    if (this._dropdownCloseHandler) return;
    this._dropdownCloseHandler = true;
    document.addEventListener('click', (e) => {
      const searchInputs = document.querySelectorAll('.cmd-script-search');
      searchInputs.forEach(inp => {
        const dd = inp.nextElementSibling;
        if (dd && dd.classList.contains('cmd-script-dropdown')) {
          if (!inp.contains(e.target) && !dd.contains(e.target)) {
            dd.style.display = 'none';
          }
        }
      });
    });
  }

  _selectScript(event, scriptName) {
    event.stopPropagation();
    const option = event.target;
    const dropdown = option.closest('.cmd-script-dropdown');
    const input = dropdown?.previousElementSibling;
    
    if (!input || !input.classList.contains('cmd-script-search')) return;

    input.value = scriptName;
    dropdown.style.display = 'none';

    // Extract indices from data attributes
    const triggerIdx = parseInt(input.dataset.triggerIdx);
    const cmdIdx = parseInt(input.dataset.cmdIdx);
    
    this.updateCmd(triggerIdx, cmdIdx, 'command', scriptName);
  }

  _filterScriptDropdown(event) {
    const input = event.target;
    const triggerIdx = parseInt(input.dataset.triggerIdx);
    const cmdIdx = parseInt(input.dataset.cmdIdx);
    this._showScriptDropdown(event, triggerIdx, cmdIdx);
  }

  async confirmDeleteTrigger(index) {
    if (index < 0 || index >= this.triggers.length) return;
    const trigger = this.triggers[index];
    const name = trigger.name || I18N.t('actions.unnamed');
    const confirmed = await showConfirmDialog(
      I18N.t('actions.deleteTitle'),
      I18N.t('actions.deleteConfirm', { name }),
      I18N.t('actions.delete'),
      'btn-danger'
    );
    if (!confirmed) return;
    this.removeTrigger(index);
  }

  removeTrigger(index) {
    if (index < 0 || index >= this.triggers.length) return;
    this.triggers.splice(index, 1);
    this.isDirty = true;
    this._updateSaveButton();
    this._scheduleValidate();
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

  async toggleEnabled(index) {
    const t = this.triggers[index];
    if (!t) return;

    // Enabling a trigger that is already enabled elsewhere would create a duplicate
    if (!t.enabled) {
      const normalized = (t.name || '').replace(/^'|'$/g, '').toLowerCase();
      const duplicate = this.triggers.find((other, i) =>
        i !== index &&
        other.enabled &&
        (other.name || '').replace(/^'|'$/g, '').toLowerCase() === normalized
      );
      if (duplicate) {
        showToast(I18N.t('actions.duplicateToast', { name: t.name }), 'warning');
        const deleteDuplicate = await showConfirmDialog(
          I18N.t('actions.duplicateTitle'),
          I18N.t('actions.duplicateMessage', { name: t.name }),
          I18N.t('actions.deleteDuplicate'),
          'btn-danger'
        );
        if (deleteDuplicate) {
          this.removeTrigger(index);
        }
        else {
          this.triggers[index].enabled = false;
          this.renderTable();
        }
        return;
      }
    }

    t.enabled = !t.enabled;
    this.isDirty = true;
    this._updateSaveButton();
    this.renderTable();
    this._scheduleValidate();
  }

  updateCmd(ti, ci, field, value) {
    const cmd = this.triggers[ti]?.commands?.[ci];
    if (cmd) {
      cmd[field] = value;
      this.isDirty = true;
    this._updateSaveButton();
      this.renderTable();
      this._scheduleValidate();
    }
  }

  addCmd(ti) {
    const t = this.triggers[ti];
    if (!t) return;
    if (!t.commands) t.commands = [];
    t.commands.push({ type: 'vanilla', command: '', multiplier: 1, title: '', subtitle: '', duration: 3, overlay_name: 'default' });
    this.isDirty = true;
    this._updateSaveButton();
    this.renderDetail(ti);
    this.renderTable();
    this._scheduleValidate();
  }

  removeCmd(ti, ci) {
    const t = this.triggers[ti];
    if (!t) return;
    t.commands.splice(ci, 1);
    this.isDirty = true;
    this._updateSaveButton();
    this.renderDetail(ti);
    this.renderTable();
    this._scheduleValidate();
  }

  /* ── Add Event Modal (replaces prompt) ── */

  async openAddModal() {
    await this.loadGifts();
    this.selectedGiftId = null;
    this._hideAddError();
    this.addModal.classList.remove('hidden');
    this.addTypeSelect.value = 'event';
    this._populateEventSelect();
    this._onAddTypeChange();
  }

  _populateEventSelect() {
    const select = document.getElementById('actions-add-event-name');
    const customInput = document.getElementById('actions-add-event-custom');
    if (!select) return;
    // Build set of known events plus any existing custom triggers
    const known = ['follow','join','comment','likes','like_2','share'];
    const existing = new Set();
    for (const t of this.triggers) {
      if (t.type === 'Event' || t.type === 'Custom') {
        const name = (t.name || '').toLowerCase().replace(/^'|'$/g, '');
        if (name && !known.includes(name)) existing.add(name);
      }
    }
    // Sort custom like triggers numerically
    const customLikes = Array.from(existing).filter(n => n.startsWith('like_')).sort((a,b) => {
      const na = parseInt(a.replace('like_','')) || 0;
      const nb = parseInt(b.replace('like_','')) || 0;
      return na - nb;
    });
    const others = Array.from(existing).filter(n => !n.startsWith('like_')).sort();
    let html = '';
    for (const ev of known) html += `<option value="${ev}">${ev.charAt(0).toUpperCase() + ev.slice(1)}</option>`;
    if (customLikes.length) {
      html += `<optgroup label="${I18N.t('actions.customLikes')}">`;
      for (const ev of customLikes) html += `<option value="${ev}">${ev}</option>`;
      html += `</optgroup>`;
    }
    if (others.length) {
      html += `<optgroup label="${I18N.t('actions.customEvents')}">`;
      for (const ev of others) html += `<option value="${ev}">${ev}</option>`;
      html += `</optgroup>`;
    }
    html += `<option value="__custom__">${I18N.t('actions.customOption')}</option>`;
    select.innerHTML = html;
    select.onchange = () => {
      const isCustom = select.value === '__custom__';
      if (customInput) customInput.classList.toggle('hidden', !isCustom);
      if (isCustom && customInput) customInput.focus();
    };
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
      this.addGiftList.innerHTML = '<div class="gift-empty">' + I18N.t('triggers.noGifts') + '</div>';
      return;
    }

    this.addGiftList.innerHTML = filtered.map(g => {
      const imgPath = escapeHtml(g.image_url || '');
      const giftId = escapeHtml(String(g.id));
      const selected = this.selectedGiftId === g.id ? ' gift-item-selected' : '';
      return `<div class="gift-item${selected}" data-gift-id="${giftId}">
        <img src="${imgPath}" alt="${escapeHtml(g.name)}" class="gift-item-img" loading="lazy" onerror="this.style.display='none'">
        <div class="gift-item-info">
          <div class="gift-item-name">${escapeHtml(g.name)}</div>
          <div class="gift-item-meta">ID: ${giftId} &middot; ${escapeHtml(String(g.coins))} coins</div>
        </div>
      </div>`;
    }).join('');

    this.addGiftList.removeEventListener('click', this._boundGiftClick);
    this._boundGiftClick = (e) => {
      const item = e.target.closest('.gift-item');
      if (!item) return;
      this._selectGift(parseInt(item.dataset.giftId));
    };
    this.addGiftList.addEventListener('click', this._boundGiftClick);
  }

  _selectGift(id) {
    this.selectedGiftId = id;
    this.addGiftConfirm.disabled = false;
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
      return;
    }
    const select = document.getElementById('actions-add-event-name');
    const customInput = document.getElementById('actions-add-event-custom');
    let eventName = select?.value || '';
    if (eventName === '__custom__') {
      eventName = customInput?.value?.trim() || '';
    }
    if (!eventName) {
      this._showAddError(I18N.t('actions.selectEventError'));
      return;
    }
    this._addTrigger(eventName, 'Event');
  }

  _addTrigger(name, type) {
    if (!name || !name.trim()) return;
    const normalized = name.trim().replace(/^'|'$/g, '').toLowerCase();
    const exists = this.triggers.some(t => {
      const existing = (t.name || '').replace(/^'|'$/g, '').toLowerCase();
      return existing === normalized;
    });
    if (exists) {
      this._showAddError(I18N.t('actions.triggerExists', { name: name.trim() }));
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
    this._updateSaveButton();
    this.renderTable();
    this.selectTrigger(this.triggers.length - 1);
    this._closeAddModal();
    this._scheduleValidate();
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
    await this._saveVisual();
  }

  async _saveVisual() {
    try {
      for (const t of this.triggers) {
        for (const cmd of (t.commands || [])) {
          if (!cmd.command.trim()) {
            showToast(I18N.t('actions.allCommandsValue'), 'error');
            return;
          }
        }
      }

      await this._validate();
      if (this.diagnostics.some(d => d.severity === 'ERROR')) {
        showToast(I18N.t('actions.saveBlockedErrors'), 'error');
        return;
      }

      const body = { triggers: this.triggers };
      await putJSON('/actions', body);
      await this._askAndReloadActions();
      this.isDirty = false;
      this._updateSaveButton();
      await this.load();
    } catch (e) {
      showToast(I18N.t('actions.saveFailed', { msg: e.message }), 'error');
    }
  }

  async _askAndReloadActions() {
    let sendReload = false;
    if (currentConfig && currentConfig.rcon && currentConfig.rcon.enabled) {
      sendReload = await this._askServerRestart();
    }
    await postJSON('/reload', { config: false, actions: true, send_minecraft_reload: sendReload });
    if (sendReload) {
      showToast(I18N.t('actions.savedReload'), 'success');
    } else {
      showToast(I18N.t('actions.savedRunReload'), 'info');
      setRestartPending(true);
    }
  }

  _askServerRestart() {
    const dlg = document.getElementById('actions-restart-dialog');
    const nowBtn = document.getElementById('btn-actions-restart-now');
    const laterBtn = document.getElementById('btn-actions-restart-later');
    if (!dlg || !nowBtn || !laterBtn) {
      return Promise.resolve(confirm(I18N.t('actions.restartMessage')));
    }
    return new Promise((resolve) => {
      const cleanup = () => {
        dlg.classList.add('hidden');
        document.removeEventListener('keydown', onKey);
        nowBtn.replaceWith(nowBtn.cloneNode(true));
        laterBtn.replaceWith(laterBtn.cloneNode(true));
      };
      const onKey = (e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          cleanup();
          resolve(false);
        }
      };

      const newNow = nowBtn.cloneNode(true);
      const newLater = laterBtn.cloneNode(true);
      nowBtn.parentNode.replaceChild(newNow, nowBtn);
      laterBtn.parentNode.replaceChild(newLater, laterBtn);

      newNow.addEventListener('click', () => { cleanup(); resolve(true); });
      newLater.addEventListener('click', () => { cleanup(); resolve(false); });

      dlg.classList.remove('hidden');
      document.addEventListener('keydown', onKey);
    });
  }

  /* ── Raw Editor ── (removed) */
}
