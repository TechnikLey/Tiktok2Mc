/**
 * @file Schema-driven editor for the main configuration.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Editor Class ─── */
/**
 * Editor for the main `config.yaml`.
 *
 * Preserves unknown keys, renders typed fields from `SECTION_META`, validates input and supports review/diff before saving through the shared save flow.
 */
class ConfigEditor {
  /** Create the main config editor and cache its DOM elements. */
  constructor() {
    this.data = {};
    this.original = {};
    this.unknownKeys = {};
    this.originalUnknownKeys = {};
    this.searchQuery = '';
    this.errors = new Map();
    this.collectErrors = new Map();
    this.sidebar = document.getElementById('editor-sidebar');
    this.content = document.getElementById('editor-content');
    this.knownTop = new Set(Object.keys(SECTION_META));
    this.activeSection = null;
    this.originalTypes = {}; // track original types for commands_config etc.
    this._advancedMode = localStorage.getItem('config_advanced_mode') === 'true';
  }

  /** Open the editor for the supplied configuration document. */
  open(config) {
    this.original = JSON.parse(JSON.stringify(config));
    this.data = JSON.parse(JSON.stringify(config));
    this.unknownKeys = {};
    this.originalUnknownKeys = {};
    this.errors.clear();
    this.collectErrors.clear();
    // Read config_advanced from file before extractUnknownKeys removes it
    if (typeof config.config_advanced === 'boolean') {
      this._advancedMode = config.config_advanced;
      localStorage.setItem('config_advanced_mode', String(this._advancedMode));
    }
    this.extractUnknownKeys();
    this.searchQuery = '';
    document.getElementById('editor-search').value = '';
    this.render();
    document.getElementById('config-editor').classList.remove('hidden');
    this.activeSection = null;
    // Setup IntersectionObserver after render
    this.setupScrollSpy();
    // Scroll to first section
    const first = this.content.querySelector('.section-card');
    if (first) { this.scrollTo(first.id); }
    this._updateSaveButton();
    this._updateAdvancedUI();
    this._attachInputListeners();
  }

  /** Return whether the working config differs from the loaded config. */
  isDirty() {
    return JSON.stringify(this.data) !== JSON.stringify(this.original);
  }

  /** Update the save button from dirty and validation state. */
  _updateSaveButton() {
    const btn = document.getElementById('config-editor-save');
    if (!btn) return;
    const dirty = this.isDirty();
    btn.disabled = !dirty;
    btn.style.opacity = dirty ? '1' : '0.5';
    btn.style.cursor = dirty ? 'pointer' : 'not-allowed';
  }

  /** Attach change listeners to the rendered fields. */
  _attachInputListeners() {
    if (this._inputHandler) return;
    this._inputHandler = (e) => {
      if (e.target.closest && e.target.closest('.editor-content')) {
        if (this._inputTimer) clearTimeout(this._inputTimer);
        this._inputTimer = setTimeout(() => {
          this.collect();
          this._updateSaveButton();
        }, 150);
      }
    };
    this.content.addEventListener('input', this._inputHandler);
    this.content.addEventListener('change', this._inputHandler);
  }

  /** Detach field listeners before re-rendering. */
  _detachInputListeners() {
    if (!this._inputHandler) return;
    this.content.removeEventListener('input', this._inputHandler);
    this.content.removeEventListener('change', this._inputHandler);
    this._inputHandler = null;
    if (this._inputTimer) { clearTimeout(this._inputTimer); this._inputTimer = null; }
  }

  /** Return whether a config path is hidden behind advanced mode. */
  _isFieldAdvanced(path) {
    const meta = getMeta(path);
    return meta.basic === false;
  }

  /** Toggle visibility of advanced fields. */
  _toggleAdvanced() {
    if (this._advancedMode) {
      this._advancedMode = false;
      localStorage.setItem('config_advanced_mode', 'false');
      this._updateAdvancedUI();
      this.render();
    } else {
      this._unlockAdvanced();
    }
  }

  /** Confirm and unlock advanced-field editing. */
  _unlockAdvanced() {
    const dlg = document.getElementById('advanced-confirm-dialog');
    if (!dlg) return;
    const input = document.getElementById('advanced-confirm-input');
    if (!input) return;

    input.value = '';
    dlg.classList.remove('hidden');

    const okBtn = document.getElementById('advanced-confirm-ok');
    const cancelBtn = document.getElementById('advanced-confirm-cancel');
    if (okBtn) okBtn.disabled = true;

    const onInput = () => {
      const btn = document.getElementById('advanced-confirm-ok');
      if (btn) btn.disabled = input.value.trim() !== I18N.t('dialog.advancedPhrase');
    };
    input.addEventListener('input', onInput);

    const cleanup = () => {
      dlg.classList.add('hidden');
      input.removeEventListener('input', onInput);
    };

    const handleOk = () => {
      if (input.value.trim() !== I18N.t('dialog.advancedPhrase')) return;
      cleanup();
      this._advancedMode = true;
      localStorage.setItem('config_advanced_mode', 'true');
      this._updateAdvancedUI();
      this.render();
    };
    const handleCancel = () => { cleanup(); };

    if (okBtn) { okBtn.addEventListener('click', handleOk); }
    if (cancelBtn) { cancelBtn.addEventListener('click', handleCancel); }
  }

  /** Update the advanced-mode toggle and field visibility. */
  _updateAdvancedUI() {
    const btn = document.getElementById('config-advanced-btn');
    if (!btn) return;
    if (this._advancedMode) {
      btn.textContent = I18N.t('common.advanced') + ' ✓';
      btn.classList.add('active');
    } else {
      btn.textContent = I18N.t('common.advanced');
      btn.classList.remove('active');
    }
  }

  /** Close the editor. */
  close() {
    if (this.isDirty()) {
      showConfirmDialog(I18N.t('dialog.unsavedTitle'), I18N.t('dialog.unsavedClose'), I18N.t('common.close'), 'btn-danger').then(confirmed => {
        if (!confirmed) return;
        this._detachInputListeners();
        this._resetData();
        this._updateSaveButton();
        document.getElementById('config-editor').classList.add('hidden');
        document.getElementById('review-modal').classList.add('hidden');
      });
      return;
    }
    this._detachInputListeners();
    document.getElementById('config-editor').classList.add('hidden');
    document.getElementById('review-modal').classList.add('hidden');
  }

  /** Reset working data and dirty state. */
  _resetData() {
    this.data = JSON.parse(JSON.stringify(this.original));
    this.unknownKeys = JSON.parse(JSON.stringify(this.originalUnknownKeys));
  }

  /** Collect config keys not represented by section metadata. */
  extractUnknownKeys() {
    for (const key of Object.keys(this.data)) {
      if (key === 'config_version' || key === 'config_advanced') {
        delete this.data[key];
        delete this.original[key];
        continue;
      }
      if (!this.knownTop.has(key)) {
        this.unknownKeys[key] = this.data[key];
        this.originalUnknownKeys[key] = this.data[key];
        delete this.data[key];
        delete this.original[key];
      }
    }
  }

  /** Merge preserved unknown keys back into the configuration. */
  mergeUnknownKeys() {
    Object.assign(this.data, this.unknownKeys);
  }

  /** Render the complete editor. */
  render() {
    this.renderSidebar();
    this.renderContent();
    // Re-attach observer to new section cards after any re-render
    this.setupScrollSpy();
  }

  /** Render section navigation. */
  renderSidebar() {
    let html = `<div class="sidebar-header">${I18N.t('editor.navigation')}</div>`;
    for (const [cat, keys] of Object.entries(CATEGORIES)) {
      const visibleKeys = keys.filter(k => k in this.data);
      if (!visibleKeys.length) continue;
      html += '<div class="sidebar-group">';
      html += `<div class="sidebar-group-title">${escapeHtml(categoryLabel(cat))}</div>`;
      for (const key of visibleKeys) {
        const meta = sectionMeta(key) || { title: toTitle(key) };
        const hasErr = this.sectionHasError(key);
        const isActive = this.activeSection === key;
        html += `<a class="sidebar-item ${hasErr ? 'has-error' : ''} ${isActive ? 'active' : ''}" onclick="editor.scrollTo('section_${key}')">${escapeHtml(meta.title)}${hasErr ? '<span class="badge">!</span>' : ''}</a>`;
      }
      html += '</div>';
    }
    if (Object.keys(this.unknownKeys).length) {
      html += '<div class="sidebar-group">';
      html += `<div class="sidebar-group-title">${I18N.t('editor.other')}</div>`;
      const isActive = this.activeSection === '_unknown';
      html += `<a class="sidebar-item ${this.sectionHasError('_unknown') ? 'has-error' : ''} ${isActive ? 'active' : ''}" onclick="editor.scrollTo('section_unknown')">${I18N.t('editor.unrecognized')}</a>`;
      html += '</div>';
    }
    this.sidebar.innerHTML = html;
  }

  /** Return whether a section currently has a validation error. */
  sectionHasError(key) {
    const prefix = key === '_unknown' ? '_unknown' : key;
    for (const [path, err] of this.errors) {
      if (path.startsWith(prefix)) return true;
    }
    return false;
  }

  /** Render all configuration sections. */
  renderContent() {
    let html = '';
    const addedSections = new Set();
    for (const key of SECTION_ORDER) {
      if (!(key in this.data)) continue;
      if (this.searchQuery && !this.sectionMatchesSearch(key)) continue;
      html += this.buildSection(key, this.data[key]);
      addedSections.add(key);
    }
    for (const key of Object.keys(this.data).sort()) {
      if (addedSections.has(key)) continue;
      if (this.searchQuery && !this.sectionMatchesSearch(key)) continue;
      html += this.buildSection(key, this.data[key]);
    }
    if (Object.keys(this.unknownKeys).length) {
      html += this.buildUnknownSection();
    }
    if (!html) {
      html = `<div class="search-empty"><h3>${I18N.t('editor.noResults')}</h3><p>${I18N.t('editor.noResultsDesc')}</p></div>`;
    }
    this.content.innerHTML = html;
  }

  /** Return whether a section matches the search query. */
  sectionMatchesSearch(key) {
    const meta = sectionMeta(key) || {};
    if ((meta.title || key).toLowerCase().includes(this.searchQuery)) return true;
    if ((meta.desc || '').toLowerCase().includes(this.searchQuery)) return true;
    // Check fields
    const section = this.data[key];
    if (typeof section === 'object' && section !== null) {
      for (const subKey of Object.keys(section)) {
        const path = `${key}.${subKey}`;
        if (path.toLowerCase().includes(this.searchQuery)) return true;
        if ((getHelp(path) || '').toLowerCase().includes(this.searchQuery)) return true;
      }
    }
    return false;
  }

  /** Build one configuration section. */
  buildSection(key, value) {
    const meta = sectionMeta(key) || { title: toTitle(key), desc: '' };
    let body;
    if (key === 'theme') {
      body = this.buildThemeEditor(key, value);
    } else if (key === 'overlay') {
      body = this.buildOverlayEditor(key, value);
    } else if (key === 'outbound') {
      body = this.buildOutboundEditor(key, value);
    } else if (key === 'like_triggers') {
      body = this.buildLikeTriggersEditor(key, value);
    } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      body = this.buildObjectFields(key, value);
    } else if (Array.isArray(value)) {
      body = this.buildPrimitiveArray(key, value);
    } else {
      body = this.buildField(key, value, key);
    }
    const hidden = this.searchQuery ? '' : '';
    return `<div class="section-card" id="section_${key}">
      <div class="section-header"><h3>${escapeHtml(meta.title)}</h3></div>
      ${meta.desc ? `<p class="section-desc">${escapeHtml(meta.desc)}</p>` : ''}
      <div class="section-body">${body}</div>
    </div>`;
  }

  /** Build fields for an object section. */
  buildObjectFields(prefix, obj) {
    let html = '';
    for (const [k, v] of Object.entries(obj)) {
      if (k === 'config_version') continue;
      const path = `${prefix}.${k}`;
      const meta = getMeta(path);
      if (this.searchQuery && !this.fieldMatchesSearch(path, k)) continue;
      if (meta.basic === false && !this._advancedMode) {
        html += this._buildLockedField(k, path, getHelp(path));
        continue;
      }
      if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
        // Nested object (e.g., follow_tracking)
        html += `<div style="margin-bottom:1rem;"><strong style="font-size:0.9rem;color:var(--text);">${escapeHtml(toTitle(k))}</strong>`;
        if (getHelp(path)) html += `<p class="field-desc" style="margin:0.25rem 0 0.5rem 0;">${escapeHtml(getHelp(path))}</p>`;
        html += `<div style="padding-left:1rem;border-left:2px solid var(--border);">`;
        for (const [k2, v2] of Object.entries(v)) {
          const p2 = `${path}.${k2}`;
          const m2 = getMeta(p2);
          if (this.searchQuery && !this.fieldMatchesSearch(p2, k2)) continue;
          html += this.buildField(k2, v2, p2);
        }
        html += '</div></div>';
      } else if (Array.isArray(v)) {
        if (path === 'overlay.overlays') {
          html += this.buildOverlaySlotsEditor(path, v);
        } else if (path === 'outbound.channels') {
          html += this.buildOutboundChannelsEditor(path, v);
        } else if (path === 'random_triggers.triggers') {
          html += this.buildTagEditor(path, v, { label: 'Triggers', suggestions: ['likes','like_2','follow','join','comment','gift','share'] });
        } else if (path.endsWith('.commands')) {
          html += this.buildTagEditor(path, v, { label: 'Commands' });
        } else if (path.endsWith('.allowed_roles')) {
          html += this.buildRoleSelector(path, v);
        } else {
          html += this.buildPrimitiveArray(path, v);
        }
      } else {
        html += this.buildField(k, v, path);
      }
    }
    return html;
  }

  /** Return whether a field path matches the search query. */
  fieldMatchesSearch(path, key) {
    if (!this.searchQuery) return true;
    const q = this.searchQuery.toLowerCase();
    if (path.toLowerCase().includes(q)) return true;
    if (key.toLowerCase().includes(q)) return true;
    if ((getHelp(path) || '').toLowerCase().includes(q)) return true;
    return false;
  }

  /** Build a read-only field for a managed value. */
  _buildLockedField(key, path, help) {
    const label = toTitle(key);
    return `<div class="editor-field editor-field--locked" onclick="editor._unlockAdvanced()">
      <div class="field-label">
        <span class="lock-icon">🔒</span> ${escapeHtml(label)}
      </div>
      <div class="field-widget">
        <div class="locked-overlay">
          <span class="locked-text">${I18N.t('editor.advancedLocked', { unlock: 'editor._unlockAdvanced' })}</span>
        </div>
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
      </div>
    </div>`;
  }

  /** Build the control for one configuration value. */
  buildField(key, value, path) {
    const meta = getMeta(path);
    if (meta.basic === false && !this._advancedMode) {
      return this._buildLockedField(key, path, getHelp(path));
    }
    const label = toTitle(key);
    const help = getHelp(path);
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const isReq = meta.required;

    let inputHtml;
    if (meta.readonly) {
      inputHtml = `<input type="text" id="${id}" value="${escapeHtml(value !== undefined ? String(value) : '')}" data-path="${path}" data-type="string" readonly style="opacity:0.6;cursor:not-allowed;">`;
    } else if (meta.type === 'bool' || (meta.type === undefined && typeof value === 'boolean')) {
      inputHtml = `<input type="checkbox" class="toggle" id="${id}" ${value ? 'checked' : ''} data-path="${path}" data-type="bool">`;
    } else if (meta.type === 'select') {
      const onch = path.endsWith('.handler') ? ' onchange="editor.render()"' : '';
      inputHtml = `<select id="${id}" data-path="${path}" data-type="string"${onch}>${meta.options.map(o => `<option value="${o}" ${value === o ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
    } else if (meta.type === 'color') {
      const colorVal = value || '#000000';
      const colorId = id + '_cp';
      inputHtml = `<div class="color-row">
        <input type="color" id="${colorId}" value="${colorVal}" data-path="${path}" data-type="string" oninput="document.getElementById('${id}').value=this.value; editor.onFieldInput()">
        <input type="text" id="${id}" value="${colorVal}" style="width:120px;padding:0.45rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.9rem;" oninput="document.getElementById('${colorId}').value=this.value; editor.onFieldInput()" data-path="${path}" data-type="string">
      </div>`;
    } else if (meta.type === 'password') {
      inputHtml = `<input type="password" id="${id}" value="${escapeHtml(value || '')}" data-path="${path}" data-type="string">`;
    } else if (meta.type === 'number') {
      inputHtml = `<input type="number" id="${id}" value="${value !== undefined ? value : ''}" data-path="${path}" data-type="number"${meta.min !== undefined ? ` min="${meta.min}"` : ''}${meta.max !== undefined ? ` max="${meta.max}"` : ''}>`;
    } else {
      inputHtml = `<input type="text" id="${id}" value="${escapeHtml(value !== undefined ? String(value) : '')}" data-path="${path}" data-type="string">`;
    }

    const err = this.errors.get(path) || '';
    const isAdvanced = meta.basic === false;
    const fieldCls = isAdvanced ? 'editor-field editor-field--has-advanced' : 'editor-field';
    return `<div class="${fieldCls}" data-path="${path}">
      <div class="field-label">${escapeHtml(label)}${isReq ? '<span class="required">*</span>' : ''}${isAdvanced ? `<span class="advanced-badge" title="${I18N.t('editor.advancedSetting')}">!</span>` : ''}</div>
      <div class="field-widget">
        ${inputHtml}
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
        <span class="field-error ${err ? 'visible' : ''}" id="${id}_err">${escapeHtml(err)}</span>
      </div>
    </div>`;
  }

  /** Build a tag editor for a string array. */
  buildTagEditor(path, values, opts) {
    opts = opts || {};
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const help = getHelp(path);
    const chips = (values || []).map((v, idx) => `<span class="tag-chip">${escapeHtml(v)}<span class="remove" onclick="editor.removeTagByIndex('${path}', ${idx})">&times;</span></span>`).join('');
    return `<div class="editor-field" data-path="${path}">
      <div class="field-label">${escapeHtml(opts.label || toTitle(path.split('.').pop()))}</div>
      <div class="field-widget">
        <div class="tag-box" id="${id}_box">${chips}<input type="text" id="${id}_inp" placeholder="Add..." onkeydown="editor.tagKey(event, '${path}')"></div>
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
      </div>
    </div>`;
  }

  /** Add the current tag input on Enter. */
  tagKey(e, path) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const val = e.target.value.trim();
    if (!val) return;
    const arr = this.getValue(path) || [];
    if (!arr.includes(val)) { arr.push(val); this.setValue(path, arr); }
    this.render();
    // Refocus
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_') + '_inp';
    setTimeout(() => { const el = document.getElementById(id); if (el) el.focus(); }, 0);
  }

  /** Remove a tag at the given index. */
  removeTagByIndex(path, idx) {
    const arr = this.getValue(path) || [];
    if (idx >= 0 && idx < arr.length) { arr.splice(idx, 1); this.setValue(path, arr); this.render(); }
  }

  /** Build the role multi-select control. */
  buildRoleSelector(path, values) {
    const roles = ['all','moderator','superfan','fanclub'];
    const current = values || [];
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const help = getHelp(path);
    const boxes = roles.map(r => {
      const checked = current.includes(r) ? 'checked' : '';
      return `<label><input type="checkbox" ${checked} data-role="${r}" onchange="editor.onRoleChange('${path}', this)">${toTitle(r)}</label>`;
    }).join('');
    return `<div class="editor-field" data-path="${path}">
      <div class="field-label">Allowed Roles</div>
      <div class="field-widget">
        <div class="checkbox-group" id="${id}">${boxes}</div>
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
      </div>
    </div>`;
  }

  /** Handle role selection changes. */
  onRoleChange(path, cb) {
    const role = cb.getAttribute('data-role');
    const arr = this.getValue(path) || [];
    if (cb.checked) { if (!arr.includes(role)) arr.push(role); }
    else { const idx = arr.indexOf(role); if (idx > -1) arr.splice(idx, 1); }
    this.setValue(path, arr);
  }

  /** Remove one array item and re-render. */
  removeArrayItem(path, index) {
    const arr = this.getValue(path) || [];
    arr.splice(index, 1);
    this.setValue(path, arr);
    this.render();
  }

  /** Mark the editor dirty after a field edit. */
  onFieldInput() {
    this.collect();
    this._updateSaveButton();
  }

  /** Build the overlay-slot editor. */
  buildOverlaySlotsEditor(path, slots) {
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const help = getHelp(path);
    const rows = (slots || []).map((slot, i) => {
      const nameId = id + '_name_' + i;
      const urlId = id + '_url_' + i;
      const urlInput = 'url' in slot
        ? `<input type="text" id="${urlId}" value="${escapeHtml(slot.url || '')}" placeholder="OBS Browser Source URL" data-path="${path}[${i}].url" data-type="string" oninput="editor.onFieldInput()" style="flex:1;padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.85rem;">`
        : `<button class="btn btn-secondary" style="font-size:0.8rem;padding:0.3rem 0.6rem;" onclick="editor.addOverlaySlotUrl('${path}', ${i})">+ URL</button>`;
      return `<div class="overlay-slot-row">
        <input type="text" id="${nameId}" value="${escapeHtml(slot.name || '')}" placeholder="Slot name" data-path="${path}[${i}].name" data-type="string" oninput="editor.onFieldInput()" style="width:140px;padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.85rem;">
        ${urlInput}
        <button class="btn-icon" onclick="editor.removeOverlaySlot('${path}', ${i})" title="Remove slot">&times;</button>
      </div>`;
    }).join('');
    return `<div class="editor-field full-width" data-path="${path}">
      <div class="field-label">Overlay Slots</div>
      <div class="field-widget">
        <div class="overlay-slots-list" id="${id}_list">${rows}</div>
        <button class="btn btn-secondary" style="margin-top:0.5rem;" onclick="editor.addOverlaySlot('${path}')">+ Add Slot</button>
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
      </div>
    </div>`;
  }

  /** Append a new overlay slot. */
  addOverlaySlot(path) {
    const arr = this.getValue(path) || [];
    arr.push({ name: '', url: '' });
    this.setValue(path, arr);
    this.render();
  }

  /** Add a URL input to an overlay slot. */
  addOverlaySlotUrl(path, index) {
    const arr = this.getValue(path) || [];
    if (arr[index] && !('url' in arr[index])) {
      arr[index].url = '';
      this.setValue(path, arr);
      this.render();
    }
  }

  /** Remove an overlay slot. */
  removeOverlaySlot(path, index) {
    const arr = this.getValue(path) || [];
    arr.splice(index, 1);
    this.setValue(path, arr);
    this.render();
  }

  /** Build the theme editor. */
  buildThemeEditor(path, theme) {
    // Structural rendering only: nested objects are colour groups, plain
    // strings are single colours. No hardcoded consumer names — the
    // frontend must not know individual plugins.
    let html = '';
    for (const [group, value] of Object.entries(theme || {})) {
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        html += `<div style="margin-bottom:1.5rem;"><strong style="font-size:0.95rem;color:var(--text);display:block;margin-bottom:0.5rem;">${escapeHtml(toTitle(group))}</strong>`;
        for (const [ckey, cval] of Object.entries(value)) {
          const p = `${path}.${group}.${ckey}`;
          const id = 'f_' + p.replace(/[^a-zA-Z0-9]/g, '_');
          html += `<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem;">
            <span style="font-size:0.85rem;color:var(--text-secondary);min-width:100px;">${escapeHtml(toTitle(ckey))}</span>
            <input type="color" id="${id}" value="${cval}" data-path="${p}" data-type="string" oninput="document.getElementById('${id}_hex').value=this.value">
            <input type="text" id="${id}_hex" value="${escapeHtml(cval)}" style="width:120px;padding:0.45rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.9rem;" oninput="document.getElementById('${id}').value=this.value">
          </div>`;
        }
        html += '</div>';
      } else if (typeof value === 'string') {
        const p = `${path}.${group}`;
        const id = 'f_' + p.replace(/[^a-zA-Z0-9]/g, '_');
        html += `<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem;">
          <span style="font-size:0.85rem;color:var(--text-secondary);min-width:100px;">${escapeHtml(toTitle(group))}</span>
          <input type="color" id="${id}" value="${value}" data-path="${p}" data-type="string" oninput="document.getElementById('${id}_hex').value=this.value">
          <input type="text" id="${id}_hex" value="${escapeHtml(value)}" style="width:120px;padding:0.45rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.9rem;" oninput="document.getElementById('${id}').value=this.value">
        </div>`;
      }
    }
    return html;
  }

  /** Build the overlay configuration editor. */
  buildOverlayEditor(path, overlay) {
    const fields = this.buildObjectFields(path, overlay);
    return fields;
  }

  /** Build the like-trigger editor. */
  buildLikeTriggersEditor(path, triggers) {
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const help = getHelp(path);
    const lang = _editorLangIsDe() ? 'de' : 'en';
    const T = {
      en: {
        trigger: 'Trigger', remove: 'Remove trigger',
        id: 'Name', idHelp: 'A label for this trigger — only used in logs so you can tell which one fired.',
        every: 'Every N likes', everyHelp: 'How many likes between activations. E.g. 100 → fires at 100, 200, 300…',
        fn: 'Action', fnHelp: 'The trigger name from your actions.mca file. The command you wrote for this name will run.',
        payload: 'Label', payloadHelp: 'This text replaces {user} in your actions.mca command. E.g. "Community" → {user} becomes "Community".',
        add: '+ Add Trigger',
      },
      de: {
        trigger: 'Trigger', remove: 'Trigger entfernen',
        id: 'Name', idHelp: 'Ein Name für diesen Trigger — wird nur in Logs angezeigt, damit du siehst, welcher ausgelöst wurde.',
        every: 'Alle N Likes', everyHelp: 'Wie viele Likes zwischen den Auslösungen. Z.B. 100 → löst bei 100, 200, 300… aus.',
        fn: 'Aktion', fnHelp: 'Der Trigger-Name aus deiner actions.mca. Der Befehl, den du für diesen Namen geschrieben hast, wird ausgeführt.',
        payload: 'Label', payloadHelp: 'Dieser Text ersetzt {user} in deinem actions.mca-Befehl. Z.B. „Community" → {user} wird zu „Community".',
        add: '+ Trigger hinzufügen',
      }
    }[lang];
    const rows = (triggers || []).map((t, i) => {
      const enabled = t.enabled !== false;
      return `<div class="like-trigger-card">
        <div class="like-trigger-header">
          <span class="like-trigger-number">#${i + 1}</span>
          <label class="like-trigger-toggle">
            <input type="checkbox" class="toggle" data-li-enabled="${i}" ${enabled ? 'checked' : ''} onchange="this.closest('.like-trigger-card').classList.toggle('disabled',!this.checked); this.nextElementSibling.textContent=this.checked?'ON':'OFF'">
            <span class="toggle-label">${enabled ? 'ON' : 'OFF'}</span>
          </label>
          <button class="btn-icon" onclick="editor.removeLikeTrigger('${path}', ${i})" title="${T.remove}">&times;</button>
        </div>
        <div class="like-trigger-body">
          <div class="like-trigger-field">
            <label>${T.id}</label>
            <input type="text" data-li-id="${i}" value="${escapeHtml(t.id || '')}" placeholder="e.g. likes_standard">
            <span class="like-trigger-hint">${T.idHelp}</span>
          </div>
          <div class="like-trigger-field">
            <label>${T.every}</label>
            <input type="number" data-li-every="${i}" value="${t.every || 100}" min="1">
            <span class="like-trigger-hint">${T.everyHelp}</span>
          </div>
          <div class="like-trigger-field">
            <label>${T.fn}</label>
            <input type="text" data-li-function="${i}" value="${escapeHtml(t.function || '')}" placeholder="e.g. likes">
            <span class="like-trigger-hint">${T.fnHelp}</span>
          </div>
          <div class="like-trigger-field">
            <label>${T.payload}</label>
            <input type="text" data-li-payload="${i}" value="${escapeHtml(t.payload || 'Community')}" placeholder="Community">
            <span class="like-trigger-hint">${T.payloadHelp}</span>
          </div>
        </div>
      </div>`;
    }).join('');
    return `<div class="editor-field full-width" data-path="${path}">
      <div class="field-label" style="font-size:1rem;font-weight:600;">Like Triggers</div>
      <div class="field-widget">
        <p class="field-desc" style="margin-bottom:0.75rem;">${escapeHtml(getHelp(path) || 'Fire actions when total stream likes reach a threshold.')}</p>
        <div class="like-trigger-list" id="${id}_list">${rows}</div>
        <button class="btn btn-secondary" style="margin-top:0.5rem;" onclick="editor.addLikeTrigger('${path}')">${T.add}</button>
      </div>
    </div>`;
  }

  /** Append a like trigger. */
  addLikeTrigger(path) {
    const arr = this.getValue(path) || [];
    arr.push({ id: '', every: 100, function: '', payload: 'Community', enabled: true });
    this.setValue(path, arr);
    this.render();
  }

  /** Remove a like trigger. */
  removeLikeTrigger(path, index) {
    const arr = this.getValue(path) || [];
    if (index >= 0 && index < arr.length) { arr.splice(index, 1); this.setValue(path, arr); this.render(); }
  }

  /** Collect like-trigger values from the form. */
  collectLikeTriggers() {
    const path = 'like_triggers';
    const current = this.getValue(path);
    if (!Array.isArray(current)) return;
    const firstEl = this.content.querySelector('[data-li-id="0"]');
    if (!firstEl) return;
    const triggers = [];
    for (let i = 0; i < current.length; i++) {
      const enEl = this.content.querySelector(`[data-li-enabled="${i}"]`);
      const idEl = this.content.querySelector(`[data-li-id="${i}"]`);
      const evEl = this.content.querySelector(`[data-li-every="${i}"]`);
      const fnEl = this.content.querySelector(`[data-li-function="${i}"]`);
      const plEl = this.content.querySelector(`[data-li-payload="${i}"]`);
      if (!idEl) continue;
      triggers.push({
        id: idEl.value,
        every: evEl ? Number(evEl.value) || 100 : 100,
        function: fnEl ? fnEl.value : '',
        payload: plEl ? plEl.value : 'Community',
        enabled: enEl ? enEl.checked : true
      });
    }
    this.setValue(path, triggers);
  }

  /** Build the outbound notification editor. */
  buildOutboundEditor(path, value) {
    const lang = _editorLangIsDe() ? 'de' : 'en';
    const T = {
      en: {
        title: 'How it works',
        intro: 'Every matching live event is sent to your webhook in real time — e.g. announce gifts, follows or subscribers automatically in your Discord server.',
        steps: [
          'Create a webhook: Discord → Server Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL.',
          'Click "+ Add Channel" below, give it a name and paste the URL.',
          'Choose which events to forward, e.g. "tiktok.gift, tiktok.follow" or "tiktok.*" for everything (comma-separated).',
          'Keep Format "Discord", adjust the message template ({user}, {type}, {comment} …) and switch the channel ON.',
        ],
        note: 'Format "Raw" sends a plain JSON envelope instead — useful for your own scripts and bots. Failed deliveries are retried automatically; a channel that keeps failing pauses itself briefly.',
      },
      de: {
        title: 'So funktioniert es',
        intro: 'Jedes passende Live-Event wird in Echtzeit an deinen Webhook gesendet — z. B. Geschenke, Follows oder Subscriber automatisch in deinem Discord-Server ankündigen.',
        steps: [
          'Webhook erstellen: Discord → Servereinstellungen → Integrationen → Webhooks → Neuer Webhook → Webhook-URL kopieren.',
          'Unten auf „+ Channel hinzufügen" klicken, Namen vergeben und URL einfügen.',
          'Events wählen, z. B. „tiktok.gift, tiktok.follow" oder „tiktok.*" für alles (komma-getrennt).',
          'Format „Discord" lassen, Nachrichtenvorlage anpassen ({user}, {type}, {comment} …) und den Channel einschalten.',
        ],
        note: 'Format „Raw" sendet stattdessen einen reinen JSON-Envelope — nützlich für eigene Skripte und Bots. Fehlgeschlagene Zustellungen werden automatisch wiederholt; ein dauerhaft fehlschlagender Channel pausiert sich kurz selbst.',
      }
    }[lang];
    const box = `<div style="background:var(--color-bg);border:1px solid var(--color-border);border-left:3px solid var(--color-accent);border-radius:var(--radius-md);padding:var(--space-3);margin-bottom:var(--space-4);">
      <div style="font-weight:600;font-size:0.9rem;margin-bottom:0.35rem;">${escapeHtml(T.title)}</div>
      <p style="margin:0 0 0.5rem 0;font-size:0.85rem;color:var(--text-secondary);">${escapeHtml(T.intro)}</p>
      <ol style="margin:0;padding-left:1.25rem;font-size:0.85rem;color:var(--text-secondary);">
        ${T.steps.map(s => `<li style="margin-bottom:0.25rem;">${escapeHtml(s)}</li>`).join('')}
      </ol>
      <p style="margin:0.5rem 0 0 0;font-size:0.8rem;color:var(--text-secondary);">${escapeHtml(T.note)}</p>
    </div>`;
    return box + this.buildObjectFields(path, value);
  }

  /** Build the outbound channel editor. */
  buildOutboundChannelsEditor(path, channels) {
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const help = getHelp(path);
    const lang = _editorLangIsDe() ? 'de' : 'en';
    const T = {
      en: {
        add: '+ Add Channel', remove: 'Remove channel',
        name: 'Name', nameHint: 'Unique channel name, e.g. "discord-events".',
        url: 'Webhook URL', urlHint: 'Full HTTPS URL the events are POSTed to.',
        format: 'Format', raw: 'Raw (JSON envelope)', discord: 'Discord',
        template: 'Template', templateHint: 'Discord only. Placeholders: {user}, {type}, {comment}, …',
        events: 'Event patterns', eventsHint: 'Comma-separated. Exact (tiktok.gift), wildcard (tiktok.*) or * for all.',
      },
      de: {
        add: '+ Channel hinzufügen', remove: 'Channel entfernen',
        name: 'Name', nameHint: 'Eindeutiger Channel-Name, z. B. "discord-events".',
        url: 'Webhook-URL', urlHint: 'Vollständige HTTPS-URL, an die Events gesendet werden.',
        format: 'Format', raw: 'Raw (JSON-Envelope)', discord: 'Discord',
        template: 'Template', templateHint: 'Nur Discord. Platzhalter: {user}, {type}, {comment}, …',
        events: 'Event-Patterns', eventsHint: 'Komma-getrennt. Exakt (tiktok.gift), Wildcard (tiktok.*) oder * für alle.',
      }
    }[lang];
    const rows = (channels || []).map((ch, i) => {
      const enabled = ch.enabled !== false;
      const fmt = ch.format || 'raw';
      const eventsVal = Array.isArray(ch.events) ? ch.events.join(', ') : '';
      return `<div class="like-trigger-card">
        <div class="like-trigger-header">
          <span class="like-trigger-number">#${i + 1}</span>
          <label class="like-trigger-toggle">
            <input type="checkbox" class="toggle" data-path="${path}[${i}].enabled" data-type="bool" ${enabled ? 'checked' : ''} onchange="this.nextElementSibling.textContent=this.checked?'ON':'OFF'; editor.onFieldInput()">
            <span class="toggle-label">${enabled ? 'ON' : 'OFF'}</span>
          </label>
          <button class="btn-icon" onclick="editor.removeArrayItem('${path}', ${i})" title="${T.remove}">&times;</button>
        </div>
        <div class="like-trigger-body">
          <div class="like-trigger-field">
            <label>${T.name}</label>
            <input type="text" value="${escapeHtml(ch.name || '')}" placeholder="discord-events" data-path="${path}[${i}].name" data-type="string" oninput="editor.onFieldInput()">
            <span class="like-trigger-hint">${T.nameHint}</span>
          </div>
          <div class="like-trigger-field">
            <label>${T.url}</label>
            <input type="text" value="${escapeHtml(ch.url || '')}" placeholder="https://discord.com/api/webhooks/…" data-path="${path}[${i}].url" data-type="string" oninput="editor.onFieldInput()">
            <span class="like-trigger-hint">${T.urlHint}</span>
          </div>
          <div class="like-trigger-field">
            <label>${T.format}</label>
            <select data-path="${path}[${i}].format" data-type="string" onchange="editor.onFieldInput()">
              <option value="raw" ${fmt === 'raw' ? 'selected' : ''}>${T.raw}</option>
              <option value="discord" ${fmt === 'discord' ? 'selected' : ''}>${T.discord}</option>
            </select>
          </div>
          <div class="like-trigger-field">
            <label>${T.template}</label>
            <input type="text" value="${escapeHtml(ch.template || '')}" placeholder="**{user}** triggered *{type}*" data-path="${path}[${i}].template" data-type="string" oninput="editor.onFieldInput()">
            <span class="like-trigger-hint">${T.templateHint}</span>
          </div>
          <div class="like-trigger-field">
            <label>${T.events}</label>
            <input type="text" value="${escapeHtml(eventsVal)}" placeholder="tiktok.*" data-ob-events="${i}" oninput="editor.onFieldInput()">
            <span class="like-trigger-hint">${T.eventsHint}</span>
          </div>
        </div>
      </div>`;
    }).join('');
    return `<div class="editor-field full-width" data-path="${path}">
      <div class="field-label" style="font-size:1rem;font-weight:600;">Channels</div>
      <div class="field-widget">
        ${help ? `<p class="field-desc" style="margin-bottom:0.75rem;">${escapeHtml(help)}</p>` : ''}
        <div class="like-trigger-list" id="${id}_list">${rows}</div>
        <button class="btn btn-secondary" style="margin-top:0.5rem;" onclick="editor.addOutboundChannel('${path}')">${T.add}</button>
      </div>
    </div>`;
  }

  /** Append an outbound channel. */
  addOutboundChannel(path) {
    const arr = this.getValue(path) || [];
    arr.push({ name: '', url: '', events: ['tiktok.*'], format: 'raw', template: '', enabled: false });
    this.setValue(path, arr);
    this.render();
  }

  /** Collect outbound channel values from the form. */
  collectOutboundChannels() {
    const current = this.getValue('outbound.channels');
    if (!Array.isArray(current)) return;
    this.content.querySelectorAll('[data-ob-events]').forEach(el => {
      const idx = parseInt(el.getAttribute('data-ob-events'), 10);
      if (!current[idx]) return;
      current[idx].events = String(el.value || '')
        .split(',')
        .map(s => s.trim())
        .filter(Boolean);
    });
  }

  /** Build an editor for a primitive array. */
  buildPrimitiveArray(path, arr) {
    const help = getHelp(path);
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    return `<div class="editor-field full-width" data-path="${path}">
      <div class="field-label">${escapeHtml(toTitle(path.split('.').pop()))}</div>
      <div class="field-widget">
        <textarea id="${id}" data-path="${path}" data-type="json" rows="4" style="font-family:monospace;">${escapeHtml(JSON.stringify(arr, null, 2))}</textarea>
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
        <p class="field-desc">This list can be edited as raw JSON above. A visual editor for this list is not yet available.</p>
      </div>
    </div>`;
  }

  /** Render the preserved unknown-keys section. */
  buildUnknownSection() {
    let html = '<div class="section-card" id="section_unknown"><div class="section-header"><h3>Unrecognized Settings</h3></div>';
    html += '<div class="section-body"><p class="field-desc">The following settings were found in your config file but are not supported by the visual editor. They have been preserved and will remain in your config when you save.</p>';
    for (const [key, val] of Object.entries(this.unknownKeys)) {
      html += `<div class="unknown-section"><h4>${escapeHtml(key)}</h4><p class="field-desc">This setting is not recognized by the editor. It may be from a newer version of the tool, a custom plugin, or a typo. To edit it, use the raw YAML fallback below or edit config.yaml directly.</p><pre>${escapeHtml(JSON.stringify(val, null, 2))}</pre></div>`;
    }
    html += `<div class="yaml-fallback"><label style="font-size:0.85rem;font-weight:500;">Advanced: Raw YAML for unrecognized keys</label><textarea id="unknown_yaml" onchange="editor.parseUnknownYaml()">${escapeHtml(this.unknownKeysToYaml())}</textarea><p class="field-desc">Edit with caution. Invalid YAML will be rejected on save.</p></div>`;
    html += '</div></div>';
    return html;
  }

  /** Serialize preserved unknown keys to YAML. */
  unknownKeysToYaml() {
    // Very simplified YAML-like serialization for display
    let out = '';
    for (const [k, v] of Object.entries(this.unknownKeys)) {
      out += k + ':\n' + JSON.stringify(v, null, 2).split('\n').map(l => '  ' + l).join('\n') + '\n';
    }
    return out;
  }

  /** Parse the unknown-keys YAML editor. */
  parseUnknownYaml() {
    const raw = document.getElementById('unknown_yaml').value;
    try {
      // Naive YAML parser for top-level keys only
      const lines = raw.split('\n');
      const result = {};
      let currentKey = null;
      let currentLines = [];
      for (const line of lines) {
        if (!line.startsWith(' ') && line.includes(':')) {
          if (currentKey) {
            try { result[currentKey] = JSON.parse(currentLines.join('\n')); } catch (e) { result[currentKey] = currentLines.join('\n').trim(); }
          }
          currentKey = line.split(':')[0].trim();
          currentLines = [];
        } else if (currentKey) {
          currentLines.push(line);
        }
      }
      if (currentKey) {
        try { result[currentKey] = JSON.parse(currentLines.join('\n')); } catch (e) { result[currentKey] = currentLines.join('\n').trim(); }
      }
      this.unknownKeys = result;
      this.showToast(I18N.t('editor.unrecognizedUpdated'), 'info');
    } catch (e) {
      this.showToast(I18N.t('editor.yamlParseFailed', { msg: e.message }), 'error');
    }
  }

  /** Scroll a field into view. */
  scrollTo(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // Update active section state and re-render sidebar
    if (id.startsWith('section_')) {
      this.activeSection = id.substring('section_'.length);
      this.renderSidebar();
    }
  }

  /** Track the visible section while scrolling. */
  setupScrollSpy() {
    const main = document.querySelector('.editor-main');
    if (!main) return;
    if (this._observer) this._observer.disconnect();

    // Track which section is most visible
    const visibleRatios = new Map();

    this._observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const id = entry.target.id;
        if (id && id.startsWith('section_')) {
          visibleRatios.set(id, entry.intersectionRatio);
        }
      }

      // Pick the visible section with the highest ratio
      let bestId = null;
      let bestRatio = -1;
      for (const [id, ratio] of visibleRatios) {
        if (ratio > bestRatio) {
          bestRatio = ratio;
          bestId = id;
        }
      }

      if (bestId) {
        const key = bestId.substring('section_'.length);
        if (this.activeSection !== key) {
          this.activeSection = key;
          this.updateSidebarActive();
        }
      }
    }, {
      root: main,
      rootMargin: '-80px 0px -40% 0px',
      threshold: [0, 0.1, 0.25, 0.5, 0.75, 1]
    });

    for (const card of this.content.querySelectorAll('.section-card')) {
      this._observer.observe(card);
    }
  }

  /** Highlight the active section in the sidebar. */
  updateSidebarActive() {
    this.sidebar.querySelectorAll('.sidebar-item').forEach(item => {
      item.classList.remove('active');
    });
    const items = this.sidebar.querySelectorAll('.sidebar-item');
    for (const item of items) {
      const onClick = item.getAttribute('onclick');
      if (onClick && onClick.includes(`section_${this.activeSection}`)) {
        item.classList.add('active');
        // Scroll item into view within sidebar if needed
        item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        break;
      }
    }
  }

  /** Apply a search query to the editor. */
  onSearch(q) {
    this.searchQuery = q.trim().toLowerCase();
    this.render();
  }

  /* ─── Value helpers ─── */
  /** Return the config value at a path, or `undefined` when an intermediate key is missing. */
  getValue(path) {
    const keys = path.split(/\.|\[(\d+)\]/).filter(k => k !== '' && k !== undefined);
    let target = this.data;
    for (let i = 0; i < keys.length - 1; i++) {
      const k = keys[i];
      if (!(k in target)) return undefined;
      target = target[k];
    }
    return target[keys[keys.length - 1]];
  }

  /** Set a config value by path and mark the editor dirty. */
  setValue(path, value) {
    const keys = path.split(/\.|\[(\d+)\]/).filter(k => k !== '' && k !== undefined);
    let target = this.data;
    for (let i = 0; i < keys.length - 1; i++) {
      const k = keys[i];
      if (!(k in target)) {
        target[k] = /^\d+$/.test(keys[i + 1]) ? [] : {};
      }
      target = target[k];
    }
    target[keys[keys.length - 1]] = value;
  }

  /* ─── Collect from DOM ─── */
  /** Read simple fields and special editors from the DOM into the working config. */
  collect() {
    // Parse errors are derived from the current DOM pass. Fields can disappear
    // (array item removed, search filter, advanced mode), so keeping old
    // entries would block saving with an error the user cannot see.
    this.collectErrors.clear();
    // Simple inputs
    this.content.querySelectorAll('[data-path]').forEach(el => {
      const path = el.getAttribute('data-path');
      const type = el.getAttribute('data-type');
      if (!path || !type) return;
      if (el.tagName === 'INPUT' && el.type === 'checkbox' && el.classList.contains('toggle')) {
        this.setValue(path, el.checked);
      } else if (type === 'number') {
        const v = el.value.trim();
        this.setValue(path, v === '' ? 0 : Number(v));
      } else if (type === 'json') {
        try {
          this.setValue(path, JSON.parse(el.value));
          this.collectErrors.delete(path);
        } catch (e) {
          // Surface the parse error instead of silently discarding the edit;
          // validate() merges these into the field errors shown to the user.
          this.collectErrors.set(path, I18N.t('editor.invalidJson', { msg: e.message }));
        }
      } else {
        this.setValue(path, el.value);
      }
    });
    this.collectLikeTriggers();
    this.collectOutboundChannels();
  }

  /* ─── Validation ─── */
  /** Validate required, pattern, range and known special fields; return whether all pass. */
  validate() {
    this.errors.clear();
    // JSON parse failures collected during collect() override the field
    // validation: the stored data still holds the old value, so schema
    // checks alone would wrongly report a clean state.
    for (const [p, m] of this.collectErrors) this.errors.set(p, m);
    let ok = this.collectErrors.size === 0;
    for (const path of Object.keys(FIELD_META)) {
      const meta = FIELD_META[path];
      if (meta.required) {
        const val = this.getValue(path);
        if (val === '' || val === undefined || val === null) {
          this.errors.set(path, 'This field is required.');
          ok = false;
        }
      }
      if (meta.pattern) {
        const val = this.getValue(path);
        if (val && !meta.pattern.test(String(val))) {
          this.errors.set(path, 'Invalid format.');
          ok = false;
        }
      }
      if (meta.min !== undefined) {
        const val = this.getValue(path);
        if (val !== undefined && val !== '' && Number(val) < meta.min) {
          this.errors.set(path, `Must be at least ${meta.min}.`);
          ok = false;
        }
      }
      if (meta.max !== undefined) {
        const val = this.getValue(path);
        if (val !== undefined && val !== '' && Number(val) > meta.max) {
          this.errors.set(path, `Must be at most ${meta.max}.`);
          ok = false;
        }
      }
    }
    // Validate tiktok.user is not default
    const tiktokUser = this.getValue('tiktok.user');
    if (tiktokUser === 'your_tiktok_username') {
      this.errors.set('tiktok.user', 'Please change the default username to your actual TikTok username.');
      ok = false;
    }
    // Validate server_host
    const host = this.getValue('server_host');
    if (host && !/^(\d{1,3}\.){3}\d{1,3}|0\.0\.0\.0|127\.0\.0\.1$/.test(host)) {
      this.errors.set('server_host', 'Must be a valid IP address like 127.0.0.1 or 0.0.0.0.');
      ok = false;
    }
    return ok;
  }

  /* ─── Save flow ─── */
  /** Collect, validate and show the review diff before saving. */
  save() {
    this.collect();
    if (!this.validate()) {
      this.render(); // Show errors
      this.showToast(I18N.t('editor.fixErrors'), 'error');
      return;
    }
    this.mergeUnknownKeys();
    const diff = this.computeDiff();
    if (!diff.length) {
      this.showToast(I18N.t('editor.noChanges'), 'info');
      return;
    }
    const body = document.getElementById('review-body');
    body.innerHTML = diff.map(d => `<div class="review-item"><div class="review-path">${escapeHtml(d.path)}</div><div class="review-change"><span class="review-old">${escapeHtml(String(d.old))}</span> <span style="color:var(--text-secondary);">-></span> <span class="review-new">${escapeHtml(String(d.new))}</span></div></div>`).join('');
    document.getElementById('review-modal').classList.remove('hidden');
  }

  /** Hide the review dialog. */
  hideReview() {
    document.getElementById('review-modal').classList.add('hidden');
  }

  /** Persist the configuration through the API. */
  async confirmSave() {
    this.hideReview();
    try {
      const oldRcon = (this.original || {}).rcon || {};
      const newRcon = (this.data || {}).rcon || {};
      const rconPasswordSet = !oldRcon.password && newRcon.password;

      // Persist config_advanced into the saved file
      this.data.config_advanced = this._advancedMode;
      await putJSON('/config', { config: this.data, backup: true });
      this.original = JSON.parse(JSON.stringify(this.data));
      currentConfig = JSON.parse(JSON.stringify(this.data));
      this._updateSaveButton();
      await loadConfig();
      await postJSON('/reload', {});
      if (rconPasswordSet) {
        await postJSON('/server/restart', {});
      }
      this.showToast(I18N.t('editor.savedSuccess'), 'success');
    } catch (e) {
      this.showToast(I18N.t('editor.saveFailed', { msg: e.message }), 'error');
    }
  }

  /** Compute changed paths for the review diff. */
  computeDiff() {
    const changes = [];
    const walk = (obj, orig, path) => {
      const keys = new Set([...Object.keys(obj || {}), ...Object.keys(orig || {})]);
      for (const k of keys) {
        const p = path ? `${path}.${k}` : k;
        const v = obj?.[k];
        const o = orig?.[k];
        // Type mismatch: one is an array, the other is not (includes object vs array)
        if (Array.isArray(v) !== Array.isArray(o)) {
          if (JSON.stringify(v) !== JSON.stringify(o)) changes.push({ path: p, old: JSON.stringify(o), new: JSON.stringify(v) });
        } else if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
          walk(v, o, p);
        } else if (Array.isArray(v)) {
          if (JSON.stringify(v) !== JSON.stringify(o)) changes.push({ path: p, old: JSON.stringify(o), new: JSON.stringify(v) });
        } else {
          if (v !== o && !(o === undefined && v === '')) changes.push({ path: p, old: o === undefined ? '(none)' : o, new: v === undefined ? '(none)' : v });
        }
      }
    };
    walk(this.data, this.original, '');
    return changes;
  }

  /** Show an editor-local toast message. */
  showToast(msg, type) {
    const c = document.getElementById('toast-container');
    const t = document.createElement('div');
    t.className = 'toast ' + type;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.remove(), 4000);
  }

}

const editor = new ConfigEditor();
