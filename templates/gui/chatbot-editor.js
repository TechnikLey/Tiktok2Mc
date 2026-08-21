/**
 * Chatbot editor — config/chatbot.yaml, encrypted TikTok session and live status.
 *
 * Reuses shared DOM/API helpers from app.js (fetchJSON, putJSON,
 * showToast, escapeHtml, I18N).  Loaded before app.js like the other
 * editor modules; app.js globals are only touched inside methods.
 */
class ChatbotEditor {
  constructor() {
    this.el = document.getElementById('chatbot-editor');
    this.data = {};
    this.original = {};
    this._dirty = false;
    this._keywords = [];
    this._status = null;
    this._sessionInfo = null;
    this._loginPolling = false;
    this._loginPollIntervalMs = 1500;
    this._bindEvents();
  }

  _bindEvents() {
    // Dirty-tracking for every config input inside the editor. Session
    // inputs are excluded — they are saved separately via their own API.
    const content = document.getElementById('chatbot-content');
    if (content) {
      content.addEventListener('input', e => {
        if (e.target.closest('#cb-session-card')) return;
        if (e.target.matches('input, textarea, select')) this._markDirty();
      });
      content.addEventListener('change', e => {
        if (e.target.closest('#cb-session-card')) return;
        if (e.target.matches('input, textarea, select')) this._markDirty();
      });
    }
    const addBtn = document.getElementById('cb-keyword-add');
    if (addBtn) {
      addBtn.addEventListener('click', () => {
        this._keywordRows().push({ keyword: '', reply: '' });
        this.renderKeywords();
        this._markDirty();
      });
    }
  }

  async open() {
    this.el.classList.remove('hidden');
    this._updateWebviewButton();
    await Promise.all([this.load(), this.loadSession()]);
    // Initial snapshot so the pill is correct before the next SSE event.
    try {
      const res = await fetchJSON('/chatbot/status');
      this._renderStatus(res.status || null);
    } catch (_) { /* bridge may not be running */ }
  }

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

  isDirty() { return this._dirty; }

  async load() {
    let cfg = {};
    try {
      const res = await fetchJSON('/chatbot/config');
      cfg = res.chatbot || {};
    } catch (e) {
      showToast(I18N.t('chatbot.loadFailed', { msg: e.message }), 'error');
    }
    this.data = JSON.parse(JSON.stringify(cfg));
    this.original = JSON.parse(JSON.stringify(cfg));
    this._dirty = false;
    this._updateSaveButton();
    this._applyToForm();
  }

  async save() {
    const payload = this._collect();
    try {
      const res = await putJSON('/chatbot/config', { chatbot: payload });
      this.data = JSON.parse(JSON.stringify(payload));
      this.original = JSON.parse(JSON.stringify(payload));
      this._dirty = false;
      this._updateSaveButton();
      if (res && res.reloaded === false) {
        showToast(I18N.t('chatbot.savedNoReload'), 'warning');
      } else {
        showToast(I18N.t('chatbot.saved'), 'success');
      }
    } catch (e) {
      showToast(I18N.t('chatbot.saveFailed', { msg: e.message }), 'error');
    }
  }

  /* ─── Form <-> data ─── */

  _applyToForm() {
    const d = this.data;
    const spam = d.spam_protection || {};
    const triggers = d.triggers || {};
    const templates = d.templates || {};

    document.getElementById('cb-enabled').checked = !!d.enabled;
    document.getElementById('cb-on-gift').checked = triggers.gift !== false;
    document.getElementById('cb-on-follow').checked = triggers.follow !== false;
    document.getElementById('cb-on-join').checked = triggers.join === true;
    document.getElementById('cb-gift-thanks').value = templates.gift_thanks ?? '';
    document.getElementById('cb-follow-thanks').value = templates.follow_thanks ?? '';
    document.getElementById('cb-join-welcome').value = templates.join_welcome ?? '';
    document.getElementById('cb-min-interval').value = spam.min_interval_s ?? 5;
    document.getElementById('cb-max-per-minute').value = spam.max_per_minute ?? 10;
    document.getElementById('cb-max-queue').value = spam.max_queue ?? 20;
    document.getElementById('cb-max-len').value = spam.max_len ?? 150;
    document.getElementById('cb-dedupe').checked = spam.dedupe_identical !== false;

    this._keywords = Object.entries(d.keyword_replies || {}).map(([keyword, reply]) => ({ keyword, reply }));
    this.renderKeywords();
    this._renderSessionWarning();
  }

  _collect() {
    const keywords = {};
    for (const row of this._keywordRows()) {
      const k = String(row.keyword || '').trim().toLowerCase();
      const v = String(row.reply || '').trim();
      if (k && v) keywords[k] = v;
    }
    return {
      enabled: document.getElementById('cb-enabled').checked,
      spam_protection: {
        min_interval_s: parseFloat(document.getElementById('cb-min-interval').value) || 0,
        max_per_minute: parseInt(document.getElementById('cb-max-per-minute').value, 10) || 10,
        max_queue: parseInt(document.getElementById('cb-max-queue').value, 10) || 20,
        max_len: parseInt(document.getElementById('cb-max-len').value, 10) || 150,
        dedupe_identical: document.getElementById('cb-dedupe').checked,
      },
      triggers: {
        gift: document.getElementById('cb-on-gift').checked,
        follow: document.getElementById('cb-on-follow').checked,
        join: document.getElementById('cb-on-join').checked,
      },
      templates: {
        gift_thanks: document.getElementById('cb-gift-thanks').value.trim(),
        follow_thanks: document.getElementById('cb-follow-thanks').value.trim(),
        join_welcome: document.getElementById('cb-join-welcome').value.trim(),
      },
      keyword_replies: keywords,
      session: { tt_target_idc: (this.data.session || {}).tt_target_idc || '' },
    };
  }

  /* ─── TikTok session (login) ─── */

  async loadSession() {
    try {
      this._sessionInfo = await fetchJSON('/chatbot/session');
    } catch (_) {
      this._sessionInfo = null;
    }
    this._renderSessionState();
    this._renderSessionWarning();
  }

  _renderSessionState() {
    const badge = document.getElementById('cb-session-badge');
    const badgeText = document.getElementById('cb-session-badge-text');
    const idcInput = document.getElementById('cb-session-idc');
    if (!badge || !badgeText) return;

    const info = this._sessionInfo;
    if (info && info.configured) {
      badge.classList.add('signed-in');
      badgeText.textContent = I18N.t('chatbot.sessionSignedIn', { id: info.masked_session_id || '' });
      if (idcInput && !idcInput.value) idcInput.value = info.tt_target_idc || '';
    } else {
      badge.classList.remove('signed-in');
      badgeText.textContent = I18N.t('chatbot.sessionMissing');
    }
  }

  /**
   * Warn when the bot would run without a login: sending is impossible
   * without a session, so an enabled bot without one is a misconfiguration.
   */
  _renderSessionWarning() {
    const warn = document.getElementById('cb-session-warning');
    if (!warn) return;
    const enabled = document.getElementById('cb-enabled')?.checked;
    const signedIn = !!(this._sessionInfo && this._sessionInfo.configured);
    if (enabled && !signedIn) {
      warn.textContent = I18N.t('chatbot.sessionWarnNoLogin');
      warn.classList.remove('hidden');
    } else {
      warn.classList.add('hidden');
    }
  }

  toggleSessionVisibility() {
    const field = document.querySelector('#cb-session-card .chatbot-secret-field');
    const input = document.getElementById('cb-session-id');
    if (!field || !input) return;
    const reveal = input.type === 'password';
    input.type = reveal ? 'text' : 'password';
    field.classList.toggle('revealed', reveal);
  }

  toggleSessionHelp() {
    document.getElementById('cb-session-steps')?.classList.toggle('hidden');
  }

  /* ─── Webview login (desktop app only, CHATBOT.md §5) ─── */

  _hasWebviewLogin() {
    const api = window.pywebview && window.pywebview.api;
    return !!(api && typeof api.open_tiktok_login === 'function');
  }

  _updateWebviewButton() {
    const btn = document.getElementById('cb-session-webview');
    if (!btn) return;
    btn.classList.toggle('hidden', !this._hasWebviewLogin());
  }

  async webviewLogin() {
    if (this._loginPolling) return;
    const api = window.pywebview && window.pywebview.api;
    if (!this._hasWebviewLogin()) {
      showToast(I18N.t('chatbot.webviewUnavailable'), 'warning');
      return;
    }
    let res;
    try {
      res = await api.open_tiktok_login();
    } catch (e) {
      showToast(I18N.t('chatbot.webviewFailed', { msg: e.message || e }), 'error');
      return;
    }
    if (res !== 'started') {
      showToast(I18N.t('chatbot.webviewAlreadyRunning'), 'warning');
      return;
    }
    this._setWebviewLoginBusy(true);
    this._loginPolling = true;
    try {
      for (;;) {
        await new Promise(resolve => setTimeout(resolve, this._loginPollIntervalMs));
        let state;
        try {
          state = await api.get_tiktok_login_state();
        } catch (_) {
          break; // bridge died — stop polling silently
        }
        if (!state || state.state === 'waiting') continue;
        await this._handleLoginState(state);
        break;
      }
    } finally {
      this._loginPolling = false;
      this._setWebviewLoginBusy(false);
    }
  }

  async _handleLoginState(state) {
    switch (state.state) {
      case 'success':
        showToast(I18N.t('chatbot.webviewSuccess', { id: state.masked_session_id || '' }), 'success');
        await this.loadSession();
        break;
      case 'cancelled':
        showToast(I18N.t('chatbot.webviewCancelled'), 'warning');
        break;
      case 'timeout':
        showToast(I18N.t('chatbot.webviewTimeout'), 'warning');
        break;
      case 'error':
        showToast(I18N.t('chatbot.webviewFailed', { msg: state.error || '?' }), 'error');
        break;
      default:
        break;
    }
  }

  _setWebviewLoginBusy(busy) {
    const btn = document.getElementById('cb-session-webview');
    if (!btn) return;
    btn.disabled = busy;
    if (busy) {
      btn.dataset.label = btn.textContent;
      btn.textContent = I18N.t('chatbot.webviewWaiting');
    } else if (btn.dataset.label) {
      btn.textContent = btn.dataset.label;
      delete btn.dataset.label;
    }
  }

  async saveSession() {
    const input = document.getElementById('cb-session-id');
    const idcInput = document.getElementById('cb-session-idc');
    const sessionId = String(input?.value || '').trim();

    // When nothing new was typed, keep the stored credentials untouched.
    if (!sessionId) {
      showToast(I18N.t('chatbot.sessionEmptyHint'), 'warning');
      return;
    }

    try {
      const info = await putJSON('/chatbot/session', {
        session_id: sessionId,
        tt_target_idc: String(idcInput?.value || '').trim() || null,
      });
      this._sessionInfo = info;
      if (input) input.value = '';
      this._renderSessionState();
      this._renderSessionWarning();
      this._applyStatusSession(this._status);
      showToast(I18N.t('chatbot.sessionSaved'), 'success');
    } catch (e) {
      showToast(I18N.t('chatbot.sessionSaveFailed', { msg: e.message }), 'error');
    }
  }

  async clearSession() {
    try {
      const confirmed = await showConfirmDialog(
        I18N.t('chatbot.sessionRemoveTitle'),
        I18N.t('chatbot.sessionRemoveConfirm'),
        I18N.t('common.delete'),
        'btn-danger'
      );
      if (!confirmed) return;
      this._sessionInfo = await fetch(API + '/chatbot/session', { method: 'DELETE', headers: _withApiKey({}) })
        .then(async res => {
          if (!res.ok) await _throwResError(res);
          return res.json();
        });
      const idcInput = document.getElementById('cb-session-idc');
      if (idcInput) idcInput.value = '';
      this._renderSessionState();
      this._renderSessionWarning();
      this._applyStatusSession(this._status);
      showToast(I18N.t('chatbot.sessionCleared'), 'success');
    } catch (e) {
      showToast(I18N.t('chatbot.sessionSaveFailed', { msg: e.message }), 'error');
    }
  }

  /* ─── Placeholder chips ─── */

  insertPlaceholder(text) {
    const activeId = ['cb-gift-thanks', 'cb-follow-thanks', 'cb-join-welcome']
      .find(id => document.activeElement?.id === id)
      || 'cb-gift-thanks';
    const input = document.getElementById(activeId);
    if (!input) return;
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? input.value.length;
    input.value = input.value.slice(0, start) + text + input.value.slice(end);
    input.focus();
    input.setSelectionRange(start + text.length, start + text.length);
    this._markDirty();
  }

  /* ─── Keyword rows ─── */

  _keywordRows() {
    if (!this._keywords) this._keywords = [];
    return this._keywords;
  }

  renderKeywords() {
    const list = document.getElementById('cb-keywords-list');
    if (!list) return;
    const rows = this._keywordRows();
    if (!rows.length) {
      list.innerHTML = `<p class="hint chatbot-no-keywords">${I18N.t('chatbot.noKeywords')}</p>`;
      return;
    }
    list.innerHTML = rows.map((row, i) => `
      <div class="chatbot-keyword-row" data-index="${i}">
        <input type="text" class="cb-kw" placeholder="${I18N.t('chatbot.keywordPlaceholder')}" value="${escapeHtml(row.keyword)}">
        <span class="chatbot-arrow">→</span>
        <input type="text" class="cb-reply" placeholder="${I18N.t('chatbot.replyPlaceholder')}" value="${escapeHtml(row.reply)}">
        <button type="button" class="chatbot-remove-btn" aria-label="Remove" onclick="chatbotEditor.removeKeyword(${i})">✕</button>
      </div>
    `).join('');
    list.querySelectorAll('.chatbot-keyword-row').forEach(rowEl => {
      const i = parseInt(rowEl.dataset.index, 10);
      rowEl.querySelector('.cb-kw').addEventListener('input', e => { this._keywordRows()[i].keyword = e.target.value; this._markDirty(); });
      rowEl.querySelector('.cb-reply').addEventListener('input', e => { this._keywordRows()[i].reply = e.target.value; this._markDirty(); });
    });
  }

  removeKeyword(i) {
    this._keywordRows().splice(i, 1);
    this.renderKeywords();
    this._markDirty();
  }

  /* ─── Dirty / save button ─── */

  _markDirty() {
    this._dirty = true;
    this._updateSaveButton();
  }

  _updateSaveButton() {
    const btn = document.getElementById('chatbot-save');
    if (!btn) return;
    btn.disabled = !this._dirty;
    btn.style.opacity = this._dirty ? '1' : '0.5';
    btn.style.cursor = this._dirty ? 'pointer' : 'not-allowed';
  }

  /* ─── Live status ─── */

  /**
   * Called by the central SSE dispatcher in app.js when a
   * ``chatbot.status`` event arrives (bridge → POST /events → SSE).
   */
  _renderStatus(status) {
    this._status = status;
    const pill = document.getElementById('chatbot-status-pill');
    const stats = document.getElementById('chatbot-stats');
    const heroTitle = document.getElementById('cb-hero-title');
    const heroSub = document.getElementById('cb-hero-sub');
    const heroDot = document.getElementById('cb-hero-dot');
    const errorBox = document.getElementById('chatbot-error');
    if (!pill || !stats) return;

    this._renderSessionWarning();

    if (!status) {
      pill.textContent = I18N.t('chatbot.stateUnknown');
      pill.className = 'chatbot-pill unknown';
      heroTitle.textContent = I18N.t('chatbot.stateUnknown');
      heroSub.textContent = I18N.t('chatbot.heroUnknownSub');
      heroDot.className = 'chatbot-pulse-dot';
      stats.innerHTML = '';
      errorBox.classList.add('hidden');
      return;
    }

    this._applyStatusSession(status);

    let heroKey;
    if (status.auto_disabled) {
      pill.textContent = I18N.t('chatbot.stateDisabled');
      pill.className = 'chatbot-pill error';
      heroTitle.textContent = I18N.t('chatbot.heroDisabledTitle');
      heroDot.className = 'chatbot-pulse-dot error';
    } else if (status.enabled) {
      pill.textContent = I18N.t('chatbot.stateOn');
      pill.className = 'chatbot-pill online';
      heroTitle.textContent = I18N.t('chatbot.stateOn');
      heroDot.className = 'chatbot-pulse-dot on';
    } else {
      pill.textContent = I18N.t('chatbot.stateOff');
      pill.className = 'chatbot-pill offline';
      heroTitle.textContent = I18N.t('chatbot.heroIdle');
      heroDot.className = 'chatbot-pulse-dot';
    }

    const subs = [];
    subs.push(status.connected ? I18N.t('chatbot.subConnected') : I18N.t('chatbot.subDisconnected'));
    if (status.has_session === false && status.enabled && !status.auto_disabled) {
      subs.push(I18N.t('chatbot.subNoSession'));
    }
    heroSub.textContent = subs.join(' · ');

    const items = [
      [I18N.t('chatbot.statSent'), status.sent_count ?? 0],
      [I18N.t('chatbot.statDropped'), status.dropped_count ?? 0],
      [I18N.t('chatbot.statQueued'), status.queue_size ?? 0],
    ];
    stats.innerHTML = items.map(([label, value]) => `
      <div class="chatbot-stat"><span class="chatbot-stat-value">${escapeHtml(String(value))}</span><span class="chatbot-stat-label">${escapeHtml(label)}</span></div>
    `).join('');

    if (status.last_error) {
      errorBox.textContent = status.last_error;
      errorBox.classList.remove('hidden');
    } else {
      errorBox.classList.add('hidden');
    }
  }

  /** Sync the topbar/session badge with the bridge-reported session flag. */
  _applyStatusSession(status) {
    if (!status || typeof status.has_session !== 'boolean') return;
    const badge = document.getElementById('cb-session-badge');
    const badgeText = document.getElementById('cb-session-badge-text');
    if (!badge || !badgeText) return;
    if (status.has_session && !(this._sessionInfo && this._sessionInfo.configured)) {
      badge.classList.add('signed-in');
      badgeText.textContent = I18N.t('chatbot.sessionSignedInBridge');
    }
  }
}

const chatbotEditor = new ChatbotEditor();
