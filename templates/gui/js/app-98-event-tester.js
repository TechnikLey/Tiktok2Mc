/**
 * @file Manual trigger/event tester.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */

/* ─── Event Tester ─── */
/**
 * Interactive trigger tester.
 *
 * Renders type-specific inputs, sends test triggers, toggles the TikTok connection and keeps a local history.
 */
class EventTester {
  /** Create the trigger tester and cache its DOM elements. */
  constructor() {
    this._cooldown = false;
    this._history = [];
    this._statusEl = document.getElementById('trigger-tester-status');
    this._errorEl = document.getElementById('trigger-error');
    this._historyEl = document.getElementById('trigger-history');
    this._gifts = [];
    this._selectedGift = null;
    this._giftSelectLoaded = false;
    this._milestones = [];
    this._selectedMilestone = null;
    this._milestonesLoaded = false;
  }

  /** Render inputs appropriate for the selected trigger type. */
  onTypeChange() {
    const type = document.getElementById('trigger-type').value;
    const customGroup = document.getElementById('custom-trigger-group');
    const giftGroup = document.getElementById('gift-trigger-group');
    const commentFields = document.getElementById('comment-fields');
    const likeMilestoneGroup = document.getElementById('like-milestone-group');
    if (customGroup) customGroup.style.display = type === 'custom' ? 'block' : 'none';
    if (giftGroup) giftGroup.style.display = type === 'gift' ? 'block' : 'none';
    if (commentFields) commentFields.style.display = type === 'comment' ? 'flex' : 'none';
    if (likeMilestoneGroup) likeMilestoneGroup.style.display = type === 'like' ? 'block' : 'none';

    if (type === 'gift' && !this._giftSelectLoaded) {
      this._loadGifts();
    }
    if (type === 'like' && !this._milestonesLoaded) {
      this._loadMilestones();
    }
  }

  /** Load the gift catalog for the trigger tester. */
  async _loadGifts() {
    try {
      const data = await fetchJSON('/gifts');
      this._gifts = data.gifts || [];
      this._giftSelectLoaded = true;
      this._renderGiftSelect(this._gifts);
    } catch (e) {
      showToast(I18N.t('triggers.giftsLoadFailed', { msg: e.message }), 'error');
      this._gifts = [];
    }
  }

  /** Load the configured like milestones. */
  async _loadMilestones() {
    try {
      const data = await fetchJSON('/triggers/like-milestones');
      this._milestones = (data.milestones || []).filter(m => m.enabled);
      this._milestonesLoaded = true;
      this._renderMilestoneSelect(this._milestones);
    } catch (e) {
      showToast(I18N.t('triggers.giftsLoadFailed', { msg: e.message }), 'error');
      this._milestones = [];
    }
  }

  /** Render the milestone selector. */
  _renderMilestoneSelect(milestones) {
    const select = document.getElementById('like-milestone-select');
    const info = document.getElementById('like-milestone-info');
    if (!select) return;
    select.innerHTML = '';
    if (!milestones.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = I18N.t('triggers.noMilestones');
      opt.disabled = true;
      select.appendChild(opt);
      if (info) info.textContent = '';
      return;
    }
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = I18N.t('triggers.chooseMilestone');
    placeholder.disabled = true;
    placeholder.selected = !this._selectedMilestone;
    select.appendChild(placeholder);
    for (const m of milestones) {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = `${m.id} — ${I18N.t('triggers.milestoneInfo', { every: m.every, function: m.function })}`;
      if (this._selectedMilestone && this._selectedMilestone.id === m.id) opt.selected = true;
      select.appendChild(opt);
    }
    if (info && this._selectedMilestone) {
      info.textContent = I18N.t('triggers.milestoneInfo', { every: this._selectedMilestone.every, function: this._selectedMilestone.function });
    } else if (info) {
      info.textContent = '';
    }
  }

  /** Update tester state after a milestone selection. */
  onMilestoneChange() {
    const select = document.getElementById('like-milestone-select');
    const info = document.getElementById('like-milestone-info');
    const id = select ? select.value : '';
    this._selectedMilestone = this._milestones.find(m => m.id === id) || null;
    if (info && this._selectedMilestone) {
      info.textContent = I18N.t('triggers.milestoneInfo', { every: this._selectedMilestone.every, function: this._selectedMilestone.function });
    } else if (info) {
      info.textContent = '';
    }
  }

  /** Render the gift selector. */
  _renderGiftSelect(gifts) {
    const container = document.getElementById('gift-select');
    if (!container) return;
    if (!gifts.length) {
      container.innerHTML = '<div class="gift-empty">' + I18N.t('triggers.noGifts') + '</div>';
      return;
    }
    const selectedId = this._selectedGift ? String(this._selectedGift.id) : '';
    container.innerHTML = gifts.map(g => {
      const imgPath = g.image_url || '';
      const selected = String(g.id) === selectedId ? ' gift-item-selected' : '';
      return `<div class="gift-item${selected}" data-gift-id="${g.id}" data-gift-name="${escapeHtml(g.name)}">
        <img src="${imgPath}" alt="${escapeHtml(g.name)}" class="gift-item-img" loading="lazy" onerror="this.style.display='none'">
        <div class="gift-item-info">
          <div class="gift-item-name">${escapeHtml(g.name)}</div>
          <div class="gift-item-meta">ID: ${g.id} &middot; ${g.coins} ${I18N.t('common.coins')}</div>
        </div>
      </div>`;
    }).join('');
    container._clickHandler = (e) => {
      const item = e.target.closest('.gift-item');
      if (!item) return;
      const id = parseInt(item.dataset.giftId);
      const name = item.dataset.giftName || '';
      this._selectGift(id, name);
    };
    container.removeEventListener('click', container._boundClick);
    container._boundClick = container._clickHandler.bind(this);
    container.addEventListener('click', container._boundClick);
  }

  /** Select a gift by id and display its name. */
  _selectGift(id, name) {
    this._selectedGift = { id: id, name: name };
    const hid = document.getElementById('gift-selected-id');
    if (hid) hid.value = id;
    const container = document.getElementById('gift-select');
    if (container) {
      container.querySelectorAll('.gift-item').forEach(el => {
        el.classList.toggle('gift-item-selected', parseInt(el.dataset.giftId) === id);
      });
    }
  }

  /** Filter the gift selector by search text. */
  onGiftSearch(query) {
    const q = (query || '').toLowerCase().trim();
    const filtered = q
      ? this._gifts.filter(g => (g.name || '').toLowerCase().includes(q) || String(g.id).includes(q))
      : this._gifts;
    this._renderGiftSelect(filtered);
  }

  /** Toggle the TikTok connection from the tester. */
  async toggleTiktok() {
    if (this._cooldown) {
      this._showError(I18N.t('triggers.pleaseWait'));
      return;
    }
    const turningOff = !_tiktokConnectDisabled;
    const confirmed = await showConfirmDialog(
      turningOff && _tiktokLiveState === true
        ? I18N.t('triggers.disconnectTitle')
        : I18N.t('triggers.toggleTitle'),
      turningOff && _tiktokLiveState === true
        ? I18N.t('triggers.disconnectWarning')
        : I18N.t('triggers.turnWarning', { state: turningOff ? I18N.t('triggers.off') : I18N.t('triggers.on') }),
      I18N.t('triggers.toggle'),
      'btn-danger'
    );
    if (!confirmed) return;

    this._cooldown = true;
    this._setStatus('running', I18N.t('triggers.toggling'));
    try {
      const result = await postJSON('/triggers/tiktok-connection', {});
      if (result.status === 'ok' || result.status === 'success') {
        _tiktokConnectDisabled = !result.connected;
        this._updateTiktokStateUI();
        this._setStatus('success', I18N.t('triggers.toggled'));
        showToast(I18N.t('triggers.connectionNow', { state: result.connected ? I18N.t('triggers.on') : I18N.t('triggers.off') }), 'success');
        log(`[TEST] TikTok connection toggled: ${result.connected ? 'ON' : 'OFF'}`, 'info');
      } else {
        this._setStatus('error', I18N.t('triggers.failed'));
        this._showError(result.message || I18N.t('triggers.toggleFailedTitle'));
        log(`[TEST ERROR] TikTok toggle: ${result.message}`, 'error');
      }
      this._addHistory('system', 'tiktok-toggle', 'System', result.status, result.message || '');
    } catch (e) {
      this._setStatus('error', I18N.t('triggers.failed'));
      this._showError(e.message);
      showToast(I18N.t('triggers.toggleFailed', { msg: e.message }), 'error');
      log(`[TEST ERROR] ${e.message}`, 'error');
      this._addHistory('system', 'tiktok-toggle', 'System', 'error', e.message);
    } finally {
      setTimeout(() => {
        this._cooldown = false;
        this._setStatus('offline', I18N.t('triggers.ready'));
      }, 1500);
    }
  }

  /** Update the TikTok connection indicator and button state. */
  _updateTiktokStateUI() {
    const label = document.getElementById('tiktok-connection-state');
    const btn = document.getElementById('btn-tiktok-toggle');
    if (!label || !btn) return;
    const tiktok = currentConfig.tiktok || {};
    let text, labelCls;
    if (_tiktokConnectDisabled) {
      text = I18N.t('triggers.off');
      labelCls = 'tiktok-state-label tiktok-state-off';
    } else {
      text = I18N.t('triggers.on');
      labelCls = 'tiktok-state-label tiktok-state-on';
    }
    label.textContent = text;
    label.className = labelCls;
    btn.textContent = I18N.t('triggers.toggleConnection');
    btn.className = 'btn btn--secondary';
  }

  /** Set the tester status message and style. */
  _setStatus(state, text) {
    if (!this._statusEl) return;
    this._statusEl.textContent = text;
    this._statusEl.className = 'console-status ' + state;
  }

  /** Display an error in the tester. */
  _showError(msg) {
    if (!this._errorEl) return;
    this._errorEl.textContent = msg;
    this._errorEl.classList.remove('hidden');
    setTimeout(() => this._errorEl.classList.add('hidden'), 5000);
  }

  /** Send the configured test trigger. */
  async sendTrigger() {
    if (this._cooldown) {
      this._showError(I18N.t('triggers.pleaseWaitTrigger'));
      return;
    }

    const typeSelect = document.getElementById('trigger-type');
    const type = typeSelect ? typeSelect.value : 'follow';
    let triggerName = type;
    let giftId = null;

    if (type === 'custom') {
      const customInput = document.getElementById('trigger-custom-name');
      triggerName = customInput ? customInput.value.trim() : '';
      if (!triggerName) {
        this._showError(I18N.t('triggers.customRequired'));
        return;
      }
    } else if (type === 'gift') {
      if (!this._selectedGift || !this._selectedGift.id) {
        this._showError(I18N.t('triggers.selectGiftRequired'));
        return;
      }
      giftId = String(this._selectedGift.id);
      triggerName = this._selectedGift.name || giftId;
    } else if (type === 'like') {
      if (!this._selectedMilestone || !this._selectedMilestone.function) {
        this._showError(I18N.t('triggers.selectMilestoneRequired'));
        return;
      }
      triggerName = this._selectedMilestone.function;
    }

    const userInput = document.getElementById('trigger-user');
    const user = userInput ? (userInput.value.trim() || 'TestUser') : 'TestUser';

    const confirmed = await showConfirmDialog(
      I18N.t('triggers.confirmTitle'),
      I18N.t('triggers.confirmMessage', {
        kind: type === 'comment' ? I18N.t('triggers.kindComment') : I18N.t('triggers.kindTrigger'),
        trigger: triggerName,
        user,
      }),
      I18N.t('common.send'),
      'btn-danger',
      'text-danger'
    );
    if (!confirmed) return;

    this._cooldown = true;
    this._setStatus('running', I18N.t('triggers.sending'));

    try {
      let result;
      if (type === 'comment') {
        const text = document.getElementById('comment-text').value.trim();
        if (!text) {
          this._showError(I18N.t('triggers.commentRequired'));
          this._setStatus('error', I18N.t('common.error'));
          this._cooldown = false;
          return;
        }
        const moderator = document.getElementById('comment-mod').checked;
        const superfan = document.getElementById('comment-sf').checked;
        const fanclub = document.getElementById('comment-fc').checked;
        result = await postJSON('/triggers/comment', {
          user, text, moderator, superfan, fanclub
        });
      } else {
        const payload = { trigger: triggerName, user };
        if (giftId) payload.gift_id = giftId;
        result = await postJSON('/triggers/execute', payload);
      }

      if (result.status === 'ok' || result.status === 'success') {
        this._setStatus('success', I18N.t('triggers.sent'));
        showToast(I18N.t('triggers.testSent'), 'success');
        log(`[TEST] ${type}: ${triggerName} (${user})`, 'info');
      } else {
        this._setStatus('error', I18N.t('triggers.failed'));
        this._showError(result.message || I18N.t('triggers.triggerFailedTitle'));
        showToast(I18N.t('triggers.triggerFailed', { msg: result.message || I18N.t('common.unknown') }), 'error');
        log(`[TEST ERROR] ${type}: ${result.message}`, 'error');
      }
      this._addHistory(type, triggerName, user, result.status, result.message || '');
    } catch (e) {
      this._setStatus('error', I18N.t('triggers.failed'));
      this._showError(e.message);
      showToast(I18N.t('triggers.triggerFailed', { msg: e.message }), 'error');
      log(`[TEST ERROR] ${e.message}`, 'error');
      this._addHistory(type, triggerName, user, 'error', e.message);
    } finally {
      setTimeout(() => {
        this._cooldown = false;
        this._setStatus('offline', I18N.t('triggers.ready'));
      }, 1500);
    }
  }

  /** Append an entry to the local trigger history. */
  _addHistory(kind, trigger, user, status, message) {
    const entry = {
      time: new Date().toLocaleTimeString(),
      kind,
      trigger,
      user,
      status,
      message
    };
    this._history.unshift(entry);
    if (this._history.length > 50) this._history.pop();
    this._renderHistory();
  }

  /** Render the local trigger history. */
  _renderHistory() {
    if (!this._historyEl) return;
    if (!this._history.length) {
      this._historyEl.innerHTML = '<p class="text-muted">' + I18N.t('triggers.noEvents') + '</p>';
      return;
    }
    this._historyEl.innerHTML = this._history.map(h => {
      const kindClass = h.kind === 'comment' ? 'kind-comment' : (h.kind === 'system' ? 'kind-system' : 'kind-trigger');
      const badgeClass = h.status === 'ok' || h.status === 'success' ? 'badge-success' : 'badge-error';
      let label = 'TRIGGER';
      if (h.kind === 'comment') label = 'COMMENT';
      else if (h.kind === 'system') label = 'SYSTEM';
      const detail = h.kind === 'comment' ? `${h.trigger}` : `${h.trigger} → ${h.user}`;
      return `<div class="trigger-history-entry">
        <span class="trigger-history-time">${escapeHtml(h.time)}</span>
        <span class="trigger-history-kind ${kindClass}">${label}</span>
        <span class="trigger-history-detail">${escapeHtml(detail)}</span>
        <span class="trigger-history-badge ${badgeClass}">${escapeHtml(h.status)}</span>
        ${h.message ? `<span class="trigger-history-message" title="${escapeHtml(h.message)}">${escapeHtml(h.message)}</span>` : ''}
      </div>`;
    }).join('');
  }

  /** Clear the local trigger history. */
  clearHistory() {
    this._history = [];
    this._renderHistory();
  }
}

const eventTester = new EventTester();

