/**
 * @file Schema-driven editor for hook configuration.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Hook Config Editor ─── */

/**
 * Schema-driven editor for a hook's `config.yaml`.
 *
 * Loads `/hooks/<name>/config`, renders categorized fields, supports search, advanced mode, validation, review/diff and save.
 */
class HookConfigEditor {
  /** Create the hook config editor and cache its DOM elements. */
  constructor() {
    this.hookName = null;
    this.displayName = null;
    this.config = {};
    this.schema = null;
    this.original = {};
    this.errors = new Map();
    this.collectErrors = new Map();
    this.searchQuery = '';
    this.sidebar = document.getElementById('hooks-config-sidebar');
    this.content = document.getElementById('hooks-config-content');
    this.searchInput = document.getElementById('hooks-config-search');
    this.saveBtn = document.getElementById('hooks-config-save');
    this.activeCategory = null;
    this.hasSchema = false;
    this._advancedMode = localStorage.getItem('hook_config_advanced_mode') === 'true';
  }

  /** Load the hook schema and current configuration from the API. */
  async _loadConfig(hookName) {
    try {
      const [cfgRes, schemaRes] = await Promise.all([
        fetchJSON(`/hooks/${encodeURIComponent(hookName)}/config`),
        fetchJSON(`/hooks/${encodeURIComponent(hookName)}/config/schema`)
      ]);
      this.config = JSON.parse(JSON.stringify(cfgRes.config || {}));
      this.original = JSON.parse(JSON.stringify(cfgRes.config || {}));
      this.schema = schemaRes.config_schema;
      this.hasSchema = !!(this.schema && this.schema.fields && this.schema.fields.length);
    } catch (e) {
      log('Failed to load hook config: ' + e.message, 'err');
      this.showToast(I18N.t('editor.loadFailed', { msg: e.message }), 'error');
      throw e;
    }
  }

  /** Open the hook editor inline for the selected hook. */
  async openInline(hookName, displayName) {
    this.hookName = hookName;
    this.displayName = displayName || hookName;
    this.searchQuery = '';
    this.searchInput.value = '';
    this.errors.clear();
    this.collectErrors.clear();

    try {
      await this._loadConfig(hookName);
    } catch (e) {
      return;
    }

    document.getElementById('hooks-config-title').textContent = escapeHtml(this.displayName) + ' Configuration';
    document.getElementById('hook-list-section').classList.add('hidden');
    document.getElementById('hooks-config-section').classList.remove('hidden');
    this.render();
    this.setupScrollSpy();
    this._updateSaveButton();
    this._updateAdvancedUI();
    this._attachInputListeners();
  }

  /** Filter the inline hook editor by a search query. */
  onInlineSearch(query) {
    this.searchQuery = query.toLowerCase();
    this.renderContent();
  }

  /** Return whether the editor has unsaved changes. */
  isDirty() {
    return JSON.stringify(this.config) !== JSON.stringify(this.original);
  }

  /** Update the save button from dirty and validation state. */
  _updateSaveButton() {
    const btn = document.getElementById('hooks-config-save');
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

  /** Close the inline editor and discard its transient state. */
  closeInline() {
    if (this.isDirty()) {
      showConfirmDialog(I18N.t('dialog.unsavedTitle'), I18N.t('dialog.unsavedGoBack'), I18N.t('common.goBack'), 'btn-danger').then(confirmed => {
        if (!confirmed) return;
        this._detachInputListeners();
        this.config = JSON.parse(JSON.stringify(this.original));
        this._updateSaveButton();
        this._hideInline();
      });
      return;
    }
    this._detachInputListeners();
    this._hideInline();
  }

  /** Hide the inline editor without resetting its data. */
  _hideInline() {
    document.getElementById('hooks-config-section').classList.add('hidden');
    document.getElementById('hook-list-section').classList.remove('hidden');
    document.getElementById('hook-review-modal').classList.add('hidden');
    document.querySelector('.nav-item[data-view="hooks"]')?.classList.add('active');
  }

  /** Toggle visibility of advanced fields. */
  _toggleAdvanced() {
    if (this._advancedMode) {
      this._advancedMode = false;
      localStorage.setItem('hook_config_advanced_mode', 'false');
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
      localStorage.setItem('hook_config_advanced_mode', 'true');
      this._updateAdvancedUI();
      this.render();
    };
    const handleCancel = () => { cleanup(); };

    if (okBtn) { okBtn.addEventListener('click', handleOk); }
    if (cancelBtn) { cancelBtn.addEventListener('click', handleCancel); }
  }

  /** Update the advanced-mode toggle and field visibility. */
  _updateAdvancedUI() {
    const btn = document.getElementById('hooks-config-advanced-btn');
    if (!btn) return;
    if (this._advancedMode) {
      btn.textContent = 'Advanced \u2713';
      btn.classList.add('active');
    } else {
      btn.textContent = I18N.t('common.advanced');
      btn.classList.remove('active');
    }
  }

  /** Render the complete editor. */
  render() {
    this.renderSidebar();
    this.renderContent();
    this.setupScrollSpy();
  }

  /** Render category navigation. */
  renderSidebar() {
    let html = '<div class="sidebar-header">Categories</div>';
    if (!this.hasSchema) {
      html += '<div class="sidebar-group"><a class="sidebar-item active" onclick="hookEditor.scrollTo(\'section_raw\')">Raw JSON</a></div>';
      this.sidebar.innerHTML = html;
      return;
    }

    const categories = this.groupByCategory();
    for (const [cat, fields] of Object.entries(categories)) {
      const catId = 'hook_cat_' + cat.replace(/[^a-zA-Z0-9]/g, '_');
      const hasErr = fields.some(f => this.fieldHasError(f.key));
      const isActive = this.activeCategory === cat;
      html += '<div class="sidebar-group">';
      html += `<a class="sidebar-item ${hasErr ? 'has-error' : ''} ${isActive ? 'active' : ''}" onclick="hookEditor.scrollTo('${catId}')">${escapeHtml(cat)}${hasErr ? '<span class="badge">!</span>' : ''}</a>`;
      html += '</div>';
    }
    this.sidebar.innerHTML = html;
  }

  /** Render configuration fields grouped by category. */
  renderContent() {
    if (!this.hasSchema) {
      this.content.innerHTML = this.buildRawEditor();
      return;
    }

    const categories = this.groupByCategory();
    let html = '';
    for (const [cat, fields] of Object.entries(categories)) {
      const catId = 'hook_cat_' + cat.replace(/[^a-zA-Z0-9]/g, '_');
      if (this.searchQuery && !this.categoryMatchesSearch(cat, fields)) continue;
      html += `<div class="section-card" id="${catId}">
        <div class="section-header"><h3>${escapeHtml(cat)}</h3></div>
        <div class="section-body">`;
      for (const field of fields) {
        if (this.searchQuery && !this.fieldMatchesSearch(field)) continue;
        const value = this.getConfigValue(field.key);
        html += this.buildSchemaField(field, value);
      }
      html += '</div></div>';
    }

    if (!html) {
      html = '<div class="search-empty"><h3>No results</h3><p>No settings match your search.</p></div>';
    }
    this.content.innerHTML = html;
  }

  /** Group schema fields into their categories. */
  groupByCategory() {
    const cats = {};
    if (!this.schema || !this.schema.fields) return cats;
    for (const field of this.schema.fields) {
      const cat = field.category || 'General';
      if (!cats[cat]) cats[cat] = [];
      cats[cat].push(field);
    }
    return cats;
  }

  /** Build the input control for one schema field. */
  buildSchemaField(field, value) {
    if (field.advanced && !this._advancedMode) {
      const label = field.label || toTitle(field.key.split('.').pop());
      const help = field.help || '';
      return `<div class="editor-field editor-field--locked" onclick="hookEditor._unlockAdvanced()">
        <div class="field-label">
          <span class="lock-icon">\uD83D\uDD12</span> ${escapeHtml(label)}
        </div>
        <div class="field-widget">
          <div class="locked-overlay">
            <span class="locked-text">Advanced setting — <a href="#" onclick="event.preventDefault();hookEditor._unlockAdvanced()">unlock advanced features</a> to edit</span>
          </div>
          ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
        </div>
      </div>`;
    }
    const path = field.key;
    const id = 'hf_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const isReq = field.required;
    const label = field.label || toTitle(path.split('.').pop());
    const help = field.help || '';
    const err = this.errors.get(path) || '';

    let widget;
    const ftype = field.type || 'string';

    if (ftype === 'boolean') {
      const checked = value ? 'checked' : '';
      widget = `<input type="checkbox" class="toggle" id="${id}" ${checked} data-path="${escapeHtml(path)}" data-type="bool">`;
    } else if (ftype === 'integer' || ftype === 'number') {
      const v = value !== undefined ? value : '';
      const minAttr = field.min !== undefined && field.min !== null ? ` min="${field.min}"` : '';
      const maxAttr = field.max !== undefined && field.max !== null ? ` max="${field.max}"` : '';
      widget = `<input type="number" id="${id}" value="${v}" data-path="${escapeHtml(path)}" data-type="number"${minAttr}${maxAttr}>`;
    } else if (ftype === 'select') {
      const opts = field.options || [];
      const optionsHtml = opts.map(o => `<option value="${escapeHtml(o)}" ${value === o ? 'selected' : ''}>${escapeHtml(o)}</option>`).join('');
      widget = `<select id="${id}" data-path="${escapeHtml(path)}" data-type="string">${optionsHtml}</select>`;
    } else if (ftype === 'color' || field.widget === 'color') {
      const colorVal = value || '#000000';
      widget = `<div class="color-row">
        <input type="color" id="${id}" value="${escapeHtml(colorVal)}" data-path="${escapeHtml(path)}" data-type="string" oninput="document.getElementById('${id}_hex').value=this.value">
        <input type="text" id="${id}_hex" value="${escapeHtml(colorVal)}" style="width:120px;padding:0.45rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.9rem;" oninput="document.getElementById('${id}').value=this.value" data-path="${escapeHtml(path)}" data-type="string">
      </div>`;
    } else if (field.secret || field.widget === 'password') {
      widget = `<input type="password" id="${id}" value="${escapeHtml(value || '')}" data-path="${escapeHtml(path)}" data-type="string">`;
    } else if (field.widget === 'textarea') {
      widget = `<textarea id="${id}" data-path="${escapeHtml(path)}" data-type="string" rows="3">${escapeHtml(value || '')}</textarea>`;
    } else if (ftype === 'array') {
      widget = this.buildArrayField(field, value, path, id);
    } else if (ftype === 'object') {
      widget = this.buildObjectField(field, value, path, id);
    } else {
      widget = `<input type="text" id="${id}" value="${escapeHtml(value !== undefined ? String(value) : '')}" data-path="${escapeHtml(path)}" data-type="string">`;
    }

    const isAdvanced = field.advanced;
    const fieldCls = isAdvanced ? 'editor-field editor-field--has-advanced' : 'editor-field';
    return `<div class="${fieldCls}" data-path="${escapeHtml(path)}">
      <div class="field-label">${escapeHtml(label)}${isReq ? '<span class="required">*</span>' : ''}${isAdvanced ? '<span class="advanced-badge" title="Advanced setting">!</span>' : ''}</div>
      <div class="field-widget">
        ${widget}
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
        <span class="field-error ${err ? 'visible' : ''}" id="${id}_err">${escapeHtml(err)}</span>
      </div>
    </div>`;
  }

  /** Build the array editor for a schema field. */
  buildArrayField(field, value, path, id) {
    const arr = Array.isArray(value) ? value : [];
    const itemSchema = field.item_schema || {};
    const itemType = itemSchema.type || 'string';

    if (itemType === 'object' && itemSchema.fields) {
      const cols = itemSchema.fields;
      let html = '<table class="array-table"><thead><tr>';
      for (const col of cols) {
        html += `<th>${escapeHtml(col.label || toTitle(col.key))}</th>`;
      }
      html += '<th></th></tr></thead><tbody>';
      for (let i = 0; i < arr.length; i++) {
        const item = arr[i] || {};
        html += '<tr>';
        for (const col of cols) {
          const cpath = `${path}[${i}].${col.key}`;
          const cid = id + '_r' + i + '_' + col.key.replace(/[^a-zA-Z0-9]/g, '_');
          const cval = item[col.key];
          if (col.type === 'boolean') {
            html += `<td><input type="checkbox" class="toggle" id="${cid}" ${cval ? 'checked' : ''} data-path="${escapeHtml(cpath)}" data-type="bool"></td>`;
          } else if (col.type === 'select') {
            const sopts = (col.options || []).map(o => `<option value="${escapeHtml(o)}" ${cval === o ? 'selected' : ''}>${escapeHtml(o)}</option>`).join('');
            html += `<td><select id="${cid}" data-path="${escapeHtml(cpath)}" data-type="string">${sopts}</select></td>`;
          } else if (col.type === 'integer' || col.type === 'number') {
            const cv = cval !== undefined ? cval : '';
            html += `<td><input type="number" id="${cid}" value="${cv}" data-path="${escapeHtml(cpath)}" data-type="number"></td>`;
          } else {
            html += `<td><input type="text" id="${cid}" value="${escapeHtml(cval !== undefined ? String(cval) : '')}" data-path="${escapeHtml(cpath)}" data-type="string"></td>`;
          }
        }
        html += `<td class="row-actions"><button class="btn-icon" onclick="hookEditor.removeArrayItem('${path}', ${i})">Remove</button></td></tr>`;
      }
      html += '</tbody></table>';
      html += `<button class="btn btn-secondary" style="margin-top:0.5rem;" onclick="hookEditor.addArrayObjectItem('${path}')">+ Add Row</button>`;
      return html;
    } else if (itemType === 'string') {
      const chips = arr.map((v, idx) => `<span class="tag-chip">${escapeHtml(v)}<span class="remove" onclick="hookEditor.removeTagByIndex('${path}', ${idx})">&times;</span></span>`).join('');
      return `<div class="tag-box" id="${id}_box">${chips}<input type="text" id="${id}_inp" placeholder="Add..." onkeydown="hookEditor.tagKey(event, '${path}')"></div>`;
    } else {
      return `<textarea id="${id}" data-path="${escapeHtml(path)}" data-type="json" rows="4" style="font-family:monospace;">${escapeHtml(JSON.stringify(arr, null, 2))}</textarea>`;
    }
  }

  /** Build the nested-object editor for a schema field. */
  buildObjectField(field, value, path, id) {
    const obj = (typeof value === 'object' && value !== null && !Array.isArray(value)) ? value : {};
    const subfields = field.item_schema ? (field.item_schema.fields || []) : [];
    if (!subfields.length) {
      return `<textarea id="${id}" data-path="${escapeHtml(path)}" data-type="json" rows="3" style="font-family:monospace;">${escapeHtml(JSON.stringify(obj, null, 2))}</textarea>`;
    }
    let html = '<div style="padding-left:1rem;border-left:2px solid var(--border);">';
    for (const sub of subfields) {
      const subpath = `${path}.${sub.key}`;
      const subval = obj[sub.key];
      html += this.buildSchemaField({ ...sub, key: subpath }, subval);
    }
    html += '</div>';
    return html;
  }

  /** Build the raw JSON fallback editor. */
  buildRawEditor() {
    return `<div class="section-card" id="section_raw">
      <div class="section-header"><h3>${I18N.t('hooks.rawConfig')}</h3></div>
      <div class="section-body">
        <p class="field-desc">${I18N.t('hooks.noSchema')}</p>
        <textarea id="hook-raw-json" rows="20" style="font-family:monospace;width:100%;" onchange="hookEditor.parseRawJson()">${escapeHtml(JSON.stringify(this.config, null, 2))}</textarea>
        <p class="field-desc">${I18N.t('hooks.noSchemaCareful')}</p>
      </div>
    </div>`;
  }

  /** Return whether a category contains a search match. */
  categoryMatchesSearch(cat, fields) {
    const q = this.searchQuery;
    if (cat.toLowerCase().includes(q)) return true;
    return fields.some(f => this.fieldMatchesSearch(f));
  }

  /** Return whether a field matches the search query. */
  fieldMatchesSearch(field) {
    const q = this.searchQuery;
    const label = (field.label || field.key || '').toLowerCase();
    const help = (field.help || '').toLowerCase();
    return label.includes(q) || help.includes(q);
  }

  /** Apply a search query to the editor. */
  onSearch(q) {
    this.searchQuery = q.trim().toLowerCase();
    this.render();
  }

  /** Read the current value at a dot-separated path. */
  getConfigValue(path) {
    const keys = path.split('.');
    let target = this.config;
    for (let i = 0; i < keys.length - 1; i++) {
      if (target === undefined || target === null) return undefined;
      target = target[keys[i]];
    }
    return target !== undefined && target !== null ? target[keys[keys.length - 1]] : undefined;
  }

  /** Write a value at a dot-separated path. */
  setConfigValue(path, value) {
    const keys = path.split('.');
    let target = this.config;
    for (let i = 0; i < keys.length - 1; i++) {
      if (!(keys[i] in target) || typeof target[keys[i]] !== 'object' || target[keys[i]] === null) {
        target[keys[i]] = {};
      }
      target = target[keys[i]];
    }
    target[keys[keys.length - 1]] = value;
  }

  /** Remove one array item and re-render. */
  removeArrayItem(path, index) {
    const arr = this.getConfigValue(path) || [];
    arr.splice(index, 1);
    this.setConfigValue(path, arr);
    this.render();
  }

  /** Append an empty object to an object array. */
  addArrayObjectItem(path) {
    const itemSchema = this.findFieldByPath(path)?.item_schema || {};
    const defaults = {};
    if (itemSchema.fields) {
      for (const f of itemSchema.fields) {
        if (f.default !== undefined) defaults[f.key] = f.default;
        else if (f.type === 'boolean') defaults[f.key] = false;
        else if (f.type === 'integer' || f.type === 'number') defaults[f.key] = 0;
        else defaults[f.key] = '';
      }
    }
    const arr = this.getConfigValue(path) || [];
    arr.push(defaults);
    this.setConfigValue(path, arr);
    this.render();
  }

  /** Remove a tag at the given index. */
  removeTagByIndex(path, idx) {
    const arr = this.getConfigValue(path) || [];
    if (idx >= 0 && idx < arr.length) { arr.splice(idx, 1); this.setConfigValue(path, arr); this.render(); }
  }

  /** Add the current tag input on Enter. */
  tagKey(e, path) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const val = e.target.value.trim();
    if (!val) return;
    const arr = this.getConfigValue(path) || [];
    if (!arr.includes(val)) { arr.push(val); this.setConfigValue(path, arr); }
    this.render();
    const id = 'hf_' + path.replace(/[^a-zA-Z0-9]/g, '_') + '_inp';
    setTimeout(() => { const el = document.getElementById(id); if (el) el.focus(); }, 0);
  }

  /** Parse the raw JSON editor into the working configuration. */
  parseRawJson() {
    // Scope the lookup to this editor: the dashboard keeps all editor sections
    // in the DOM, so a global id lookup could read another editor's field.
    const field = this.content.querySelector('#hook-raw-json');
    if (!field) return;
    const raw = field.value;
    try {
      const parsed = JSON.parse(raw);
      // The editor only works with a JSON object. Arrays, primitives and null
      // would make setConfigValue/getConfigValue throw on the next interaction.
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        this.showToast(I18N.t('editor.jsonObjectRequired'), 'error');
        return;
      }
      this.config = parsed;
      this.errors.clear();
      this.collectErrors.clear();
      this.showToast(I18N.t('editor.jsonValid'), 'info');
    } catch (e) {
      this.showToast(I18N.t('editor.jsonInvalid', { msg: e.message }), 'error');
    }
  }

  /** Return schema metadata for a configuration path. */
  findFieldByPath(path) {
    if (!this.schema || !this.schema.fields) return null;
    return this.schema.fields.find(f => f.key === path) || null;
  }

  /** Collect form values into a plain configuration object. */
  collect() {
    // Parse errors are derived from the current DOM pass. Fields can disappear
    // (array item removed, search filter, advanced mode), so keeping old
    // entries would block saving with an error the user cannot see.
    this.collectErrors.clear();
    if (!this.hasSchema) return;
    this.content.querySelectorAll('[data-path]').forEach(el => {
      const path = el.getAttribute('data-path');
      const type = el.getAttribute('data-type');
      if (!path || !type) return;
      if (el.tagName === 'INPUT' && el.type === 'checkbox' && el.classList.contains('toggle')) {
        this.setConfigValue(path, el.checked);
      } else if (type === 'number') {
        const v = el.value.trim();
        this.setConfigValue(path, v === '' ? undefined : Number(v));
      } else if (type === 'json') {
        try {
          this.setConfigValue(path, JSON.parse(el.value));
          this.collectErrors.delete(path);
        } catch (e) {
          // Surface the parse error instead of silently discarding the edit;
          // validate() merges these into the field errors shown to the user.
          this.collectErrors.set(path, I18N.t('editor.invalidJson', { msg: e.message }));
        }
      } else {
        this.setConfigValue(path, el.value);
      }
    });
  }

  /** Validate all fields and render their errors. */
  validate() {
    this.errors.clear();
    if (!this.hasSchema) {
      try { JSON.stringify(this.config); return true; }
      catch (e) { this.showToast(I18N.t('hooks.invalidJson'), 'error'); return false; }
    }
    // JSON parse failures collected during collect() override the field
    // validation: the stored config still holds the old value, so schema
    // checks alone would wrongly report a clean state.
    for (const [p, m] of this.collectErrors) this.errors.set(p, m);
    let ok = this.collectErrors.size === 0;
    for (const field of (this.schema.fields || [])) {
      const path = field.key;
      const value = this.getConfigValue(path);
      const err = this.validateField(field, value);
      if (err) {
        this.errors.set(path, err);
        ok = false;
      }
      if (field.type === 'array' && Array.isArray(value) && field.item_schema) {
        const itemType = field.item_schema.type;
        if (itemType === 'object') {
          const subfields = field.item_schema.fields || [];
          for (let i = 0; i < value.length; i++) {
            const item = value[i];
            for (const sub of subfields) {
              const subpath = `${path}[${i}].${sub.key}`;
              const suberr = this.validateField(sub, item[sub.key]);
              if (suberr) {
                this.errors.set(subpath, suberr);
                ok = false;
              }
            }
          }
        }
      }
      if (field.type === 'object' && field.item_schema && field.item_schema.fields) {
        const obj = (typeof value === 'object' && value !== null) ? value : {};
        for (const sub of field.item_schema.fields) {
          const subpath = `${path}.${sub.key}`;
          const suberr = this.validateField(sub, obj[sub.key]);
          if (suberr) {
            this.errors.set(subpath, suberr);
            ok = false;
          }
        }
      }
    }
    return ok;
  }

  /** Validate one field value against its schema. */
  validateField(field, value) {
    const ftype = field.type || 'string';
    if (field.required) {
      if (value === undefined || value === null || value === '') return 'This field is required.';
      if (ftype === 'array' && Array.isArray(value) && value.length === 0) return 'This field is required.';
    }
    if (value === undefined || value === null || value === '') return null;
    if (ftype === 'integer') {
      if (!Number.isInteger(Number(value))) return 'Must be an integer.';
    } else if (ftype === 'number') {
      if (isNaN(Number(value))) return 'Must be a number.';
    } else if (ftype === 'color' || field.widget === 'color') {
      if (!/^#[0-9a-fA-F]{6}$/.test(String(value))) return 'Must be a hex color like #RRGGBB.';
    } else if (ftype === 'select') {
      const opts = field.options || [];
      if (opts.length && !opts.includes(value)) return 'Must be one of: ' + opts.join(', ') + '.';
    }
    if ((ftype === 'integer' || ftype === 'number') && field.min !== undefined && field.min !== null) {
      if (Number(value) < field.min) return 'Must be at least ' + field.min + '.';
    }
    if ((ftype === 'integer' || ftype === 'number') && field.max !== undefined && field.max !== null) {
      if (Number(value) > field.max) return 'Must be at most ' + field.max + '.';
    }
    return null;
  }

  /** Return whether a field currently has a validation error. */
  fieldHasError(path) {
    for (const [epath, _] of this.errors) {
      if (epath === path || epath.startsWith(path + '.')) return true;
    }
    return false;
  }

  /** Validate and open the review dialog. */
  save() {
    this.collect();
    if (!this.validate()) {
      this.render();
      this.showToast(I18N.t('editor.fixErrors'), 'error');
      return;
    }
    const diff = this.computeDiff();
    if (!diff.length) {
      this.showToast(I18N.t('editor.noChanges'), 'info');
      return;
    }
    const body = document.getElementById('hook-review-body');
    body.innerHTML = diff.map(d => `<div class="review-item"><div class="review-path">${escapeHtml(d.path)}</div><div class="review-change"><span class="review-old">${escapeHtml(String(d.old))}</span> <span style="color:var(--text-secondary);">-></span> <span class="review-new">${escapeHtml(String(d.new))}</span></div></div>`).join('');
    document.getElementById('hook-review-modal').classList.remove('hidden');
  }

  /** Hide the review dialog. */
  hideReview() {
    document.getElementById('hook-review-modal').classList.add('hidden');
  }

  /** Persist the configuration through the API. */
  async confirmSave() {
    this.hideReview();
    try {
      const payload = JSON.parse(JSON.stringify(this.config));
      payload._backup = true;
      await putJSON(`/hooks/${encodeURIComponent(this.hookName)}/config`, payload);
      this.original = JSON.parse(JSON.stringify(this.config));
      this._updateSaveButton();
      this.closeInline();
      await loadHooks();
      this.showToast(I18N.t('hooks.configSaved'), 'success');
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
        if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
          walk(v, o, p);
        } else if (Array.isArray(v)) {
          if (JSON.stringify(v) !== JSON.stringify(o)) changes.push({ path: p, old: JSON.stringify(o), new: JSON.stringify(v) });
        } else {
          if (v !== o && !(o === undefined && v === '')) changes.push({ path: p, old: o === undefined ? '(none)' : o, new: v === undefined ? '(none)' : v });
        }
      }
    };
    walk(this.config, this.original, '');
    return changes;
  }

  /** Scroll a field into view. */
  scrollTo(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (id.startsWith('hook_cat_')) {
      this.activeCategory = id.substring(9).replace(/_/g, ' ');
      this.renderSidebar();
    }
  }

  /** Track the visible category while scrolling. */
  setupScrollSpy() {
    const main = document.querySelector('#view-hooks .editor-main');
    if (!main) return;
    if (this._observer) this._observer.disconnect();

    const visibleRatios = new Map();
    this._observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const id = entry.target.id;
        if (id && id.startsWith('hook_cat_')) {
          visibleRatios.set(id, entry.intersectionRatio);
        }
      }
      let bestId = null, bestRatio = -1;
      for (const [id, ratio] of visibleRatios) {
        if (ratio > bestRatio) { bestRatio = ratio; bestId = id; }
      }
      if (bestId) {
        const key = bestId.substring(9).replace(/_/g, ' ');
        if (this.activeCategory !== key) {
          this.activeCategory = key;
          this.updateSidebarActive();
        }
      }
    }, { root: main, rootMargin: '-80px 0px -40% 0px', threshold: [0, 0.1, 0.25, 0.5, 0.75, 1] });

    for (const card of this.content.querySelectorAll('.section-card')) {
      this._observer.observe(card);
    }
  }

  /** Highlight the active category in the sidebar. */
  updateSidebarActive() {
    this.sidebar.querySelectorAll('.sidebar-item').forEach(item => item.classList.remove('active'));
    const items = this.sidebar.querySelectorAll('.sidebar-item');
    for (const item of items) {
      const onClick = item.getAttribute('onclick');
      if (onClick && onClick.includes(`hook_cat_${this.activeCategory.replace(/[^a-zA-Z0-9]/g, '_')}`)) {
        item.classList.add('active');
        item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        break;
      }
    }
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

