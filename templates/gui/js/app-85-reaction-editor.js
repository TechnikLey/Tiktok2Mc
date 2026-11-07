/**
 * @file Reaction-event editor.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/**
 * Editor for event-to-plugin/command reactions.
 *
 * Provides catalog-backed four-step creation, editing, deletion and dirty tracking for reaction rules.
 */
class ReactionEditor {
  /** Create the reaction editor and cache its DOM elements. */
  constructor() {
    this.el = document.getElementById('reaction-editor');
    this.wizardEl = document.getElementById('reaction-wizard');
    this.content = document.getElementById('reaction-content');
    this.sidebar = document.getElementById('reaction-sidebar-categories');
    this.data = {};
    this.original = {};
    this._dirty = false;
    this.searchQuery = '';
    this.activeCategory = 'all';

    // Wizard state
    this.wizardStep = 0; // 0=event, 1=plugin, 2=command, 3=args+confirm
    this.wizardEditing = null; // null = creating, {event, idx} = editing
    this.wizardDraft = { event: '', plugin: '', command: '', args: {} };

    // Human-readable catalogs.
    // These are offline fallbacks only: the authoritative catalog is served
    // by GET /api/v1/reactions/catalog, assembled from each plugin's own
    // plugin.json (emitted_events / accepted_commands). loadCatalog() merges
    // the server data over these defaults at runtime.
    this.eventCatalog = {
      // TikTok
      'tiktok.follow': { name: 'New Follower', name_i18n: { en: 'New Follower', de: 'Neuer Follower' }, desc: 'When someone follows your TikTok account', desc_i18n: { en: 'When someone follows your TikTok account', de: 'Jemand folgt deinem TikTok-Account' }, category: 'tiktok', icon: '👤' },
      'tiktok.join': { name: 'Viewer Joins', name_i18n: { en: 'Viewer Joins', de: 'Zuschauer betritt' }, desc: 'When someone joins your live stream', desc_i18n: { en: 'When someone joins your live stream', de: 'Jemand betritt deinen Live-Stream' }, category: 'tiktok', icon: '🚪' },
      'tiktok.comment': { name: 'New Comment', name_i18n: { en: 'New Comment', de: 'Neuer Kommentar' }, desc: 'When someone sends a chat message', desc_i18n: { en: 'When someone sends a chat message', de: 'Jemand sendet eine Nachricht' }, category: 'tiktok', icon: '💬' },
      'tiktok.like': { name: 'New Like', name_i18n: { en: 'New Like', de: 'Neues Like' }, desc: 'When someone likes your stream', desc_i18n: { en: 'When someone likes your stream', de: 'Jemand liked deinen Stream' }, category: 'tiktok', icon: '❤️' },
      'tiktok.share': { name: 'New Share', name_i18n: { en: 'New Share', de: 'Neuer Share' }, desc: 'When someone shares your stream', desc_i18n: { en: 'When someone shares your stream', de: 'Jemand teilt deinen Stream' }, category: 'tiktok', icon: '🔗' },
      'tiktok.gift': { name: 'Gift Received', name_i18n: { en: 'Gift Received', de: 'Geschenk erhalten' }, desc: 'When someone sends a gift', desc_i18n: { en: 'When someone sends a gift', de: 'Jemand sendet ein Geschenk' }, category: 'tiktok', icon: '🎁' },
      // Minecraft
      'minecraft.player_death': { name: 'Player Dies', name_i18n: { en: 'Player Dies', de: 'Spieler stirbt' }, desc: 'When you or another player dies', desc_i18n: { en: 'When you or another player dies', de: 'Du oder ein anderer Spieler stirbt' }, category: 'minecraft', icon: '💀' },
      'minecraft.player_respawn': { name: 'Player Respawns', name_i18n: { en: 'Player Respawns', de: 'Spieler spawnt neu' }, desc: 'When a player respawns after dying', desc_i18n: { en: 'When a player respawns after dying', de: 'Ein Spieler spawnt nach dem Tod neu' }, category: 'minecraft', icon: '✨' },
      // Server
      'server.started': { name: 'Server Starts', name_i18n: { en: 'Server Starts', de: 'Server startet' }, desc: 'When the Minecraft server finishes starting', desc_i18n: { en: 'When the Minecraft server finishes starting', de: 'Der Minecraft-Server hat erfolgreich gestartet' }, category: 'server', icon: '🟢' },
      'server.stopping': { name: 'Server Stopping', name_i18n: { en: 'Server Stopping', de: 'Server stoppt' }, desc: 'When the Minecraft server begins to shut down', desc_i18n: { en: 'When the Minecraft server begins to shut down', de: 'Der Minecraft-Server fährt herunter' }, category: 'server', icon: '🛑' },
    };

    // Plugin/command catalogs start empty: everything plugin-owned comes
    // from GET /api/v1/reactions/catalog (assembled from each plugin's own
    // plugin.json). The frontend must not hardcode plugin metadata.
    this.pluginCatalog = {};

    this.commandCatalog = {};

    this.templates = [];

    this._bindEvents();
  }

  /** Wire navigation, search, save and wizard controls. */
  _bindEvents() {
    document.getElementById('reaction-add')?.addEventListener('click', () => this.startCreate());
    document.getElementById('reaction-wizard-back')?.addEventListener('click', () => this.wizardBack());
    document.getElementById('reaction-wizard-next')?.addEventListener('click', () => this.wizardNext());
    document.getElementById('reaction-wizard-cancel')?.addEventListener('click', () => this._closeWizard());
    document.getElementById('reaction-delete-cancel')?.addEventListener('click', () => this._hideDeleteModal());
  }

  /* ─── Public API ─── */

  /** Open the reaction editor, reload plugins and load reactions. */
  async open() {
    this.el.classList.remove('hidden');
    await loadPlugins();
    await this.load();
  }

  /** Close the editor and discard transient wizard state. */
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

  /** Fetch configured reactions and render the editor. */
  async load() {
    try {
      await this.loadCatalog();
      const res = await fetchJSON('/event-commands');
      this.data = JSON.parse(JSON.stringify(res.event_commands || {}));
      this.original = JSON.parse(JSON.stringify(this.data));
      this._dirty = false;
      this._updateSaveButton();
      this._updateDashboardSummary();
      this.renderSidebar();
      this.renderList();
    } catch (e) {
      showToast(I18N.t('reactions.loadFailed', { msg: e.message }), 'error');
    }
  }

  /** Load the plugin and command catalogs used by the wizard. */
  async loadCatalog() {
    try {
      const res = await fetchJSON('/reactions/catalog');
      if (!res || typeof res !== 'object') return;
      if (res.events && typeof res.events === 'object') {
        for (const [key, info] of Object.entries(res.events)) {
          this.eventCatalog[key] = info;
        }
      }
      if (res.plugins && typeof res.plugins === 'object') {
        for (const [key, info] of Object.entries(res.plugins)) {
          this.pluginCatalog[key] = { ...(this.pluginCatalog[key] || {}), ...info };
        }
      }
      if (res.commands && typeof res.commands === 'object') {
        for (const [key, cmds] of Object.entries(res.commands)) {
          if (cmds && typeof cmds === 'object') {
            this.commandCatalog[key] = { ...(this.commandCatalog[key] || {}), ...cmds };
          }
        }
      }
      if (Array.isArray(res.templates) && res.templates.length) {
        this.templates = res.templates;
      }
    } catch (e) {
      console.warn('Failed to load reaction catalog, using built-in defaults:', e);
    }
  }

  /** Return whether the editor has unsaved changes. */
  isDirty() {
    return this._dirty;
  }

  /** Apply a search query to the reaction list. */
  onSearch(q) {
    this.searchQuery = q.trim().toLowerCase();
    this.renderList();
  }

  /* ─── Dashboard summary ─── */

  /** Update the dashboard reaction count summary. */
  _updateDashboardSummary() {
    const el = document.getElementById('reactions-summary');
    if (!el) return;
    const count = Object.keys(this.data).reduce((sum, k) => sum + (this.data[k]?.length || 0), 0);
    if (count === 0) {
      el.innerHTML = '<span style="color:var(--text-secondary);">' + I18N.t('reactions.noReactionsSet') + '</span>';
    } else {
      el.innerHTML = `<span style="color:var(--success);">${count === 1 ? I18N.t('reactions.reactionCount', { count }) : I18N.t('reactions.reactionsCount', { count })}</span> <span style="color:var(--text-secondary);">${I18N.t('reactions.configured')}</span>`;
    }
  }

  /** Update the save button from dirty state. */
  _updateSaveButton() {
    const btn = document.getElementById('reaction-save');
    if (!btn) return;
    btn.disabled = !this._dirty;
    btn.style.opacity = this._dirty ? '1' : '0.5';
    btn.style.cursor = this._dirty ? 'pointer' : 'not-allowed';
  }

  /* ─── Sidebar / Filters ─── */

  /** Return the localized variant of a catalog field, falling back to the default value. */
  _localized(obj, field) {
    const i18nKey = field + '_i18n';
    if (obj[i18nKey]) {
      const lang = I18N.lang();
      if (obj[i18nKey][lang]) return obj[i18nKey][lang];
    }
    return obj[field] || '';
  }

  /** Turn a category identifier into a readable label. */
  _humanizeCategory(cat) {
    return cat
      .split(/[-_]/)
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

  /** Return the localized label for a reaction category. */
  _categoryLabel(cat) {
    const i18nMap = {
      all: 'reactions.categoryAll',
      tiktok: 'reactions.categoryTiktok',
      minecraft: 'reactions.categoryMinecraft',
      server: 'reactions.categoryServer',
      custom: 'reactions.categoryCustom',
    };
    if (i18nMap[cat]) return I18N.t(i18nMap[cat]);
    const plugin = this.pluginCatalog[cat];
    if (plugin && plugin.name) return plugin.name;
    return this._humanizeCategory(cat);
  }

  /** Render the category sidebar. */
  renderSidebar() {
    // Derive categories from the events that actually have reactions, so
    // plugin-defined categories appear automatically.
    const counts = new Map();
    for (const event of Object.keys(this.data)) {
      const actions = this.data[event] || [];
      if (!actions.length) continue;
      const info = this.eventCatalog[event];
      const cat = (info && info.category) || 'custom';
      counts.set(cat, (counts.get(cat) || 0) + actions.length);
    }
    const total = [...counts.values()].reduce((a, b) => a + b, 0);
    const categories = ['all', ...[...counts.keys()].sort()];
    let html = '';
    for (const cat of categories) {
      const count = cat === 'all' ? total : counts.get(cat);
      const active = this.activeCategory === cat ? 'active' : '';
      html += `<div class="sidebar-filter ${active}" onclick="reactionEditor.setCategory('${cat}')">
        <span>${escapeHtml(this._categoryLabel(cat))}</span>
        <span class="badge">${count}</span>
      </div>`;
    }
    this.sidebar.innerHTML = html;
  }

  /** Select a reaction category and render its events. */
  setCategory(cat) {
    this.activeCategory = cat;
    this.renderSidebar();
    this.renderList();
  }

  /* ─── List Rendering ─── */

  /** Render reactions for the active category and search query. */
  renderList() {
    const allEvents = Object.keys(this.data);
    const filtered = allEvents.filter(event => {
      const actions = this.data[event] || [];
      if (!actions.length) return false;
      const info = this.eventCatalog[event] || { name: event, category: 'custom' };
      if (this.activeCategory !== 'all') {
        if (this.activeCategory === 'custom') {
          if (info.category && info.category !== 'custom') return false;
        } else if (info.category !== this.activeCategory) {
          return false;
        }
      }
      if (this.searchQuery) {
        const q = this.searchQuery;
        const name = (info.name || event).toLowerCase();
        const hasMatch = name.includes(q) || actions.some(a => {
          const plugin = (this.pluginCatalog[a.target]?.name || a.target || '').toLowerCase();
          const cmd = (this.commandCatalog[a.target]?.[a.command]?.name || a.command || '').toLowerCase();
          return plugin.includes(q) || cmd.includes(q);
        });
        if (!hasMatch) return false;
      }
      return true;
    });

    if (!filtered.length) {
      this.renderEmptyState();
      return;
    }

    let html = '';
    for (const event of filtered) {
      const actions = this.data[event] || [];
      const info = this.eventCatalog[event] || { name: event, category: 'custom', icon: '⚡' };
      const catClass = `reaction-category-${info.category || 'custom'}`;
      const catLabel = this._categoryLabel(info.category);

      for (let idx = 0; idx < actions.length; idx++) {
        const action = actions[idx];
        const pluginInfo = this.pluginCatalog[action.target] || { name: action.target, icon: '🔌' };
        const cmdInfo = (this.commandCatalog[action.target] || {})[action.command] || { name: action.command };
        const plugin = currentPlugins.find(p => p.name === action.target);
        const pluginDisabled = !!plugin && !plugin.enabled;
        const disabledClass = pluginDisabled ? ' reaction-card--disabled' : '';
        const disabledNotice = pluginDisabled
          ? `<div class="reaction-disabled-notice">${I18N.t('reactions.disabledNotice', { plugin: escapeHtml(pluginInfo.name) })}</div>`
          : '';

        html += `<div class="reaction-card${disabledClass}">
          <div class="reaction-card-header">
            <div class="reaction-meta">
              <span class="reaction-category-badge ${catClass}">${escapeHtml(catLabel)}</span>
              <span style="font-size:0.75rem;color:var(--text-secondary);">${I18N.t('reactions.eventLabel', { name: escapeHtml(this._localized(info, 'name')) })}</span>
            </div>
            <div class="reaction-card-actions">
              <button class="reaction-btn-sm reaction-btn-test" onclick="reactionEditor.testReaction('${escapeHtml(event)}', ${idx})"${pluginDisabled ? ' disabled' : ''}>${I18N.t('reactions.test')}</button>
              <button class="reaction-btn-sm reaction-btn-edit" onclick="reactionEditor.startEdit('${escapeHtml(event)}', ${idx})">${I18N.t('reactions.edit')}</button>
              <button class="reaction-btn-sm reaction-btn-delete" onclick="reactionEditor.confirmDelete('${escapeHtml(event)}', ${idx})">${I18N.t('reactions.delete')}</button>
            </div>
          </div>
          ${disabledNotice}
          <div class="reaction-card-body">
            <div class="reaction-flow">
              <div class="reaction-when">
                <span style="font-size:1.1rem;">${info.icon || '⚡'}</span>
                <span>${escapeHtml(this._localized(info, 'name'))}</span>
              </div>
              <span class="reaction-arrow">→</span>
              <div class="reaction-then">
                <span style="font-size:1.1rem;">${pluginInfo.icon || '🔌'}</span>
                <span>${escapeHtml(this._localized(cmdInfo, 'name'))}</span>
              </div>
            </div>
            ${this._renderReactionArgs(action, cmdInfo)}
          </div>
        </div>`;
      }
    }
    this.content.innerHTML = html;
  }

  /** Render the argument fields for a reaction action. */
  _renderReactionArgs(action, cmdInfo) {
    const args = action.args || {};
    const keys = Object.keys(args);
    if (!keys.length) return '';
    const schema = (cmdInfo && cmdInfo.args) || {};
    const chips = keys.map(key => {
      const spec = schema[key] || {};
      const label = spec.label || key;
      let value = args[key];
      if (spec.type === 'select' && Array.isArray(spec.options)) {
        const opt = spec.options.find(o => String(o) === String(value));
        if (opt !== undefined) value = opt;
      }
      return `<span class="reaction-arg-chip">
        <span class="reaction-arg-key">${escapeHtml(label)}</span>
        <span class="reaction-arg-value">${escapeHtml(String(value))}</span>
      </span>`;
    }).join('');
    return `<div class="reaction-args">${chips}</div>`;
  }

  /** Render the empty state when no reactions exist. */
  renderEmptyState() {
    const isSearch = this.searchQuery !== '';
    const isFilter = this.activeCategory !== 'all';
    if (isSearch || isFilter) {
      this.content.innerHTML = `<div class="reaction-empty">
        <h3>${I18N.t('reactions.noResults')}</h3>
        <p>${I18N.t('reactions.noResultsDesc')}</p>
      </div>`;
      return;
    }
    let html = `<div class="reaction-empty">
      <h3>${I18N.t('reactions.noneYet')}</h3>
      <p>${I18N.t('reactions.emptyDesc')}</p>
      <button class="btn btn-primary" style="margin-top:1.5rem;padding:0.7rem 1.4rem;" onclick="reactionEditor.startCreate()">${I18N.t('reactions.createYourFirst')}</button>
    </div>`;
    this.content.innerHTML = html;
  }

  /* ─── Actions ─── */

  /** Start the wizard with an empty reaction draft. */
  startCreate() {
    this.wizardEditing = null;
    this.wizardStep = 0;
    this.wizardDraft = { event: '', plugin: '', command: '', args: {} };
    this._openWizard();
    this._renderWizard();
  }

  /** Start editing an existing reaction in the wizard. */
  startEdit(event, idx) {
    const action = this.data[event]?.[idx];
    if (!action) return;
    this.wizardEditing = { event, idx };
    this.wizardStep = 0;
    this.wizardDraft = {
      event: event,
      plugin: action.target || '',
      command: action.command || '',
      args: JSON.parse(JSON.stringify(action.args || {}))
    };
    this._openWizard();
    this._renderWizard();
  }

  /** Persist the current reaction configuration. */
  async save() {
    // Validate: every action must have a target and command
    for (const [event, actions] of Object.entries(this.data)) {
      for (const action of actions) {
        if (!action.target || !action.command) {
          showToast(I18N.t('reactions.incomplete', { event }), 'error');
          return;
        }
      }
    }
    try {
      await putJSON('/event-commands', { event_commands: this.data });
      this.original = JSON.parse(JSON.stringify(this.data));
      this._dirty = false;
      this._updateSaveButton();
      this._updateDashboardSummary();
      showToast(I18N.t('reactions.saved'), 'success');
    } catch (e) {
      showToast(I18N.t('reactions.saveFailed', { msg: e.message }), 'error');
      throw e;
    }
  }

  /** Send a test event for a configured reaction. */
  async testReaction(event, idx) {
    const action = this.data[event]?.[idx];
    if (!action) return;
    const plugin = currentPlugins.find(p => p.name === action.target);
    if (plugin && !plugin.enabled) {
      showToast(I18N.t('reactions.pluginDisabled', { plugin: action.target }), 'error');
      return;
    }
    try {
      // Publish to EventBus so the event-command mapper dispatches the reaction
      await postJSON('/events', { type: event, data: { test: true, source: 'reaction_test' } });
      // Also attempt to send via trigger service if it's a known TikTok event type
      const knownTiktokEvents = ['follow', 'join', 'share', 'comment', 'gift'];
      const tiktokPrefix = event.startsWith('tiktok.') ? event.slice(7) : '';
      if (knownTiktokEvents.includes(tiktokPrefix)) {
        await postJSON('/triggers/execute', {
          trigger: tiktokPrefix,
          user: 'TestUser',
        }).catch(() => {}); // fire-and-forget, bridge may not be running
      }
      const extra = tiktokPrefix ? I18N.t('reactions.testSentBridge') : '';
      showToast(I18N.t('reactions.testSent', { event, extra }), 'info');
    } catch (e) {
      showToast(I18N.t('reactions.testFailed', { msg: e.message }), 'error');
    }
  }

  /** Ask for confirmation before deleting a reaction. */
  confirmDelete(event, idx) {
    const action = this.data[event]?.[idx];
    if (!action) return;
    const evInfo = this.eventCatalog[event] || { name: event };
    const plInfo = this.pluginCatalog[action.target] || { name: action.target };
    const cmdInfo = (this.commandCatalog[action.target] || {})[action.command] || { name: action.command };
    const msg = I18N.t('reactions.deleteMessage') + ' "' + evInfo.name + ' → ' + cmdInfo.name + '"';
    document.getElementById('reaction-delete-message').textContent = msg;
    document.getElementById('reaction-delete-modal').classList.remove('hidden');
    const confirmBtn = document.getElementById('reaction-delete-confirm');
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
    newBtn.addEventListener('click', () => {
      this._hideDeleteModal();
      this._deleteReaction(event, idx);
    });
  }

  /** Hide the delete confirmation dialog. */
  _hideDeleteModal() {
    document.getElementById('reaction-delete-modal').classList.add('hidden');
  }

  /** Delete a reaction after confirmation. */
  _deleteReaction(event, idx) {
    if (!this.data[event]) return;
    this.data[event].splice(idx, 1);
    if (this.data[event].length === 0) {
      delete this.data[event];
    }
    this._dirty = true;
    this._updateSaveButton();
    this.renderSidebar();
    this.renderList();
    showToast(I18N.t('reactions.deleted'), 'info');
  }

  /* ─── Wizard ─── */

  /** Show the reaction wizard and reset its scroll position. */
  _openWizard() {
    this.wizardEl.classList.remove('hidden');
    requestAnimationFrame(() => {
      const body = this.wizardEl.querySelector('.reaction-wizard-body');
      if (body) body.scrollTop = 0;
    });
  }

  /** Close the reaction wizard. */
  _closeWizard() {
    this.wizardEl.classList.add('hidden');
  }

  /** Render the current wizard step. */
  _renderWizard() {
    const titleEl = document.getElementById('reaction-wizard-title');
    const stepsEl = document.getElementById('reaction-wizard-steps');
    const bodyEl = document.getElementById('reaction-wizard-body');
    const backBtn = document.getElementById('reaction-wizard-back');
    const nextBtn = document.getElementById('reaction-wizard-next');

    titleEl.textContent = this.wizardEditing ? I18N.t('reactions.wizardEdit') : I18N.t('reactions.wizardCreate');
    stepsEl.innerHTML = [0, 1, 2, 3].map(i => {
      let cls = '';
      if (i === this.wizardStep) cls = 'active';
      else if (i < this.wizardStep) cls = 'done';
      return `<div class="wizard-step-dot ${cls}"></div>`;
    }).join('');

    backBtn.style.visibility = this.wizardStep === 0 ? 'hidden' : 'visible';
    backBtn.textContent = I18N.t('wizard.back');
    nextBtn.textContent = this.wizardStep === 3 ? (this.wizardEditing ? I18N.t('reactions.saveChanges') : I18N.t('reactions.wizardCreate')) : I18N.t('wizard.next');
    nextBtn.disabled = false;

    if (this.wizardStep === 0) {
      bodyEl.innerHTML = this._renderStepEvent();
    } else if (this.wizardStep === 1) {
      bodyEl.innerHTML = this._renderStepPlugin();
    } else if (this.wizardStep === 2) {
      bodyEl.innerHTML = this._renderStepCommand();
    } else {
      bodyEl.innerHTML = this._renderStepConfirm();
    }
  }

  /** Render the event-selection step. */
  _renderStepEvent() {
    const standardLabels = {
      tiktok: I18N.t('reactions.categoryTiktok'),
      minecraft: I18N.t('reactions.categoryMinecraft'),
      server: I18N.t('reactions.categoryServer'),
    };
    // Standard groups first, then one group per plugin (named after the plugin).
    const groups = [];
    for (const cat of ['tiktok', 'minecraft', 'server']) {
      groups.push({ cat, label: standardLabels[cat], items: [] });
    }
    const extraGroups = new Map();
    for (const [key, info] of Object.entries(this.eventCatalog)) {
      const cat = info.category || 'custom';
      const group = groups.find(g => g.cat === cat);
      if (group) {
        group.items.push({ key, ...info });
      } else {
        if (!extraGroups.has(cat)) {
          const label = this.pluginCatalog[cat]?.name || this._humanizeCategory(cat);
          extraGroups.set(cat, { cat, label, items: [] });
        }
        extraGroups.get(cat).items.push({ key, ...info });
      }
    }
    for (const g of extraGroups.values()) groups.push(g);

    let html = `<h3>${I18N.t('reactions.step1Title')}</h3>
    <p class="muted-desc">${I18N.t('reactions.step1Desc')}</p>`;

    for (const g of Object.values(groups)) {
      if (!g.items.length) continue;
      html += `<div style="margin-bottom:1.25rem;"><strong style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">${escapeHtml(g.label)}</strong>`;
      html += `<div class="event-grid" style="margin-top:0.5rem;">`;
      for (const item of g.items) {
        const selected = this.wizardDraft.event === item.key ? 'selected' : '';
        html += `<div class="event-option ${selected}" onclick="reactionEditor.selectEvent('${escapeHtml(item.key)}')">
          <span class="event-icon">${item.icon}</span>
          <h4>${escapeHtml(this._localized(item, 'name'))}</h4>
          <p>${escapeHtml(this._localized(item, 'desc'))}</p>
        </div>`;
      }
      html += `</div></div>`;
    }

    // Custom event input
    const customVal = this.wizardDraft.event && !this.eventCatalog[this.wizardDraft.event] ? escapeHtml(this.wizardDraft.event) : '';
    html += `<div style="margin-top:1rem;padding-top:1rem;border-top:1px solid var(--border);">
      <strong style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">${I18N.t('common.advanced')}</strong>
      <p class="muted-desc">${I18N.t('reactions.customEventHint')}</p>
      <input type="text" id="custom-event-input" value="${customVal}" placeholder="custom.event.name" style="width:100%;padding:0.6rem 0.8rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:0.9rem;" oninput="reactionEditor.onCustomEventInput(this.value)" onchange="reactionEditor.selectEvent(this.value, true)">
    </div>`;

    return html;
  }

  /** Render the plugin-selection step. */
  _renderStepPlugin() {
    let html = `<h3>${I18N.t('reactions.step2Title')}</h3>
    <p class="muted-desc">${I18N.t('reactions.step2Desc', { name: escapeHtml((this.eventCatalog[this.wizardDraft.event]?.name) || this.wizardDraft.event) })}</p>`;

    html += `<div class="plugin-grid">`;
    for (const [key, info] of Object.entries(this.pluginCatalog)) {
      const selected = this.wizardDraft.plugin === key ? 'selected' : '';
      html += `<div class="plugin-option ${selected}" onclick="reactionEditor.selectPlugin('${escapeHtml(key)}')">
        <div style="font-size:1.5rem;">${info.icon}</div>
        <div class="plugin-option-name">${escapeHtml(this._localized(info, 'name'))}</div>
        <div class="plugin-option-desc">${escapeHtml(this._localized(info, 'desc'))}</div>
      </div>`;
    }
    html += `</div>`;

    return html;
  }

  /** Render the command-selection step. */
  _renderStepCommand() {
    let html = `<h3>${I18N.t('reactions.step3Title')}</h3>
    <p class="muted-desc">${I18N.t('reactions.step3Desc', { name: escapeHtml((this.pluginCatalog[this.wizardDraft.plugin]?.name) || this.wizardDraft.plugin) })}</p>`;

    const commands = this.commandCatalog[this.wizardDraft.plugin] || {};
    if (!this.wizardDraft.plugin || Object.keys(commands).length === 0) {
      html += `<div style="padding:1.5rem;text-align:center;color:var(--text-secondary);border:1px dashed var(--border);border-radius:8px;">${I18N.t('reactions.noCommandsAvailable')}</div>`;
      return html;
    }

    html += `<div class="command-grid">`;
    for (const [key, info] of Object.entries(commands)) {
      const selected = this.wizardDraft.command === key ? 'selected' : '';
      html += `<div class="command-option ${selected}" onclick="reactionEditor.selectCommand('${escapeHtml(key)}')">
        <h4>${escapeHtml(this._localized(info, 'name'))}</h4>
        <p>${escapeHtml(this._localized(info, 'desc'))}</p>
      </div>`;
    }
    html += `</div>`;

    return html;
  }

  /** Render the argument and confirmation step. */
  _renderStepConfirm() {
    const evInfo = this.eventCatalog[this.wizardDraft.event] || { name: this.wizardDraft.event, icon: '⚡', desc: 'Custom event' };
    const plInfo = this.pluginCatalog[this.wizardDraft.plugin] || { name: this.wizardDraft.plugin, icon: '🔌' };
    const cmdInfo = (this.commandCatalog[this.wizardDraft.plugin] || {})[this.wizardDraft.command] || { name: this.wizardDraft.command, desc: '' };

    let html = `<h3>${I18N.t('reactions.step4Title')}</h3>
    <p class="muted-desc">${I18N.t('reactions.step4Desc')}</p>`;

    html += `<div class="reaction-preview">
      <div class="reaction-preview-label">${I18N.t('reactions.preview')}</div>
      <div class="reaction-preview-flow">
        <div class="reaction-when"><span style="font-size:1.1rem;">${evInfo.icon}</span> <span>${escapeHtml(this._localized(evInfo, 'name'))}</span></div>
        <span class="reaction-arrow">→</span>
        <div class="reaction-then"><span style="font-size:1.1rem;">${plInfo.icon}</span> <span>${escapeHtml(this._localized(cmdInfo, 'name'))}</span></div>
      </div>
    </div>`;

    // Dynamic args form
    const argSchema = cmdInfo.args || {};
    const hasArgs = Object.keys(argSchema).length > 0;
    if (hasArgs) {
      html += `<div class="args-form" style="margin-top:1.25rem;">`;
      html += `<strong style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:0.75rem;">${I18N.t('reactions.options')}</strong>`;
      for (const [argKey, spec] of Object.entries(argSchema)) {
        const currentVal = this.wizardDraft.args[argKey] !== undefined ? this.wizardDraft.args[argKey] : (spec.default !== undefined ? spec.default : '');
        const id = `arg_${argKey}`;
        html += `<div class="form-group">`;
        html += `<label for="${id}">${escapeHtml(spec.label || argKey)}</label>`;
        if (spec.type === 'number') {
          html += `<input type="number" id="${id}" value="${escapeHtml(String(currentVal))}" ${spec.min !== undefined && spec.min !== null ? `min="${spec.min}"` : ''} ${spec.max !== undefined && spec.max !== null ? `max="${spec.max}"` : ''}>`;
        } else if (spec.type === 'select') {
          html += `<select id="${id}">${(spec.options || []).map(o => `<option value="${escapeHtml(o)}" ${o === currentVal ? 'selected' : ''}>${escapeHtml(o)}</option>`).join('')}</select>`;
        } else {
          html += `<input type="text" id="${id}" value="${escapeHtml(String(currentVal))}" placeholder="${escapeHtml(spec.placeholder || '')}">`;
        }
        if (spec.hint) html += `<div class="hint">${escapeHtml(spec.hint)}</div>`;
        html += `</div>`;
      }
      html += `</div>`;
    }

    return html;
  }

  /* ─── Wizard interactions ─── */

  /** Select an event for the reaction draft. */
  selectEvent(key, isCustom = false) {
    this.wizardDraft.event = key;
    this._renderWizard();
  }

  /** Track a custom event name entered by the user. */
  onCustomEventInput(value) {
    // Update draft without re-rendering so the input keeps focus
    this.wizardDraft.event = value;
  }

  /** Select a plugin in the wizard. */
  selectPlugin(key) {
    this.wizardDraft.plugin = key;
    this.wizardDraft.command = '';
    this.wizardDraft.args = {};
    this._renderWizard();
  }

  /** Select a command in the wizard. */
  selectCommand(key) {
    this.wizardDraft.command = key;
    const cmdInfo = (this.commandCatalog[this.wizardDraft.plugin] || {})[key] || {};
    // Pre-fill defaults
    this.wizardDraft.args = {};
    for (const [k, spec] of Object.entries(cmdInfo.args || {})) {
      if (spec.default !== undefined) this.wizardDraft.args[k] = spec.default;
    }
    this._renderWizard();
  }

  /** Move to the previous wizard step. */
  wizardBack() {
    if (this.wizardStep > 0) {
      this.wizardStep--;
      this._renderWizard();
    }
  }

  /** Validate and advance to the next wizard step. */
  wizardNext() {
    if (this.wizardStep === 0) {
      if (!this.wizardDraft.event) {
        showToast(I18N.t('reactions.selectEvent'), 'error');
        return;
      }
    } else if (this.wizardStep === 1) {
      if (!this.wizardDraft.plugin) {
        showToast(I18N.t('reactions.selectPlugin'), 'error');
        return;
      }
    } else if (this.wizardStep === 2) {
      if (!this.wizardDraft.command) {
        showToast(I18N.t('reactions.selectCommand'), 'error');
        return;
      }
    } else if (this.wizardStep === 3) {
      if (!this._collectArgs()) return;
      this._commitWizard();
      return;
    }
    this.wizardStep++;
    this._renderWizard();
  }

  /** Collect argument values from the wizard form. */
  _collectArgs() {
    const cmdInfo = (this.commandCatalog[this.wizardDraft.plugin] || {})[this.wizardDraft.command] || {};
    const schema = cmdInfo.args || {};
    for (const key of Object.keys(schema)) {
      const el = document.getElementById(`arg_${key}`);
      if (!el) continue;
      const spec = schema[key];
      if (spec.type === 'number') {
        let v = parseFloat(el.value);
        if (isNaN(v)) v = spec.default !== undefined ? spec.default : 0;
        if (spec.min !== undefined && spec.min !== null && v < spec.min) {
          showToast(I18N.t('reactions.minError', { label: spec.label || key, min: spec.min }), 'error');
          return false;
        }
        if (spec.max !== undefined && spec.max !== null && v > spec.max) {
          showToast(I18N.t('reactions.maxError', { label: spec.label || key, max: spec.max }), 'error');
          return false;
        }
        this.wizardDraft.args[key] = v;
      } else {
        this.wizardDraft.args[key] = el.value;
      }
    }
    return true;
  }

  /** Commit the wizard result to the working reaction list. */
  _commitWizard() {
    const { event, plugin, command, args } = this.wizardDraft;
    if (!event || !plugin || !command) {
      showToast(I18N.t('reactions.incompleteSteps'), 'error');
      return;
    }

    const newAction = { target: plugin, command, args: JSON.parse(JSON.stringify(args || {})) };

    if (this.wizardEditing) {
      // Edit existing
      const { event: oldEvent, idx } = this.wizardEditing;
      if (oldEvent === event) {
        this.data[event][idx] = newAction;
      } else {
        // Event changed: remove from old, add to new
        this.data[oldEvent].splice(idx, 1);
        if (this.data[oldEvent].length === 0) delete this.data[oldEvent];
        if (!this.data[event]) this.data[event] = [];
        this.data[event].push(newAction);
      }
    } else {
      // Create new
      if (!this.data[event]) this.data[event] = [];
      this.data[event].push(newAction);
    }

    this._dirty = true;
    this._updateSaveButton();
    this._closeWizard();
    this.renderSidebar();
    this.renderList();
    showToast(this.wizardEditing ? I18N.t('reactions.updated') : I18N.t('reactions.created'), 'success');
  }
}

