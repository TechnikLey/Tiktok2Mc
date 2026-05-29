class ActionsEditor {
  constructor() {
    this.triggers = [];
    this.selectedIndex = -1;
    this.isDirty = false;
    this.rawContent = '';
    this.activeTab = 'visual'; // 'visual' | 'raw'

    this.el = document.getElementById('actions-editor');
    this.tableBody = document.getElementById('actions-table-body');
    this.detailPanel = document.getElementById('actions-detail');
    this.rawEditor = document.getElementById('actions-raw-editor');
    this.rawTextarea = document.getElementById('actions-raw-text');
    this.rawDiag = document.getElementById('actions-raw-diag');
    this.addBtn = document.getElementById('actions-add-trigger');
    this.visualTab = document.getElementById('actions-tab-visual');
    this.rawTab = document.getElementById('actions-tab-raw');
    this.closeBtn = document.getElementById('actions-editor-close');
    this.saveBtn = document.getElementById('actions-editor-save');

    this._bindEvents();
  }

  _bindEvents() {
    this.closeBtn?.addEventListener('click', () => this.close());
    this.saveBtn?.addEventListener('click', () => this.save());
    this.addBtn?.addEventListener('click', () => this.addTrigger());
    this.visualTab?.addEventListener('click', () => this.switchTab('visual'));
    this.rawTab?.addEventListener('click', () => this.switchTab('raw'));
  }

  async open() {
    this.el.classList.remove('hidden');
    this.selectedIndex = -1;
    this.isDirty = false;
    this.activeTab = 'visual';
    this.switchTab('visual');
    await this.load();
  }

  close() {
    if (this.isDirty) {
      const msg = 'You have unsaved changes. Close anyway?';
      if (!confirm(msg)) return;
    }
    this.el.classList.add('hidden');
  }

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

  async loadRaw() {
    try {
      const data = await fetchJSON('/actions/raw');
      this.rawContent = data.content || '';
      this.rawTextarea.value = this.rawContent;
      this.renderDiagnostics(data.diagnostics || []);
    } catch (e) {
      showToast('Failed to load raw actions: ' + e.message, 'error');
    }
  }

  renderDiagnostics(diags) {
    if (!this.rawDiag) return;
    if (!diags.length) {
      this.rawDiag.innerHTML = '<div class="raw-diag-item raw-diag-ok">No issues found.</div>';
      return;
    }
    this.rawDiag.innerHTML = diags.map(d => {
      const cls = d.severity === 'error' ? 'raw-diag-error'
        : d.severity === 'warning' ? 'raw-diag-warning' : 'raw-diag-info';
      const loc = d.line ? `Line ${d.line}` : '';
      return `<div class="raw-diag-item ${cls}">${loc}: ${escapeHtml(d.message)}</div>`;
    }).join('');
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
      const cmdCount = (t.commands || []).length;
      const cmdSummary = cmdCount
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

    // Re-select if we had a selection
    if (this.selectedIndex >= 0 && this.selectedIndex < this.triggers.length) {
      this.renderDetail(this.selectedIndex);
    } else if (this.triggers.length > 0) {
      this.selectTrigger(0);
    }
  }

  selectTrigger(index) {
    this.selectedIndex = index;
    this.renderTable(); // re-render to update .selected class
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
      <label class="detail-toggle">
        <input type="checkbox" class="toggle" ${t.enabled ? 'checked' : ''} onchange="actionsEditor.toggleEnabled(${index})">
        <span>Enabled</span>
      </label>
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

      // Overlay fields
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

  addTrigger() {
    const name = prompt('Enter trigger name (e.g. follow, 100 for gift):');
    if (!name || !name.trim()) return;
    this.triggers.push({
      name: name.trim(),
      enabled: true,
      type: name.trim().match(/^\d+$/) ? 'Gift' : 'Event',
      commands: [{ type: 'vanilla', command: '', multiplier: 1, title: '', subtitle: '', duration: 3, overlay_name: 'default' }]
    });
    this.isDirty = true;
    this.renderTable();
    this.selectTrigger(this.triggers.length - 1);
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
      // Validate: ensure no command is empty
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

  async _saveRaw() {
    try {
      const content = this.rawTextarea.value;
      const result = await putJSON('/actions/raw', { content });
      this.rawContent = content;
      this.isDirty = false;
      this.renderDiagnostics(result.diagnostics || []);
      showToast('Raw actions saved.', 'success');
    } catch (e) {
      showToast('Failed to save raw: ' + e.message, 'error');
    }
  }
}
