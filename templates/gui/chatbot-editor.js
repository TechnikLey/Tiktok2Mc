/**
 * Chatbot editor — config/chatbot.yaml + live status.
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
    this._bindEvents();
  }

  _bindEvents() {
    document.getElementById('cb-keyword-add')?.addEventListener('click', () => {
      this._keywordRows().push({ keyword: '', reply: '' });
      this.renderKeywords();
      this._markDirty();
    });
    // Mark dirty on any input change inside the editor.
    this.el?.querySelector('input')?.closest('.editor-content')?.addEventListener('input', () => this._markDirty());
  }

  async open() {
    this.el.classList.remove('hidden');
    await this.load();
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
    const session = d.session || {};

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
      list.innerHTML = `<p class="hint">${I18N.t('chatbot.noKeywords')}</p>`;
      return;
    }
    list.innerHTML = rows.map((row, i) => `
      <div class="chatbot-keyword-row" data-index="${i}">
        <input type="text" class="cb-kw" placeholder="${I18N.t('chatbot.keywordPlaceholder')}" value="${escapeHtml(row.keyword)}">
        <span class="chatbot-arrow">→</span>
        <input type="text" class="cb-reply" placeholder="${I18N.t('chatbot.replyPlaceholder')}" value="${escapeHtml(row.reply)}">
        <button type="button" class="btn btn--secondary btn-sm" onclick="chatbotEditor.removeKeyword(${i})">✕</button>
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
    if (!pill || !stats) return;

    if (!status) {
      pill.textContent = I18N.t('chatbot.stateUnknown');
      pill.className = 'chatbot-pill unknown';
      stats.innerHTML = '';
      return;
    }

    if (status.auto_disabled) {
      pill.textContent = I18N.t('chatbot.stateDisabled');
      pill.className = 'chatbot-pill error';
    } else if (status.enabled) {
      pill.textContent = I18N.t('chatbot.stateOn');
      pill.className = 'chatbot-pill online';
    } else {
      pill.textContent = I18N.t('chatbot.stateOff');
      pill.className = 'chatbot-pill offline';
    }

    const items = [
      [I18N.t('chatbot.statSent'), status.sent_count ?? 0],
      [I18N.t('chatbot.statDropped'), status.dropped_count ?? 0],
      [I18N.t('chatbot.statQueued'), status.queue_size ?? 0],
    ];
    let html = items.map(([label, value]) => `
      <div class="chatbot-stat"><span class="chatbot-stat-value">${escapeHtml(String(value))}</span><span class="chatbot-stat-label">${escapeHtml(label)}</span></div>
    `).join('');
    if (status.last_error) {
      html += `<div class="chatbot-error">${escapeHtml(status.last_error)}</div>`;
    }
    stats.innerHTML = html;
  }
}

const chatbotEditor = new ChatbotEditor();
