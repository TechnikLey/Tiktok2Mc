/**
 * @file Comment-command editor.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ════════════════════════════════════════════════════════════════════
   Comment Commands Editor
   ════════════════════════════════════════════════════════════════════ */

/**
 * Editor for comment-command groups.
 *
 * Manages global enable/cooldown settings, plugin references, inline overrides and the three-step create/edit wizard.
 */
class CommentCommandsEditor {
  /** Create the comment-command editor and cache its DOM elements. */
  constructor() {
    this.el = document.getElementById('comment-commands-editor');
    this.content = document.getElementById('cc-content');
    this.sidebar = document.getElementById('cc-sidebar-categories');
    this.data = { enabled: false, cooldown: 0, user_cooldown: 0, groups: [] };
    this.original = JSON.parse(JSON.stringify(this.data));
    this._dirty = false;
    this.searchQuery = '';
    this.activeCategory = 'all';
    this._wizardMode = null;
    this._wizardIndex = null;
    this._wizardStep = 0;
    this._wizardDraft = {};
    this._expandedOverride = null;
    this._pluginCatalog = {};
    this._refPanelOpen = false;
    this._openPluginRefPanels = new Set();
    this._bindEvents();
  }

  /** Wire navigation, search, save and wizard controls. */
  _bindEvents() {
    document.getElementById('cc-add')?.addEventListener('click', () => this.startCreate());
    document.getElementById('cc-group-cancel')?.addEventListener('click', () => this._closeWizard());
    document.getElementById('cc-group-next')?.addEventListener('click', () => this._wizardNext());
    document.getElementById('cc-group-back')?.addEventListener('click', () => this._wizardBack());
    document.getElementById('cc-delete-cancel')?.addEventListener('click', () => this._hideDeleteModal());
  }

  /** Open the editor and load the current configuration. */
  async open() {
    this.el.classList.remove('hidden');
    await this.load();
  }

  /** Close the editor and discard transient state. */
  close() {
    if (this._dirty) {
      showConfirmDialog(I18N.t('dialog.unsavedTitle'), I18N.t('dialog.unsavedClose'), I18N.t('common.close'), 'btn-danger').then(confirmed => {
        if (!confirmed) return;
        this._dirty = false;
        this._updateSaveButton();
        this.el.classList.add('hidden');
      });
      return;
    }
    this.el.classList.add('hidden');
  }

  /** Fetch comment-command groups and render the editor. */
  async load() {
    try {
      const res = await fetchJSON('/comment-commands');
      this.data = JSON.parse(JSON.stringify(res.comment_commands || { enabled: false, cooldown: 0, user_cooldown: 0, groups: [] }));
      this.original = JSON.parse(JSON.stringify(this.data));
      this._dirty = false;
      this._updateSaveButton();
      this._expandedOverride = null;
      this.renderSidebar();
      this.renderList();
    } catch (e) {
      showToast(I18N.t('cc.loadFailed', { msg: e.message }), 'error');
    }
    this._loadPluginCatalog();
  }

  /** Load the plugin catalog used by command references. */
  async _loadPluginCatalog() {
    try {
      const res = await fetchJSON('/reactions/catalog');
      this._pluginCatalog = res.commands || {};
    } catch (e) {
      this._pluginCatalog = {};
    }
  }

  /** Return whether the editor has unsaved changes. */
  isDirty() { return this._dirty; }

  /** Apply a search query to the group list. */
  onSearch(q) { this.searchQuery = q.trim().toLowerCase(); this.renderList(); }

  /** Update the save button from dirty state. */
  _updateSaveButton() {
    const btn = document.getElementById('cc-save');
    if (!btn) return;
    const dirty = this._dirty;
    btn.disabled = !dirty;
    btn.style.opacity = dirty ? '1' : '0.5';
    btn.style.cursor = dirty ? 'pointer' : 'not-allowed';
  }

  /** Populate a plugin select with the available plugins. */
  async _loadPluginsForSelect(selectEl, current) {
    try {
      const res = await fetchJSON('/plugins');
      const plugins = res.plugins || [];
      let html = '<option value="">—</option>';
      for (const p of plugins) {
        const sel = p.name === current ? ' selected' : '';
        html += `<option value="${escapeHtml(p.name)}"${sel}>${escapeHtml(p.name)}</option>`;
      }
      selectEl.innerHTML = html;
    } catch (e) { /* ignore */ }
  }

  /* ─── Sidebar ─── */
  /** Render the all/system/plugin category filters. */
  renderSidebar() {
    const groups = this.data.groups || [];
    let sysCount = 0, plugCount = 0;
    for (const g of groups) {
      const h = (g.handler || '').toLowerCase();
      if (h === 'rcon' || h === 'http') sysCount++; else plugCount++;
    }
    const total = groups.length;
    const cats = [['all', total], ['system', sysCount], ['plugin', plugCount]].filter(([, c]) => c > 0);
    let html = '';
    for (const [key, count] of cats) {
      const active = this.activeCategory === key ? 'active' : '';
      const label = key === 'all' ? I18N.t('cc.catAll') : key === 'system' ? I18N.t('cc.catSystem') : I18N.t('cc.catPlugin');
      html += `<div class="sidebar-filter ${active}" onclick="commentCommandsEditor.setCategory('${key}')">
        <span>${escapeHtml(label)}</span><span class="badge">${count}</span>
      </div>`;
    }
    this.sidebar.innerHTML = html;
  }

  /** Select a command category and re-render. */
  setCategory(cat) { this.activeCategory = cat; this.renderSidebar(); this.renderList(); }

  /* ─── List ─── */
  /** Render comment-command groups matching the active category and search. */
  renderList() {
    const groups = this.data.groups || [];
    const filtered = groups.filter((g, i) => {
      g._index = i;
      const h = (g.handler || '').toLowerCase();
      const cat = (h === 'rcon' || h === 'http') ? 'system' : 'plugin';
      if (this.activeCategory !== 'all' && this.activeCategory !== cat) return false;
      if (this.searchQuery) {
        const q = this.searchQuery;
        if ((g.prefix || '').includes(q)) return true;
        if ((g.commands || []).some(c => c.toLowerCase().includes(q))) return true;
        return false;
      }
      return true;
    });

    if (!filtered.length) {
      const isFiltered = this.searchQuery || this.activeCategory !== 'all';
      this.content.innerHTML = `<div class="reaction-empty">
        <h3>${isFiltered ? I18N.t('cc.noResults') : I18N.t('cc.noneYet')}</h3>
        <p>${isFiltered ? I18N.t('cc.noResultsDesc') : I18N.t('cc.emptyDesc')}</p>
        ${!isFiltered ? `<button class="btn btn-primary" style="margin-top:1.5rem;padding:0.7rem 1.4rem;" onclick="commentCommandsEditor.startCreate()">${I18N.t('cc.createYourFirst')}</button>` : ''}
      </div>`;
      return;
    }

    let html = this._renderGlobalSettings();
    for (const g of filtered) {
      html += this._renderGroupPanel(g);
    }
    this.content.innerHTML = html;
  }

  /** Render the detail panel for one comment-command group. */
  _renderGroupPanel(g) {
    const i = g._index;
    const h = (g.handler || '').toLowerCase();
    const isSystem = h === 'rcon' || h === 'http';
    const catClass = isSystem ? 'reaction-category-minecraft' : 'reaction-category-custom';
    const catLabel = isSystem ? I18N.t('cc.catSystem') : I18N.t('cc.catPlugin');
    const handlerLabel = h === 'rcon' ? 'RCON' : h === 'http' ? 'HTTP' : h === 'plugin' ? `Plugin: ${escapeHtml(g.plugin_name || '—')}` : h;
    const prefixDisplay = escapeHtml(g.prefix || '#');
    const roles = (g.allowed_roles || []).join(', ');
    const modeLabel = g.mode || 'deny-all';
    const disabledClass = !g.enabled ? ' cc-group-panel--disabled' : '';
    const cmds = g.commands || [];
    const config = g.commands_config || {};
    const isExpanded = (ed) => this._expandedOverride && this._expandedOverride.groupIdx === i && this._expandedOverride.cmdName === ed;

    let panelHtml = `<div class="cc-group-panel${disabledClass}">`;

    /* Header */
    panelHtml += `<div class="cc-group-header">
      <div class="cc-group-header-left">
        <span class="cc-group-prefix">${prefixDisplay}</span>
        <div class="cc-group-meta">
          <span class="reaction-category-badge ${catClass}">${escapeHtml(catLabel)}</span>
          <span class="cc-group-meta-sep">·</span>
          <span>${escapeHtml(handlerLabel)}</span>
        </div>
      </div>
      <div class="cc-group-header-actions">
        <button class="reaction-btn-sm reaction-btn-edit" onclick="commentCommandsEditor.startEdit(${i})">${I18N.t('cc.editGroup')}</button>
        <button class="reaction-btn-sm reaction-btn-delete" onclick="commentCommandsEditor.confirmDelete(${i})">${I18N.t('cc.delete')}</button>
      </div>
    </div>`;

    /* Disabled notice */
    if (!g.enabled) {
      panelHtml += `<div class="reaction-disabled-notice">${I18N.t('cc.groupDisabled')}</div>`;
    }

    /* Info bar */
    panelHtml += `<div class="cc-group-info">
      <div class="cc-group-info-item"><span class="cc-group-info-label">${I18N.t('cc.roles')}:</span> ${escapeHtml(roles)}</div>
      <div class="cc-group-info-item"><span class="cc-group-info-label">${I18N.t('cc.mode')}:</span> ${escapeHtml(modeLabel)}</div>
      ${g.cooldown ? `<div class="cc-group-info-item"><span class="cc-group-info-label">${I18N.t('cc.cooldown')}:</span> ${g.cooldown}s</div>` : ''}
      ${g.user_cooldown ? `<div class="cc-group-info-item"><span class="cc-group-info-label">${I18N.t('cc.userCooldown')}:</span> ${g.user_cooldown}s</div>` : ''}
    </div>`;

    /* Commands table */
    panelHtml += `<div class="cc-group-commands">`;
    if (cmds.length) {
      panelHtml += `<div class="cc-group-cmd-header">
        <span>${I18N.t('cc.commands')}</span>
        <span>${I18N.t('cc.cooldown')}</span>
        <span>${I18N.t('cc.cmdOverrideRoles')}</span>
        <span>${I18N.t('cc.handler')}</span>
        <span></span>
      </div>`;
      for (const cmd of cmds) {
        const cfg = config[cmd] || {};
        const hasOverrides = Object.keys(cfg).length > 0;
        const expanded = isExpanded(cmd);
        const cdDisplay = cfg.cooldown != null ? `${cfg.cooldown}s` : '—';
        const rolesDisplay = cfg.roles ? cfg.roles.join(', ') : '—';
        const handlerDisplay = cfg.handler || '—';

        const cdClass = cfg.cooldown != null ? 'cc-group-cmd-td cc-group-cmd-td-override' : 'cc-group-cmd-td';
        const rolesClass = cfg.roles ? 'cc-group-cmd-td cc-group-cmd-td-override' : 'cc-group-cmd-td';
        const handlerClass = cfg.handler ? 'cc-group-cmd-td cc-group-cmd-td-override' : 'cc-group-cmd-td';

        panelHtml += `<div class="cc-group-cmd-row" id="cc-cmd-row-${i}-${escapeHtml(cmd)}">
          <div class="cc-group-cmd-name">
            ${hasOverrides ? '<span class="cc-group-cmd-override-dot" title="Has overrides"></span>' : ''}
            ${escapeHtml(cmd)}
          </div>
          <span class="${cdClass}">${cdDisplay}</span>
          <span class="${rolesClass}">${rolesDisplay}</span>
          <span class="${handlerClass}">${handlerDisplay}</span>
          <div class="cc-group-cmd-actions">
            <button class="cc-group-cmd-btn" title="${I18N.t('cc.cmdEditOverrides')}" onclick="commentCommandsEditor.toggleOverride(${i},'${escapeHtml(cmd)}')">
              ${expanded ? '&#9650;' : '&#9660;'}
            </button>
            <button class="cc-group-cmd-btn cc-group-cmd-btn--danger" title="${I18N.t('cc.cmdRemove')}" onclick="commentCommandsEditor.removeCommand(${i},'${escapeHtml(cmd)}')">
              &times;
            </button>
          </div>
        </div>`;

        /* Inline override panel */
        if (expanded) {
          panelHtml += this._renderInlineOverridePanel(i, cmd, cfg, g);
        }
      }
    } else {
      panelHtml += `<div class="cc-group-cmd-empty">${I18N.t('cc.noCommands')}</div>`;
    }

    /* Add command row */
    panelHtml += `<div class="cc-group-cmd-add">
      <input type="text" class="cc-group-cmd-add-input" id="cc-add-cmd-${i}" placeholder="${I18N.t('cc.commandsPlaceholder')}"
        onkeydown="if(event.key==='Enter'){event.preventDefault();commentCommandsEditor.addCommand(${i},this.value);this.value='';}">
      <button class="cc-group-cmd-add-btn" onclick="const inp=document.getElementById('cc-add-cmd-${i}');commentCommandsEditor.addCommand(${i},inp.value);inp.value='';">
        + ${I18N.t('cc.cmdAdd')}
      </button>
    </div>`;

    /* Plugin commands suggestions (inline) */
    if (h === 'plugin' && g.plugin_name && this._pluginCatalog[g.plugin_name]) {
      const pcmds = this._pluginCatalog[g.plugin_name];
      const pkeys = Object.keys(pcmds);
      if (pkeys.length) {
        const isOpen = this._openPluginRefPanels.has(i);
        panelHtml += `<div class="cc-plugin-commands-ref" style="margin-top:var(--space-3);">
          <div class="cc-plugin-commands-ref-header" onclick="commentCommandsEditor._toggleInlinePluginRef(${i})">
            <h4><span class="mi" style="font-size:14px;">extension</span> ${I18N.t('cc.availableCommands')} — ${escapeHtml(g.plugin_name)}</h4>
            <span class="cc-ref-toggle${isOpen ? ' open' : ''}">▾</span>
          </div>
          <div class="cc-plugin-commands-ref-body${isOpen ? ' open' : ''}">
            ${pkeys.map(k => {
              const c = pcmds[k];
              const alreadyAdded = cmds.includes(k);
              return `<div class="cc-plugin-cmd-item">
                <span class="cc-plugin-cmd-name" data-cmd="${escapeHtml(k)}" ${alreadyAdded ? 'style="opacity:0.4;cursor:default;"' : `onclick="commentCommandsEditor.addCommand(${i},'${escapeHtml(k)}')"`} title="${alreadyAdded ? 'Already added' : 'Click to add'}">${escapeHtml(k)}${alreadyAdded ? ' ✓' : ''}</span>
                <span class="cc-plugin-cmd-desc">${escapeHtml(c.desc || c.name || '')}</span>
              </div>`;
            }).join('')}
          </div>
        </div>`;
      }
    }

    panelHtml += `</div></div>`;
    return panelHtml;
  }

  /** Render the inline override panel for one command. */
  _renderInlineOverridePanel(groupIdx, cmd, cfg, group) {
    const cdVal = cfg.cooldown != null ? cfg.cooldown : '';
    const handlerVal = cfg.handler || '';
    const urlVal = cfg.url || '';
    const roles = cfg.roles || [];
    const dataAttr = `data-gi="${groupIdx}" data-cmd="${escapeHtml(cmd)}"`;

    return `<div class="cc-override-panel" ${dataAttr}>
      <div class="cc-override-field">
        <label>${I18N.t('cc.cmdOverrideCooldown')}</label>
        <input type="number" class="cc-ov-cooldown" min="0" value="${cdVal}" placeholder="${I18N.t('cc.cmdOverrideUseGroup')}">
      </div>
      <div class="cc-override-field cc-override-roles">
        <label>${I18N.t('cc.cmdOverrideRoles')}</label>
        <div class="cc-ov-role-toggles">
          ${['all', 'moderator', 'superfan', 'fanclub'].map(r => `<label class="cc-ov-role-toggle"><input type="checkbox" class="cc-ov-role-cb" value="${r}" ${roles.includes(r) ? 'checked' : ''}> ${r}</label>`).join('')}
        </div>
      </div>
      <div class="cc-override-field">
        <label>${I18N.t('cc.cmdOverrideHandler')}</label>
        <select class="cc-ov-handler">
          <option value="" ${!handlerVal ? 'selected' : ''}>${I18N.t('cc.cmdOverrideUseGroup')}</option>
          <option value="rcon" ${handlerVal === 'rcon' ? 'selected' : ''}>RCON</option>
          <option value="http" ${handlerVal === 'http' ? 'selected' : ''}>HTTP</option>
          <option value="plugin" ${handlerVal === 'plugin' ? 'selected' : ''}>Plugin</option>
        </select>
      </div>
      <div class="cc-override-field">
        <label>${I18N.t('cc.cmdOverrideUrl')}</label>
        <input type="text" class="cc-ov-url" value="${escapeHtml(urlVal)}" placeholder="${I18N.t('cc.cmdOverrideUseGroup')}">
      </div>
    </div>`;
  }

  /* ─── Inline command management ─── */
  /** Add a normalized command to a group, rejecting duplicates. */
  addCommand(groupIdx, raw) {
    const v = (raw || '').trim().toLowerCase();
    if (!v) return;
    const g = this.data.groups[groupIdx];
    if (!g) return;
    if (!g.commands) g.commands = [];
    if (g.commands.includes(v)) { showToast(I18N.t('cc.duplicateCommand') + ': ' + v, 'error'); return; }
    g.commands.push(v);
    this._dirty = true;
    this._updateSaveButton();
    this.renderList();
  }

  /** Remove a command from a group. */
  removeCommand(groupIdx, cmd) {
    const g = this.data.groups[groupIdx];
    if (!g) return;
    g.commands = (g.commands || []).filter(c => c !== cmd);
    if (g.commands_config) delete g.commands_config[cmd];
    if (this._expandedOverride && this._expandedOverride.groupIdx === groupIdx && this._expandedOverride.cmdName === cmd) {
      this._expandedOverride = null;
    }
    this._dirty = true;
    this._updateSaveButton();
    this.renderList();
  }

  /** Toggle an inline override for a command. */
  toggleOverride(groupIdx, cmd) {
    if (this._expandedOverride && this._expandedOverride.groupIdx === groupIdx && this._expandedOverride.cmdName === cmd) {
      this._collectAndSaveOverride(groupIdx, cmd);
      this._expandedOverride = null;
    } else {
      if (this._expandedOverride) {
        this._collectAndSaveOverride(this._expandedOverride.groupIdx, this._expandedOverride.cmdName);
      }
      this._expandedOverride = { groupIdx, cmdName: cmd };
    }
    this.renderList();
  }

  /** Toggle a plugin reference for a group. */
  _toggleInlinePluginRef(groupIdx) {
    if (this._openPluginRefPanels.has(groupIdx)) {
      this._openPluginRefPanels.delete(groupIdx);
    } else {
      this._openPluginRefPanels.add(groupIdx);
    }
    this.renderList();
  }

  /** Collect and persist inline override values. */
  _collectAndSaveOverride(groupIdx, cmd) {
    const panel = document.querySelector(`.cc-override-panel[data-gi="${groupIdx}"][data-cmd="${CSS.escape(cmd)}"]`);
    if (!panel) return;
    const g = this.data.groups[groupIdx];
    if (!g) return;
    if (!g.commands_config) g.commands_config = {};
    const cfg = {};
    const cdEl = panel.querySelector('.cc-ov-cooldown');
    const handlerEl = panel.querySelector('.cc-ov-handler');
    const urlEl = panel.querySelector('.cc-ov-url');
    const roleCbs = panel.querySelectorAll('.cc-ov-role-cb:checked');
    if (cdEl && cdEl.value !== '') cfg.cooldown = parseInt(cdEl.value) || 0;
    if (roleCbs.length) cfg.roles = [...roleCbs].map(cb => cb.value);
    if (handlerEl && handlerEl.value) cfg.handler = handlerEl.value;
    if (urlEl && urlEl.value) cfg.url = urlEl.value;
    if (Object.keys(cfg).length > 0) g.commands_config[cmd] = cfg;
    else delete g.commands_config[cmd];
    this._dirty = true;
    this._updateSaveButton();
  }

  /* ─── Global settings ─── */
  /** Render the global enable and cooldown controls. */
  _renderGlobalSettings() {
    return `<div style="display:flex;align-items:center;gap:1rem;margin-bottom:1rem;padding:0.8rem 1rem;background:var(--card-bg);border:1px solid var(--border);border-radius:8px;">
      <label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer;">
        <input type="checkbox" class="toggle" ${this.data.enabled ? 'checked' : ''} onchange="commentCommandsEditor.toggleGlobal(this.checked)">
        <span style="font-weight:600;">${I18N.t('cc.masterSwitch')}</span>
      </label>
      <div style="margin-left:auto;display:flex;gap:0.8rem;align-items:center;">
        <label style="font-size:0.8rem;color:var(--text-secondary);">${I18N.t('cc.globalCooldown')}:
          <input type="number" min="0" value="${this.data.cooldown || 0}" style="width:60px;padding:0.2rem 0.4rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.8rem;" onchange="commentCommandsEditor.setGlobalCooldown(parseInt(this.value)||0)">
        </label>
        <label style="font-size:0.8rem;color:var(--text-secondary);">${I18N.t('cc.globalUserCooldown')}:
          <input type="number" min="0" value="${this.data.user_cooldown || 0}" style="width:60px;padding:0.2rem 0.4rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.8rem;" onchange="commentCommandsEditor.setGlobalUserCooldown(parseInt(this.value)||0)">
        </label>
      </div>
    </div>`;
  }

  /** Toggle comment commands globally. */
  toggleGlobal(enabled) { this.data.enabled = enabled; this._dirty = true; this._updateSaveButton(); }
  /** Set the global command cooldown. */
  setGlobalCooldown(v) { this.data.cooldown = v; this._dirty = true; this._updateSaveButton(); }
  /** Set the per-user command cooldown. */
  setGlobalUserCooldown(v) { this.data.user_cooldown = v; this._dirty = true; this._updateSaveButton(); }

  /* ─── Wizard (create / edit group — 3 steps, no overrides) ─── */
  /** Start the wizard with a new comment-command group draft. */
  startCreate() {
    this._wizardMode = 'create';
    this._wizardIndex = null;
    this._wizardStep = 0;
    this._wizardDraft = {
      enabled: true, prefix: this._nextAvailablePrefix(), allowed_roles: ['moderator'], mode: 'deny-all',
      commands: [], commands_config: {}, handler: 'rcon', plugin_name: '',
      url: '', cooldown: 0, user_cooldown: 0, trigger_comment_event: true
    };
    this._openWizard();
  }

  /** Start editing a group. */
  startEdit(idx) {
    const g = this.data.groups[idx];
    if (!g) return;
    this._wizardMode = 'edit';
    this._wizardIndex = idx;
    this._wizardStep = 0;
    this._wizardDraft = JSON.parse(JSON.stringify(g));
    if (!this._wizardDraft.commands_config) this._wizardDraft.commands_config = {};
    this._openWizard();
  }

  /** Open the create/edit group wizard. */
  _openWizard() {
    this._renderWizardStep();
    document.getElementById('cc-group-editor').classList.remove('hidden');
  }

  /** Close the group wizard. */
  _closeWizard() { document.getElementById('cc-group-editor').classList.add('hidden'); }

  /** Return the next free command prefix for a new group. */
  _nextAvailablePrefix() {
    const seq = ['#','!','$','@','*','?','+','~','&','%','/','^'];
    const used = new Set((this.data.groups || []).map(g => g.prefix));
    return seq.find(c => !used.has(c)) || '?';
  }

  /** Move to the previous wizard step. */
  _wizardBack() {
    if (this._wizardStep > 0) { this._wizardStep--; this._renderWizardStep(); }
  }

  /** Validate and advance to the next wizard step. */
  _wizardNext() {
    if (!this._validateCurrentStep()) return;
    if (this._wizardStep < 2) {
      this._collectStepData(this._wizardStep);
      this._wizardStep++;
      this._renderWizardStep();
    } else {
      this._collectStepData(this._wizardStep);
      this._commitWizard();
    }
  }

  /* ─── Validation ─── */
  static VALID_PREFIX_CHARS = new Set('!@#$%^&*?~+/=<>-_|\\:.;()[]{}\'"`');
  static _isSpecialChar(ch) { return CommentCommandsEditor.VALID_PREFIX_CHARS.has(ch); }

  /** Validate the fields of the current wizard step. */
  _validateCurrentStep() {
    const d = this._wizardDraft;
    if (this._wizardStep === 0) {
      const prefix = (d.prefix || '').trim();
      if (!prefix) { this._showStepError(I18N.t('cc.prefixRequired')); return false; }
      if (prefix.length !== 1 || !CommentCommandsEditor._isSpecialChar(prefix)) {
        this._showStepError(I18N.t('cc.prefixInvalid')); return false;
      }
      const otherIdx = this._wizardMode === 'edit' ? this._wizardIndex : -1;
      const dup = this.data.groups.some((g, i) => i !== otherIdx && (g.prefix || '').trim() === prefix);
      if (dup) { this._showStepError(I18N.t('cc.prefixDuplicate')); return false; }
      if (d.handler === 'plugin' && !d.plugin_name) { this._showStepError(I18N.t('cc.pluginRequired')); return false; }
    }
    return true;
  }

  /** Display a validation error for the current step. */
  _showStepError(msg) {
    const el = document.getElementById('cc-wiz-error');
    if (el) { el.textContent = msg; el.style.display = 'flex'; }
    else showToast(msg, 'error');
  }

  /* ─── Collect data ─── */
  /** Copy the visible wizard fields into the draft for the given step. */
  _collectStepData(step) {
    const d = this._wizardDraft;
    if (step === 0) {
      const prefixEl = document.getElementById('cc-wiz-prefix');
      if (prefixEl) d.prefix = prefixEl.value.trim();
      const handlerEl = document.getElementById('cc-wiz-handler');
      if (handlerEl) d.handler = handlerEl.value;
      const pluginNameEl = document.getElementById('cc-wiz-plugin-name');
      if (pluginNameEl) d.plugin_name = pluginNameEl.value;
      const enabledEl = document.getElementById('cc-wiz-enabled');
      if (enabledEl) d.enabled = enabledEl.checked;
    } else if (step === 1) {
      const checked = [...document.querySelectorAll('.cc-role-cb:checked')].map(c => c.value);
      d.allowed_roles = checked;
      const modeEl = document.getElementById('cc-wiz-mode');
      if (modeEl) d.mode = modeEl.value;
    } else if (step === 2) {
      const cdEl = document.getElementById('cc-cd');
      if (cdEl) d.cooldown = parseInt(cdEl.value) || 0;
      const ucdEl = document.getElementById('cc-ucd');
      if (ucdEl) d.user_cooldown = parseInt(ucdEl.value) || 0;
      const urlEl = document.getElementById('cc-url');
      if (urlEl) d.url = urlEl.value;
      const trigEl = document.getElementById('cc-trig');
      if (trigEl) d.trigger_comment_event = trigEl.checked;
    }
  }

  /* ─── Render wizard step ─── */
  /** Render the wizard title, step markers and current step body. */
  _renderWizardStep() {
    const d = this._wizardDraft;
    const title = document.getElementById('cc-group-title');
    const body = document.getElementById('cc-group-body');
    const stepsBar = document.getElementById('cc-wizard-steps');
    const backBtn = document.getElementById('cc-group-back');
    const nextBtn = document.getElementById('cc-group-next');

    if (title) title.textContent = this._wizardMode === 'edit' ? I18N.t('cc.editGroup') : I18N.t('cc.createGroup');
    if (backBtn) backBtn.style.visibility = this._wizardStep > 0 ? 'visible' : 'hidden';
    if (nextBtn) nextBtn.textContent = this._wizardStep === 2
      ? (this._wizardMode === 'edit' ? I18N.t('cc.updateGroup') : I18N.t('cc.createGroup'))
      : I18N.t('common.next');

    const stepNames = [I18N.t('cc.stepBasic'), I18N.t('cc.stepAccess'), I18N.t('cc.stepCommands')];
    if (stepsBar) {
      stepsBar.innerHTML = stepNames.map((name, i) => {
        let cls = '';
        if (i === this._wizardStep) cls = 'active';
        else if (i < this._wizardStep) cls = 'done';
        return `<div class="wizard-step-dot ${cls}" title="${escapeHtml(name)}"></div>`;
      }).join('');
    }

    if (this._wizardStep === 0) this._renderStepBasic(d, body);
    else if (this._wizardStep === 1) this._renderStepAccess(d, body);
    else if (this._wizardStep === 2) this._renderStepCommands(d, body);
  }

  /* ─── Step 0: Basic ─── */
  /** Render the basic group settings step. */
  _renderStepBasic(d, body) {
    const isPlugin = d.handler === 'plugin';
    body.innerHTML = `
      <div class="form-group">
        <label>${I18N.t('cc.prefix')}</label>
        <div style="display:flex;align-items:center;gap:0.8rem;">
          <input type="text" id="cc-wiz-prefix" value="${escapeHtml(d.prefix || '#')}" maxlength="1"
            style="width:70px;padding:0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:1.3rem;text-align:center;font-weight:700;">
          <span class="hint" style="margin:0;">e.g. #, !, $, @, *</span>
        </div>
        <div id="cc-wiz-prefix-error" class="cc-validation-error" style="display:none;"></div>
      </div>
      <div class="form-group">
        <label>${I18N.t('cc.handler')}</label>
        <select id="cc-wiz-handler" style="padding:0.5rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);width:100%;">
          <option value="rcon" ${d.handler === 'rcon' ? 'selected' : ''}>RCON — ${I18N.t('cc.handlerRconDesc')}</option>
          <option value="http" ${d.handler === 'http' ? 'selected' : ''}>HTTP — ${I18N.t('cc.handlerHttpDesc')}</option>
          <option value="plugin" ${isPlugin ? 'selected' : ''}>Plugin — ${I18N.t('cc.handlerPluginDesc')}</option>
        </select>
      </div>
      <div id="cc-wiz-plugin-row" class="form-group" style="display:${isPlugin ? 'block' : 'none'};">
        <label>Plugin</label>
        <select id="cc-wiz-plugin-name" style="padding:0.5rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);width:100%;">
          <option value="">—</option>
        </select>
      </div>
      <div class="form-group">
        <label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer;">
          <input type="checkbox" class="toggle" ${d.enabled ? 'checked' : ''} id="cc-wiz-enabled">
          <span>${I18N.t('cc.enabled')}</span>
        </label>
      </div>
      <div id="cc-wiz-error" class="cc-validation-error" style="display:none;"></div>`;

    const prefixEl = document.getElementById('cc-wiz-prefix');
    if (prefixEl) prefixEl.addEventListener('input', () => {
      d.prefix = prefixEl.value;
      const errEl = document.getElementById('cc-wiz-prefix-error');
      const otherIdx = this._wizardMode === 'edit' ? this._wizardIndex : -1;
      const prefix = prefixEl.value.trim();
      if (!prefix) {
        errEl.style.display = 'none'; prefixEl.style.borderColor = '';
      } else if (prefix.length !== 1 || !CommentCommandsEditor._isSpecialChar(prefix)) {
        errEl.textContent = I18N.t('cc.prefixInvalid');
        errEl.style.display = 'flex';
        prefixEl.style.borderColor = 'var(--color-danger)';
      } else if (this.data.groups.some((g, i) => i !== otherIdx && (g.prefix || '').trim() === prefix)) {
        errEl.textContent = I18N.t('cc.prefixDuplicate');
        errEl.style.display = 'flex';
        prefixEl.style.borderColor = 'var(--color-danger)';
      } else {
        errEl.style.display = 'none';
        prefixEl.style.borderColor = '';
      }
    });
    const handlerEl = document.getElementById('cc-wiz-handler');
    if (handlerEl) handlerEl.addEventListener('change', () => {
      d.handler = handlerEl.value;
      const pluginRow = document.getElementById('cc-wiz-plugin-row');
      if (pluginRow) pluginRow.style.display = d.handler === 'plugin' ? 'block' : 'none';
    });
    const pluginNameEl = document.getElementById('cc-wiz-plugin-name');
    if (pluginNameEl) {
      pluginNameEl.addEventListener('change', () => { d.plugin_name = pluginNameEl.value; });
      this._loadPluginsForSelect(pluginNameEl, d.plugin_name);
    }
    const enabledEl = document.getElementById('cc-wiz-enabled');
    if (enabledEl) enabledEl.addEventListener('change', () => { d.enabled = enabledEl.checked; });
  }

  /* ─── Step 1: Access ─── */
  /** Render the access-control step. */
  _renderStepAccess(d, body) {
    const roles = d.allowed_roles || [];
    const showSecurityWarning = d.handler === 'rcon' && d.mode === 'allow-all' && roles.includes('all');
    body.innerHTML = `
      <div class="form-group">
        <label>${I18N.t('cc.allowedRoles')}</label>
        <div style="display:flex;gap:1rem;flex-wrap:wrap;">
          ${['all', 'moderator', 'superfan', 'fanclub'].map(r => `<label style="display:flex;align-items:center;gap:0.4rem;cursor:pointer;">
            <input type="checkbox" value="${r}" ${roles.includes(r) ? 'checked' : ''} class="cc-role-cb"> ${r}
          </label>`).join('')}
        </div>
      </div>
      <div class="form-group">
        <label>${I18N.t('cc.mode')}</label>
        <select id="cc-wiz-mode" style="padding:0.5rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);width:100%;">
          <option value="deny-all" ${d.mode === 'deny-all' ? 'selected' : ''}>deny-all — ${I18N.t('cc.modeDenyDesc')}</option>
          <option value="allow-all" ${d.mode === 'allow-all' ? 'selected' : ''}>allow-all — ${I18N.t('cc.modeAllowDesc')}</option>
        </select>
      </div>
      <div id="cc-security-warning" class="cc-security-warning" style="display:${showSecurityWarning ? 'block' : 'none'};">
        ${I18N.t('cc.securityWarning')}
      </div>`;

    document.querySelectorAll('.cc-role-cb').forEach(cb => {
      cb.addEventListener('change', () => {
        d.allowed_roles = [...document.querySelectorAll('.cc-role-cb:checked')].map(c => c.value);
        this._updateSecurityWarning(d);
      });
    });
    const modeEl = document.getElementById('cc-wiz-mode');
    if (modeEl) modeEl.addEventListener('change', () => {
      d.mode = modeEl.value;
      this._updateSecurityWarning(d);
    });
  }

  /** Update the security warning for the selected group. */
  _updateSecurityWarning(d) {
    const warnEl = document.getElementById('cc-security-warning');
    if (!warnEl) return;
    const show = d.handler === 'rcon' && d.mode === 'allow-all' && (d.allowed_roles || []).includes('all');
    warnEl.style.display = show ? 'block' : 'none';
  }

  /* ─── Step 2: Commands ─── */
  /** Render the command and cooldown step. */
  _renderStepCommands(d, body) {
    const cmds = d.commands || [];
    body.innerHTML = `
      <div class="form-group">
        <label>${I18N.t('cc.commands')} <span style="font-weight:400;color:var(--text-secondary);font-size:0.8rem;">(${I18N.t('cc.commandsHelp')})</span></label>
        <div class="cc-cmd-chips" id="cc-chips-container">
          ${cmds.map(c => `<span class="cc-cmd-chip">${escapeHtml(c)}<span class="cc-cmd-chip-remove" data-cmd="${escapeHtml(c)}">&times;</span></span>`).join('')}
          <input type="text" class="cc-cmd-input" id="cc-cmd-input" placeholder="${I18N.t('cc.commandsPlaceholder')}" value="">
        </div>
        <div id="cc-cmds-error" class="cc-validation-error" style="display:none;"></div>
      </div>
      <div style="display:flex;gap:1rem;">
        <div class="form-group" style="flex:1;">
          <label>${I18N.t('cc.cooldown')} (s)</label>
          <input type="number" id="cc-cd" min="0" value="${d.cooldown || 0}" style="width:100%;padding:0.5rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);">
        </div>
        <div class="form-group" style="flex:1;">
          <label>${I18N.t('cc.userCooldown')} (s)</label>
          <input type="number" id="cc-ucd" min="0" value="${d.user_cooldown || 0}" style="width:100%;padding:0.5rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);">
        </div>
      </div>
      ${d.handler === 'http' ? `<div class="form-group">
        <label>${I18N.t('cc.url')}</label>
        <input type="text" id="cc-url" value="${escapeHtml(d.url || '')}" style="width:100%;padding:0.5rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);" placeholder="${I18N.t('cc.urlPlaceholder')}">
      </div>` : ''}
      <div class="form-group">
        <label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer;">
          <input type="checkbox" id="cc-trig" ${d.trigger_comment_event !== false ? 'checked' : ''}>
          <span style="font-size:0.85rem;">${I18N.t('cc.triggerCommentEvent')}</span>
        </label>
      </div>
      <p class="hint" style="margin-top:var(--space-2);">${I18N.t('cc.hintOverrides')}</p>
      ${d.handler === 'plugin' && d.plugin_name ? `<div class="cc-plugin-commands-ref">
        <div class="cc-plugin-commands-ref-header" id="cc-ref-toggle">
          <h4><span class="mi" style="font-size:14px;">extension</span> ${I18N.t('cc.availableCommands')} — ${escapeHtml(d.plugin_name)}</h4>
          <span class="cc-ref-toggle" id="cc-ref-arrow">▾</span>
        </div>
        <div class="cc-plugin-commands-ref-body" id="cc-ref-body">
          ${this._renderPluginCommandsRef(d)}
        </div>
      </div>` : ''}`;

    this._bindChipInput(d);
    this._bindRefPanel(d);
  }

  /** Wire chip-style multi-value inputs. */
  _bindChipInput(d) {
    const container = document.getElementById('cc-chips-container');
    const input = document.getElementById('cc-cmd-input');
    if (!container || !input) return;

    const addChip = (val) => {
      const v = val.trim().toLowerCase();
      if (!v || (d.commands || []).includes(v)) return;
      d.commands.push(v);
      const chip = document.createElement('span');
      chip.className = 'cc-cmd-chip';
      chip.innerHTML = `${escapeHtml(v)}<span class="cc-cmd-chip-remove" data-cmd="${escapeHtml(v)}">&times;</span>`;
      container.insertBefore(chip, input);
      chip.querySelector('.cc-cmd-chip-remove').addEventListener('click', () => {
        d.commands = d.commands.filter(c => c !== v);
        chip.remove();
      });
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        const val = input.value.replace(',', '').trim();
        if (val) { addChip(val); input.value = ''; }
      }
      if (e.key === 'Backspace' && !input.value && d.commands.length) {
        const last = d.commands[d.commands.length - 1];
        d.commands.pop();
        const lastChip = container.querySelector(`.cc-cmd-chip-remove[data-cmd="${CSS.escape(last)}"]`)?.closest('.cc-cmd-chip');
        if (lastChip) lastChip.remove();
      }
    });

    input.addEventListener('blur', () => {
      const val = input.value.replace(',', '').trim();
      if (val) { addChip(val); input.value = ''; }
    });

    container.addEventListener('click', (e) => {
      if (e.target === container || e.target === input) input.focus();
    });

    container.querySelectorAll('.cc-cmd-chip-remove').forEach(btn => {
      const v = btn.dataset.cmd;
      btn.addEventListener('click', () => {
        d.commands = d.commands.filter(c => c !== v);
        btn.closest('.cc-cmd-chip')?.remove();
      });
    });
  }

  /** Render the plugin-command reference panel. */
  _renderPluginCommandsRef(d) {
    const pname = d.plugin_name;
    const cmds = pname ? (this._pluginCatalog[pname] || null) : null;
    if (!cmds || !Object.keys(cmds).length) return `<p style="color:var(--text-muted);font-size:var(--text-sm);margin:0;">${I18N.t('cc.noPluginCommands')}</p>`;
    const existing = new Set(d.commands || []);
    return `<div class="cc-plugin-cmd-group">
      <div class="cc-plugin-cmd-group-name">${escapeHtml(pname)}</div>
      ${Object.keys(cmds).map(k => {
        const c = cmds[k];
        const alreadyAdded = existing.has(k);
        return `<div class="cc-plugin-cmd-item">
          <span class="cc-plugin-cmd-name" data-plugin="${escapeHtml(pname)}" data-cmd="${escapeHtml(k)}" ${alreadyAdded ? 'style="opacity:0.4;cursor:default;"' : 'title="Click to add"'}>${escapeHtml(k)}${alreadyAdded ? ' ✓' : ''}</span>
          <span class="cc-plugin-cmd-desc">${escapeHtml(c.desc || c.name || '')}</span>
        </div>`;
      }).join('')}
    </div>`;
  }

  /** Wire the plugin-command reference panel. */
  _bindRefPanel(d) {
    const toggle = document.getElementById('cc-ref-toggle');
    const body = document.getElementById('cc-ref-body');
    const arrow = document.getElementById('cc-ref-arrow');
    if (body && arrow && this._refPanelOpen) {
      body.classList.add('open');
      arrow.classList.add('open');
    }
    if (toggle && body && arrow) {
      toggle.addEventListener('click', () => {
        this._refPanelOpen = !this._refPanelOpen;
        body.classList.toggle('open', this._refPanelOpen);
        arrow.classList.toggle('open', this._refPanelOpen);
      });
    }
    document.querySelectorAll('.cc-plugin-cmd-name[data-plugin]').forEach(el => {
      el.addEventListener('click', () => {
        const val = el.dataset.cmd;
        if (val && !d.commands.includes(val)) {
          d.commands.push(val);
          el.style.opacity = '0.4';
          el.style.cursor = 'default';
          el.title = 'Already added';
          el.textContent = val + ' ✓';
          const container = document.getElementById('cc-chips-container');
          const input = document.getElementById('cc-cmd-input');
          if (container && input) {
            const chip = document.createElement('span');
            chip.className = 'cc-cmd-chip';
            chip.innerHTML = `${escapeHtml(val)}<span class="cc-cmd-chip-remove" data-cmd="${escapeHtml(val)}">&times;</span>`;
            container.insertBefore(chip, input);
            chip.querySelector('.cc-cmd-chip-remove').addEventListener('click', () => {
              d.commands = d.commands.filter(c => c !== val);
              chip.remove();
              el.style.opacity = '';
              el.style.cursor = '';
              el.title = 'Click to add';
              el.textContent = val;
            });
          }
        }
      });
    });
  }

  /* ─── Commit wizard ─── */
  /** Validate the draft and commit it to the working group list. */
  _commitWizard() {
    const draft = this._wizardDraft;
    if (!draft.prefix) { showToast(I18N.t('cc.prefixRequired'), 'error'); return; }
    if (this._wizardMode === 'edit' && this._wizardIndex !== null) {
      this.data.groups[this._wizardIndex] = draft;
    } else {
      this.data.groups.push(draft);
    }
    this._dirty = true;
    this._updateSaveButton();
    this._closeWizard();
    this.renderSidebar();
    this.renderList();
    showToast(this._wizardMode === 'edit' ? I18N.t('cc.updated') : I18N.t('cc.created'), 'success');
  }

  /* ─── Delete ─── */
  /** Ask for confirmation before deleting a group. */
  confirmDelete(idx) {
    const g = this.data.groups[idx];
    if (!g) return;
    document.getElementById('cc-delete-message').textContent = I18N.t('cc.deleteMessage', { prefix: g.prefix });
    document.getElementById('cc-delete-modal').classList.remove('hidden');
    const confirmBtn = document.getElementById('cc-delete-confirm');
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
    newBtn.addEventListener('click', () => {
      this._hideDeleteModal();
      this.data.groups.splice(idx, 1);
      this._dirty = true;
      this._updateSaveButton();
      this.renderSidebar();
      this.renderList();
      showToast(I18N.t('cc.deleted'), 'info');
    });
  }

  /** Hide the group delete confirmation dialog. */
  _hideDeleteModal() { document.getElementById('cc-delete-modal').classList.add('hidden'); }

  /* ─── Save ─── */
  /** Persist comment-command groups through the API. */
  async save() {
    for (const g of (this.data.groups || [])) {
      if (!g.prefix) { showToast(I18N.t('cc.groupWithoutPrefix'), 'error'); return; }
    }
    try {
      await putJSON('/comment-commands', { comment_commands: this.data });
      await postJSON('/reload', { config: false, actions: false, comment_commands: true });
      this.original = JSON.parse(JSON.stringify(this.data));
      this._dirty = false;
      this._updateSaveButton();
      showToast(I18N.t('cc.saved'), 'success');
    } catch (e) {
      showToast(I18N.t('cc.saveFailed', { msg: e.message }), 'error');
      throw e;
    }
  }
}

