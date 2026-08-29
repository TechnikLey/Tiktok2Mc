const API = '/api/v1';
let currentConfig = {};
let currentPlugins = [];
let currentHooks = [];
let wizardStep = 0;
let wizardData = {};

/* ─── API key (LAN dashboard access) ───
 * When the server is exposed beyond localhost (server_host: 0.0.0.0) with
 * an api_key configured, requests from other devices need it.  Provide it
 * by opening the dashboard as /gui/?key=YOUR_KEY; it is remembered in
 * localStorage and attached to every request (and the SSE stream).
 */
let _apiKey = (typeof localStorage !== 'undefined' && localStorage.getItem('tiktok2mc_api_key')) || '';
const _urlKey = new URLSearchParams(window.location.search).get('key');
if (_urlKey) {
  _apiKey = _urlKey;
  try { localStorage.setItem('tiktok2mc_api_key', _apiKey); } catch (_) {}
  const cleanUrl = window.location.href.replace(/([?&])key=[^&]*/, '$1').replace(/[?&]$/, '');
  window.history.replaceState({}, document.title, cleanUrl);
}
function _withApiKey(headers) {
  if (!_apiKey) return headers;
  return Object.assign({}, headers, { 'X-API-Key': _apiKey });
}

/* ─── API helpers ─── */
async function _parseErrorDetail(res) {
  try {
    const data = await res.json();
    if (data && data.detail) {
      return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    }
  } catch (_) { /* not JSON */ }
  try {
    const text = await res.text();
    if (text) return text.slice(0, 500);
  } catch (_) { /* body already consumed */ }
  return '';
}
async function _throwResError(res) {
  const detail = await _parseErrorDetail(res);
  if (res.status === 401) {
    showToast(I18N.t('dialog.missingKey'), 'error');
  }
  const friendly = typeof Help !== 'undefined'
    ? Help.formatApiError(res.status, detail)
    : res.status + ' ' + res.statusText + (detail ? ': ' + detail : '');
  throw new Error(friendly);
}
async function fetchJSON(path) {
  const res = await fetch(API + path, { headers: _withApiKey({}) });
  if (!res.ok) await _throwResError(res);
  return res.json();
}
async function postJSON(path, body) {
  const res = await fetch(API + path, {
    method: 'POST',
    headers: _withApiKey({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body)
  });
  if (!res.ok) await _throwResError(res);
  return res.json();
}
async function putJSON(path, body) {
  const res = await fetch(API + path, {
    method: 'PUT',
    headers: _withApiKey({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body)
  });
  if (!res.ok) await _throwResError(res);
  return res.json();
}

/* ─── Shutdown Countdown (local — just closes the GUI window) ─── */
let _shutdownCountdownInterval = null;
let _shutdownCountdownValue = 30;
let _healthIntervalId = null;
let _statusIntervalId = null;
let _pluginsIntervalId = null;
let _hooksIntervalId = null;
let _closePollIntervalId = null;
let _uptimeIntervalId = null;
let _lastTiktokEventTime = 0;
let _tiktokLiveState = null; // null = unknown, true = live, false = not live
let _tiktokConnectDisabled = false; // bridge DISABLE_TIKTOK_CONNECT flag

/* ─── Server Manager Placeholder Data ─── */
let _serverManagerCache = null;
let _serverActionInProgress = false;

function _stopDashboardPolling() {
  if (_healthIntervalId) { clearInterval(_healthIntervalId); _healthIntervalId = null; }
  if (_statusIntervalId) { clearInterval(_statusIntervalId); _statusIntervalId = null; }
  if (_pluginsIntervalId) { clearInterval(_pluginsIntervalId); _pluginsIntervalId = null; }
  if (_hooksIntervalId) { clearInterval(_hooksIntervalId); _hooksIntervalId = null; }
  if (_uptimeIntervalId) { clearInterval(_uptimeIntervalId); _uptimeIntervalId = null; }
}

function _closeWindowForShutdown() {
  _stopDashboardPolling();
  if (_sseSource) { _sseSource.close(); _sseSource = null; }
  try { window.close(); } catch (_) {}
  if (typeof pywebview !== 'undefined' && pywebview.api) {
    try { pywebview.api.close_app(); } catch (_) {}
  }
}

function startLocalShutdownCountdown() {
  _shutdownCountdownValue = 30;
  const overlay = document.getElementById('shutdown-overlay');
  const display = document.getElementById('shutdown-countdown-display');
  const shutdownNowBtn = document.getElementById('btn-shutdown-now');
  const cancelBtn = document.getElementById('btn-shutdown-cancel');

  overlay.classList.remove('hidden');
  display.textContent = _shutdownCountdownValue + ' ' + I18N.t('dialog.seconds');
  shutdownNowBtn.disabled = false;
  cancelBtn.disabled = false;

  if (_shutdownCountdownInterval) clearInterval(_shutdownCountdownInterval);
  _shutdownCountdownInterval = setInterval(() => {
    _shutdownCountdownValue--;
    if (_shutdownCountdownValue <= 0) {
      clearInterval(_shutdownCountdownInterval);
      _shutdownCountdownInterval = null;
      display.textContent = I18N.t('dialog.shuttingDown');
      shutdownNowBtn.disabled = true;
      cancelBtn.disabled = true;
      _closeWindowForShutdown();
      return;
    }
  display.textContent = _shutdownCountdownValue + ' ' + I18N.t('dialog.seconds');
  }, 1000);
}

document.getElementById('btn-shutdown-now').addEventListener('click', () => {
  if (_shutdownCountdownInterval) {
    clearInterval(_shutdownCountdownInterval);
    _shutdownCountdownInterval = null;
  }
  document.getElementById('shutdown-countdown-display').textContent = I18N.t('dialog.shuttingDown');
  document.getElementById('btn-shutdown-now').disabled = true;
  document.getElementById('btn-shutdown-cancel').disabled = true;
  _closeWindowForShutdown();
});

document.getElementById('btn-shutdown-cancel').addEventListener('click', () => {
  if (_shutdownCountdownInterval) {
    clearInterval(_shutdownCountdownInterval);
    _shutdownCountdownInterval = null;
  }
  document.getElementById('shutdown-overlay').classList.add('hidden');
});

document.getElementById('btn-update-now').addEventListener('click', () => {
  hideUpdateNotification();
  triggerToolUpdate();
});

document.getElementById('btn-update-dismiss').addEventListener('click', hideUpdateNotification);

/* ─── Server Manager — lifecycle polling is started/stopped in view switch code ─── */

/* ─── Server Manager Modal Wiring ─── */
document.getElementById('server-create-cancel')?.addEventListener('click', closeServerCreateModal);
document.getElementById('server-create-confirm')?.addEventListener('click', confirmServerCreate);
document.getElementById('server-create-name')?.addEventListener('input', validateServerCreateForm);
document.getElementById('server-create-version')?.addEventListener('change', validateServerCreateForm);
document.getElementById('server-create-port')?.addEventListener('input', validateServerCreateForm);
document.getElementById('server-create-port')?.addEventListener('change', validateServerCreateForm);

document.getElementById('server-download-cancel')?.addEventListener('click', closeServerDownloadModal);
document.getElementById('server-download-confirm')?.addEventListener('click', confirmServerDownload);
document.getElementById('server-download-version')?.addEventListener('change', () => {
  const btn = document.getElementById('server-download-confirm');
  const sel = document.getElementById('server-download-version');
  if (btn && sel) btn.disabled = !sel.value;
});

document.getElementById('server-switch-cancel')?.addEventListener('click', closeServerSwitchModal);
document.getElementById('server-switch-download')?.addEventListener('click', () => {
  closeServerSwitchModal();
  openServerDownloadModal();
});

document.getElementById('server-custom-cancel')?.addEventListener('click', closeServerCustomModal);
document.getElementById('server-custom-confirm')?.addEventListener('click', confirmServerCustom);
document.getElementById('server-custom-name')?.addEventListener('input', validateServerCustomForm);
document.getElementById('server-custom-file')?.addEventListener('change', validateServerCustomForm);

/* ─── Dialogs ─── */
function showConfirmDialog(title, message, okText = I18N.t('common.confirm'), okClass = 'btn-primary', messageClass = '') {
  return new Promise((resolve) => {
    const dlg = document.getElementById('confirm-dialog');
    const titleEl = document.getElementById('confirm-title');
    const msgEl = document.getElementById('confirm-message');
    const okBtn = document.getElementById('btn-confirm-ok');
    const cancelBtn = document.getElementById('btn-confirm-cancel');

    titleEl.textContent = title;
    msgEl.textContent = message;
    msgEl.className = 'muted dialog-desc' + (messageClass ? ' ' + messageClass : '');
    okBtn.textContent = okText;
    okBtn.className = 'btn ' + okClass;

    const cleanup = () => {
      dlg.classList.add('hidden');
      document.removeEventListener('keydown', onKey);
      okBtn.replaceWith(okBtn.cloneNode(true));
      cancelBtn.replaceWith(cancelBtn.cloneNode(true));
    };

    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      cleanup();
      resolve(false);
    };

    const newOk = okBtn.cloneNode(true);
    const newCancel = cancelBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOk, okBtn);
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);

    newOk.addEventListener('click', () => { cleanup(); resolve(true); });
    newCancel.addEventListener('click', () => { cleanup(); resolve(false); });

    dlg.classList.remove('hidden');
    document.addEventListener('keydown', onKey);
  });
}

function showPromptDialog(title, message, defaultValue = '', okText = I18N.t('common.confirm'), okClass = 'btn-primary') {
  return new Promise((resolve) => {
    const dlg = document.getElementById('prompt-dialog');
    const titleEl = document.getElementById('prompt-title');
    const msgEl = document.getElementById('prompt-message');
    const input = document.getElementById('prompt-input');
    const okBtn = document.getElementById('btn-prompt-ok');
    const cancelBtn = document.getElementById('btn-prompt-cancel');

    titleEl.textContent = title;
    msgEl.textContent = message;
    msgEl.className = 'muted dialog-desc';
    okBtn.textContent = okText;
    okBtn.className = 'btn ' + okClass;
    input.value = defaultValue;

    const cleanup = () => {
      dlg.classList.add('hidden');
      document.removeEventListener('keydown', onKey);
      okBtn.replaceWith(okBtn.cloneNode(true));
      cancelBtn.replaceWith(cancelBtn.cloneNode(true));
    };

    const submit = () => {
      const val = input.value.trim();
      cleanup();
      resolve(val || null);
    };

    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        cleanup();
        resolve(null);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        submit();
      }
    };

    const newOk = okBtn.cloneNode(true);
    const newCancel = cancelBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOk, okBtn);
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);

    newOk.addEventListener('click', submit);
    newCancel.addEventListener('click', () => { cleanup(); resolve(null); });

    dlg.classList.remove('hidden');
    input.focus();
    input.select();
    document.addEventListener('keydown', onKey);
  });
}

/* ─── Live Log ─── */
const LOG_FILTER_KEY = 'tiktok2mc_log_filter';
const LOG_AUTOSCROLL_KEY = 'tiktok2mc_log_autoscroll';
const LOG_LEVELS = ['all', 'info', 'warning', 'error', 'debug', 'critical'];

class LiveLog {
  constructor() {
    this.view = document.getElementById('log-view');
    this.status = document.getElementById('log-status');
    this.visibleCount = document.getElementById('log-visible-count');
    this.searchInput = document.getElementById('log-search');
    this.entries = [];
    this.maxEntries = 500;
    this.paused = false;
    this.filter = 'all';
    this.searchQuery = '';
    this.levelCounts = { all: 0, info: 0, warning: 0, error: 0, debug: 0, critical: 0 };
    this._sse = null;
    this._reconnectTimer = null;
    this._restorePrefs();
    this._bindFilters();
    this._bindAutoscroll();
    this._startSSE();
    this.render();
  }

  _restorePrefs() {
    try {
      const savedFilter = localStorage.getItem(LOG_FILTER_KEY);
      if (savedFilter && LOG_LEVELS.includes(savedFilter)) this.filter = savedFilter;
    } catch (_) {}
    const autoScroll = document.getElementById('log-autoscroll');
    if (autoScroll) {
      let saved = null;
      try { saved = localStorage.getItem(LOG_AUTOSCROLL_KEY); } catch (_) {}
      if (saved !== null) autoScroll.checked = saved === 'true';
    }
    this._applyFilterButtons();
  }

  _applyFilterButtons() {
    const buttons = document.getElementById('log-filter-buttons');
    if (!buttons) return;
    buttons.querySelectorAll('.log-filter-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-level') === this.filter);
    });
  }

  _bindAutoscroll() {
    const autoScroll = document.getElementById('log-autoscroll');
    if (!autoScroll) return;
    autoScroll.addEventListener('change', () => {
      try { localStorage.setItem(LOG_AUTOSCROLL_KEY, String(autoScroll.checked)); } catch (_) {}
    });
  }

  _normalizeLevel(level) {
    const l = String(level || 'info').toLowerCase();
    if (l === 'warn') return 'warning';
    if (l === 'err') return 'error';
    if (l === 'crit') return 'critical';
    if (['info','warning','error','debug','critical'].includes(l)) return l;
    return 'info';
  }

  _bindFilters() {
    const buttons = document.getElementById('log-filter-buttons');
    if (!buttons) return;
    buttons.addEventListener('click', (e) => {
      if (!e.target.classList.contains('log-filter-btn')) return;
      this.setFilter(e.target.getAttribute('data-level'));
      buttons.querySelectorAll('.log-filter-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
    });
  }

  _startSSE() {
    if (this._sse) { try { this._sse.close(); } catch (_) {} }
    if (this._reconnectTimer) { clearTimeout(this._reconnectTimer); this._reconnectTimer = null; }

    try {
      this._sse = new EventSource(API + '/logs/stream' + (_apiKey ? '?key=' + encodeURIComponent(_apiKey) : ''));
      this._sse.onopen = () => this.setConnected(true);
      this._sse.onmessage = (e) => {
        if (!e.data || e.data.startsWith(':')) return;
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === 'log.unified') {
            const d = msg.data || {};
            this._addFromSSE(d.message || d.raw || '', d.level || 'info', d.name || '');
          }
        } catch (_) {}
      };
      this._sse.onerror = () => {
        this.setConnected(false);
        if (this._sse) { try { this._sse.close(); } catch (_) {} this._sse = null; }
        this._reconnectTimer = setTimeout(() => this._startSSE(), 3000);
      };
    } catch (_) {
      this._reconnectTimer = setTimeout(() => this._startSSE(), 5000);
    }
  }

  _addFromSSE(message, level, source) {
    if (this.paused) return;
    const entry = {
      id: Date.now() + '-' + Math.random().toString(36).slice(2),
      time: new Date().toLocaleTimeString(),
      timestamp: Date.now(),
      message: message,
      level: this._normalizeLevel(level),
      source: source || ''
    };
    this.entries.push(entry);
    if (this.entries.length > this.maxEntries) {
      const removed = this.entries.shift();
      this.levelCounts[removed.level] = Math.max(0, this.levelCounts[removed.level] - 1);
      this.levelCounts.all = Math.max(0, this.levelCounts.all - 1);
    }
    this.levelCounts[entry.level]++;
    this.levelCounts.all++;
    this._updateStats();
    if (this._matches(entry)) {
      const el = this._renderEntry(entry);
      this.view.appendChild(el);
      this._trimVisible();
      this._scrollToBottom();
    }
    this._updateVisibleCount();
  }

  setFilter(level) {
    this.filter = level || 'all';
    try { localStorage.setItem(LOG_FILTER_KEY, this.filter); } catch (_) {}
    this._applyFilterButtons();
    this.render();
  }

  onSearch(query) {
    this.searchQuery = (query || '').toLowerCase().trim();
    this.render();
  }

  togglePause() {
    this.paused = !this.paused;
    const btn = document.getElementById('log-pause-btn');
    if (btn) {
      btn.textContent = this.paused ? I18N.t('common.resume') : I18N.t('common.pause');
      btn.classList.toggle('btn--primary', this.paused);
      btn.classList.toggle('btn--secondary', !this.paused);
    }
    if (this.status) {
      this.status.textContent = this.paused ? I18N.t('log.paused') : I18N.t('log.connected');
    }
  }

  setConnected(connected) {
    if (this.status) {
      this.status.textContent = this.paused
        ? I18N.t('log.paused')
        : (connected ? I18N.t('log.connected') : I18N.t('log.streamDisconnected'));
    }
  }

  clear() {
    this.entries = [];
    this.levelCounts = { all: 0, info: 0, warning: 0, error: 0, debug: 0, critical: 0 };
    this.render();
  }

  export() {
    const lines = this.entries.map(e => `[${e.time}] [${e.level.toUpperCase()}] ${e.source ? '(' + e.source + ') ' : ''}${e.message}`);
    const content = lines.join('\n');
    const filename = `tiktok2mc-log-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;

    if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.download_file) {
      pywebview.api.download_file(content, filename).then(path => {
        if (path && !path.startsWith('error:')) {
          showToast(I18N.t('log.exportedPath', { path }), 'success');
        } else {
          showToast(I18N.t('log.exportFailed'), 'error');
        }
      });
      return;
    }

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(I18N.t('log.exported'), 'success');
  }

  add(message, level = 'info', source = '') {
    this._addFromSSE(message, level, source);
  }

  _matches(entry) {
    if (this.filter !== 'all' && entry.level !== this.filter) return false;
    if (this.searchQuery) {
      const text = (entry.message + ' ' + entry.source + ' ' + entry.level).toLowerCase();
      return text.includes(this.searchQuery);
    }
    return true;
  }

  _renderEntry(entry) {
    const line = document.createElement('div');
    line.className = 'log-line log-' + entry.level;
    line.setAttribute('data-id', entry.id);
    line.setAttribute('data-level', entry.level);
    line.innerHTML = `<span class="log-time">${escapeHtml(entry.time)}</span><span class="log-badge log-badge-${entry.level}">${entry.level.toUpperCase()}</span>${entry.source ? '<span class="log-source">' + escapeHtml(entry.source) + '</span>' : ''}<span class="log-message">${escapeHtml(entry.message)}</span>`;
    return line;
  }

  _trimVisible() {
    while (this.view.children.length > this.maxEntries) {
      this.view.removeChild(this.view.firstChild);
    }
  }

  _scrollToBottom() {
    const autoScroll = document.getElementById('log-autoscroll');
    if (!autoScroll || autoScroll.checked) {
      this.view.scrollTop = this.view.scrollHeight;
    }
  }

  _updateStats() {
    for (const level of Object.keys(this.levelCounts)) {
      const el = document.getElementById('stat-' + level);
      if (el) el.textContent = this.levelCounts[level];
    }
  }

  _updateVisibleCount() {
    if (this.visibleCount) {
      const visible = Array.from(this.view.children).filter(c => !c.classList.contains('hidden')).length;
      this.visibleCount.textContent = visible + ' / ' + this.entries.length + ' shown';
    }
  }

  render() {
    if (!this.view) return;
    this.view.innerHTML = '';
    const fragment = document.createDocumentFragment();
    let visible = 0;
    for (const entry of this.entries) {
      if (this._matches(entry)) {
        fragment.appendChild(this._renderEntry(entry));
        visible++;
      }
    }
    this.view.appendChild(fragment);
    this._updateStats();
    this._updateVisibleCount();
    this._scrollToBottom();
  }
}

function log(msg, level = 'info') {
  liveLog.add(msg, level);
}

const liveLog = new LiveLog();

/* ─── Crash Reports ─── */
class CrashReports {
  constructor() {
    this.container = document.getElementById('crash-reports-list');
    this.detailView = document.getElementById('crash-report-detail');
    this.detailContent = document.getElementById('crash-report-detail-content');
    this.emptyState = document.getElementById('crash-reports-empty');
    this.reports = [];
  }

  async load() {
    try {
      const data = await fetchJSON('/logs/crash-reports');
      this.reports = data.reports || [];
      this.renderList();
    } catch (e) {
      if (this.container) this.container.innerHTML = '<p class="muted">' + I18N.t('log.crashLoadFailed') + '</p>';
    }
  }

  renderList() {
    if (!this.container) return;
    if (!this.reports.length) {
      this.container.innerHTML = '';
      if (this.emptyState) this.emptyState.classList.remove('hidden');
      return;
    }
    if (this.emptyState) this.emptyState.classList.add('hidden');
    this.container.innerHTML = this.reports.map(r => `
      <div class="crash-report-item" onclick="crashReports.open('${escapeHtml(r.filename)}')">
        <div class="crash-report-meta">
          <span class="crash-report-time">${escapeHtml(r.timestamp || I18N.t('common.unknown'))}</span>
          <span class="crash-report-module">${escapeHtml(r.module || 'unknown')}</span>
        </div>
        <div class="crash-report-type">${escapeHtml(r.exception_type || 'Exception')}</div>
      </div>
    `).join('');
  }

  async open(filename) {
    if (!this.detailView || !this.detailContent) return;
    try {
      const data = await fetchJSON('/logs/crash-reports/' + encodeURIComponent(filename));
      this.detailContent.innerHTML = this._renderDetail(data);
      this.detailView.classList.remove('hidden');
    } catch (e) {
      showToast(I18N.t('log.crashOpenFailed'), 'error');
    }
  }

  close() {
    if (this.detailView) this.detailView.classList.add('hidden');
  }

  _renderDetail(data) {
    const ts = escapeHtml(data.timestamp || I18N.t('common.unknown'));
    const mod = escapeHtml(data.module || 'unknown');
    const excType = escapeHtml(data.exception_type || 'Exception');
    const excMsg = escapeHtml(data.exception_message || '');
    const pyVer = escapeHtml((data.python_version || '').split('\n')[0]);
    const plat = escapeHtml(data.platform || '');
    const stack = escapeHtml(data.stack_trace || 'No stack trace available.');
    const logs = (data.recent_logs || []).map(l => escapeHtml(l)).join('\n');

    return `
      <div class="crash-detail-header">
        <div>
          <h4 class="crash-detail-title">${excType}</h4>
          <div class="crash-detail-subtitle">${mod} &middot; ${ts}</div>
        </div>
        <button class="btn btn--sm btn--secondary" onclick="crashReports.close()">Close</button>
      </div>
      <div class="crash-detail-section">
        <div class="crash-detail-label">Message</div>
        <div class="crash-detail-box">${excMsg || '<span class="muted">No message</span>'}</div>
      </div>
      <div class="crash-detail-section">
        <div class="crash-detail-label">Environment</div>
        <div class="crash-detail-box crash-detail-env">
          <div><strong>Python:</strong> ${pyVer}</div>
          <div><strong>Platform:</strong> ${plat}</div>
        </div>
      </div>
      <div class="crash-detail-section">
        <div class="crash-detail-label">Stack Trace</div>
        <pre class="crash-detail-box crash-detail-pre">${stack}</pre>
      </div>
      ${logs ? `<div class="crash-detail-section">
        <div class="crash-detail-label">Recent Logs</div>
        <pre class="crash-detail-box crash-detail-pre">${logs}</pre>
      </div>` : ''}
    `;
  }
}

const crashReports = new CrashReports();

function showToast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  t.setAttribute('role', type === 'error' || type === 'warning' ? 'alert' : 'status');
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

/* ─── Dashboard ─── */
async function loadHealth() {
  try {
    const data = await fetchJSON('/health');
    const pill = document.getElementById('status-pill');
    pill.textContent = data.tool_version || ('API v' + data.api_version);
    pill.className = 'online';
  } catch (e) {
    const pill = document.getElementById('status-pill');
    pill.textContent = I18N.t('common.offline');
    pill.className = 'offline';
    log('API unreachable: ' + e.message, 'err');
  }
}

function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return h + 'h ' + m + 'm ' + s + 's';
  if (m > 0) return m + 'm ' + s + 's';
  return s + 's';
}

let _uptimeData = { baseSeconds: 0, lastFetch: 0 };
let _serverUptimeData = {};

function _updateUptimeDisplay() {
  const el = document.getElementById('uptime-value');
  if (!el) return;
  const now = Date.now();
  const elapsed = (now - _uptimeData.lastFetch) / 1000;
  const total = _uptimeData.baseSeconds + elapsed;
  el.textContent = formatUptime(total);
}

function _updateServerUptimeDisplay() {
  const now = Date.now();
  for (const instId in _serverUptimeData) {
    const d = _serverUptimeData[instId];
    const card = document.querySelector('[data-instance-id="' + instId + '"]');
    if (!card) continue;
    const stateText = card.querySelector('.server-state-text');
    if (stateText && stateText.textContent.toLowerCase() !== 'running') {
      delete _serverUptimeData[instId];
      const uptimeEl = card.querySelector('.server-uptime');
      if (uptimeEl) uptimeEl.textContent = '—';
      continue;
    }
    const elapsed = (now - d.lastFetch) / 1000;
    const total = d.baseSeconds + elapsed;
    const uptimeEl = card.querySelector('.server-uptime');
    if (uptimeEl) uptimeEl.textContent = formatUptime(total);
  }
}


async function loadStatus() {
  try {
    const data = await fetchJSON('/status');
    const el = document.getElementById('system-info');
    if (!el) return;
    _uptimeData.baseSeconds = data.uptime_seconds || 0;
    _uptimeData.lastFetch = Date.now();
    el.innerHTML =
      '<div class="status-grid">' +
        '<div class="status-card">' +
          '<span class="status-card__label">' + I18N.t('status.server') + '</span>' +
          '<span class="status-card__value">' + escapeHtml(data.server) + '</span>' +
        '</div>' +
        '<div class="status-card">' +
          '<span class="status-card__label">' + I18N.t('status.pluginsActive') + '</span>' +
          '<span class="status-card__value">' + data.plugins_active + ' / ' + data.plugins_total + '</span>' +
        '</div>' +
        '<div class="status-card">' +
          '<span class="status-card__label">' + I18N.t('status.configuration') + '</span>' +
          '<span class="status-card__value' + (data.config_loaded ? ' success' : ' danger') + '">' + (data.config_loaded ? I18N.t('status.loaded') : I18N.t('status.notLoaded')) + '</span>' +
        '</div>' +
        '<div class="status-card">' +
          '<span class="status-card__label">' + I18N.t('status.uptime') + '</span>' +
          '<span class="status-card__value" id="uptime-value">' + formatUptime(data.uptime_seconds) + '</span>' +
        '</div>' +
        '<div class="status-card">' +
          '<span class="status-card__label">' + I18N.t('status.tiktokStream') + '</span>' +
          '<span class="status-card__value" id="tiktok-status-value">' + I18N.t('status.checking') + '</span>' +
        '</div>' +
      '</div>';

    // Render Live Statistics
    renderLiveStats(data);

    // Explicit live-state from the API (reported by the bridge). This is
    // authoritative and survives quiet streams / test triggers.
    if (typeof data.tiktok_live === 'boolean') {
      _tiktokLiveState = data.tiktok_live;
    }
    _updateTiktokStatusDisplay();
  } catch (e) {
    const el = document.getElementById('system-info');
    if (el) el.innerHTML = '<span class="log-err">' + I18N.t('status.failedLoad', { msg: escapeHtml(e.message) }) + '</span>';
  }
}

function renderLiveStats(data) {
  const grid = document.getElementById('live-stats-grid');
  if (!grid) return;

  const stats = [];

  // RCON Queue Size
  if (data.rcon_queue_size !== undefined && data.rcon_queue_size !== null) {
    const cls = data.rcon_queue_size > 100 ? 'danger' : data.rcon_queue_size > 50 ? 'warning' : 'success';
    stats.push({
      label: I18N.t('status.rconQueue'),
      value: data.rcon_queue_size,
      class: cls,
    });
  }

  // Trigger Queue Size
  if (data.trigger_queue_size !== undefined && data.trigger_queue_size !== null) {
    const cls = data.trigger_queue_size > 100 ? 'danger' : data.trigger_queue_size > 50 ? 'warning' : 'success';
    stats.push({
      label: I18N.t('status.triggerQueue'),
      value: data.trigger_queue_size,
      class: cls,
    });
  }

  // Events per Minute
  if (data.events_per_minute !== undefined && data.events_per_minute !== null) {
    stats.push({
      label: I18N.t('status.eventsPerMinute'),
      value: data.events_per_minute,
      class: 'info',
    });
  }

  // Gift Value Today
  if (data.gift_value_usd_today !== undefined && data.gift_value_usd_today !== null) {
    stats.push({
      label: I18N.t('status.giftValueToday'),
      value: '$' + data.gift_value_usd_today.toFixed(2),
      class: 'success',
    });
  }

  if (stats.length === 0) {
    grid.innerHTML = '<div class="text-muted" style="grid-column: 1 / -1; text-align: center; padding: var(--space-4);">' + I18N.t('status.noLiveData') + '</div>';
    return;
  }

  grid.innerHTML = stats.map(s =>
    '<div class="status-card">' +
      '<span class="status-card__label">' + escapeHtml(s.label) + '</span>' +
      '<span class="status-card__value ' + s.class + '">' + escapeHtml(String(s.value)) + '</span>' +
    '</div>'
  ).join('');
}

function _updateTiktokStatusDisplay() {
  const el = document.getElementById('tiktok-status-value');
  const pill = document.getElementById('tiktok-status-pill');
  if (!el || !pill) return;
  const tiktok = currentConfig.tiktok || {};
  const hasUser = tiktok.user && tiktok.user !== 'your_tiktok_username';
  if (!hasUser) {
    el.textContent = I18N.t('status.notConfigured');
    el.className = 'status-card__value danger';
    pill.textContent = I18N.t('status.noUser');
    pill.className = 'tiktok-status offline';
    return;
  }
  const now = Date.now();
  const isLive = _tiktokLiveState === true
    // Fallback only while the state is still unknown (e.g. the API was
    // restarted): treat recent genuine events as evidence of an active
    // connection. Never active when an explicit "not live" was received.
    || (_tiktokLiveState === null && _lastTiktokEventTime && (now - _lastTiktokEventTime < 60000));
  if (isLive) {
    el.textContent = I18N.t('status.connected');
    el.className = 'status-card__value success';
    pill.textContent = I18N.t('status.live');
    pill.className = 'tiktok-status online';
  } else if (_tiktokLiveState === false) {
    el.textContent = I18N.t('status.configured');
    el.className = 'status-card__value';
    pill.textContent = I18N.t('status.notLive');
    pill.className = 'tiktok-status offline';
  } else {
    el.textContent = I18N.t('status.checking');
    el.className = 'status-card__value';
    pill.textContent = I18N.t('status.checkingPill');
    pill.className = 'tiktok-status connecting';
  }
  eventTester._updateTiktokStateUI();
}

function getPluginStatus(p) {
  if (p.error) return { label: I18N.t('common.error'), cls: 'status-error' };
  if (!p.enabled) return { label: I18N.t('plugins.disabled'), cls: 'status-disabled' };
  return { label: I18N.t('plugins.enabled'), cls: 'status-enabled' };
}

async function loadPlugins() {
  try {
    const data = await fetchJSON('/plugins');
    currentPlugins = data.plugins || [];
    renderPluginManager();
    renderOverlayUrls();
    renderPluginPagesNav();
    refreshHookWidgets();
  } catch (e) {
    log('Plugins load failed: ' + e.message, 'err');
  }
}

/* ─── Hook Dashboard Widgets (hook "ui" permission) ─── */

const HOOK_WIDGET_VIEW = 'hookwidgets';
const _HOOK_WIDGET_ICON = '<svg class="nav-icon" viewBox="0 0 24 24" width="20" height="20"><path d="M21 3H3a1 1 0 00-1 1v16a1 1 0 001 1h18a1 1 0 001-1V4a1 1 0 00-1-1zm-1 16H4V9h16v10zM4 7V5h16v2H4z" fill="currentColor"/></svg>';

async function refreshHookWidgets() {
  const nav = document.querySelector('.sidebar-nav');
  const main = document.getElementById('dashboard');
  if (!nav || !main) return;

  // Remove previous render
  document.querySelectorAll('[data-hook-widgets]').forEach(el => el.remove());

  let widgets;
  try {
    const data = await fetchJSON('/hooks/widgets');
    widgets = data.widgets || [];
  } catch (e) {
    return; // endpoint unavailable (older backend) — skip silently
  }
  if (!widgets.length) return;

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'nav-item';
  btn.setAttribute('data-view', HOOK_WIDGET_VIEW);
  btn.setAttribute('data-hook-widgets', '1');
  btn.title = I18N.t('hooks.widgetsTitle') || 'Hook Widgets';
  btn.innerHTML = _HOOK_WIDGET_ICON +
    '<span class="nav-label">' + escapeHtml(I18N.t('hooks.widgetsTitle') || 'Hook Widgets') + '</span>';
  btn.onclick = () => openHookWidgets();
  nav.appendChild(btn);

  let cards = '';
  for (const w of widgets) {
    const url = API + '/hooks/' + encodeURIComponent(w.name) + '/widget.html';
    cards +=
      '<div class="card hook-widget-card" data-hook-widgets="1">' +
      '<div class="card-header"><strong>' + escapeHtml(w.title) + '</strong>' +
      '<span class="muted"> (' + escapeHtml(w.name) + ')</span></div>' +
      '<iframe class="plugin-page-frame" title="' + escapeHtml(w.title) + '" loading="lazy" data-src="' + url + '" style="width:100%;height:220px;border:none"></iframe>' +
      '</div>';
  }
  const view = document.createElement('div');
  view.className = 'view';
  view.id = 'view-' + HOOK_WIDGET_VIEW;
  view.setAttribute('data-hook-widgets', '1');
  view.innerHTML =
    '<div class="view-header"><h2>' + escapeHtml(I18N.t('hooks.widgetsTitle') || 'Hook Widgets') + '</h2></div>' +
    cards;
  main.appendChild(view);
}

function openHookWidgets() {
  const view = document.getElementById('view-' + HOOK_WIDGET_VIEW);
  if (!view) return;
  // Load iframes on first open
  view.querySelectorAll('iframe[data-src]').forEach(f => {
    if (!f.src && f.dataset.src) f.src = f.dataset.src;
  });
  switchView(HOOK_WIDGET_VIEW);
}

/* ─── Server Manager ─── */
let _serverLifecycleInterval = null;

function startServerLifecyclePolling() {
  stopServerLifecyclePolling();
  updateServerLifecycleUI();
  _serverLifecycleInterval = setInterval(updateServerLifecycleUI, 5000);
}

function stopServerLifecyclePolling() {
  if (_serverLifecycleInterval) {
    clearInterval(_serverLifecycleInterval);
    _serverLifecycleInterval = null;
  }
}

async function loadServerManager() {
  try {
    const data = await fetchJSON('/servers');
    _serverManagerCache = data;
    renderServerManager();
    refreshConsoleInstanceSelector();
    loadJavaStatus();
  } catch (e) {
    log('Server Manager load failed: ' + e.message, 'err');
    ['server-instances', 'server-versions-list'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '<p class="text-muted">' + I18N.t('servers.failedLoad') + '</p>';
    });
  }
}

/* ─── Java runtime status banner ─── */

async function loadJavaStatus() {
  try {
    const data = await fetchJSON('/server/java/status');
    renderJavaStatusBanner(data);
  } catch (e) {
    const el = document.getElementById('java-status-banner');
    if (el) {
      el.classList.remove('hidden');
      el.innerHTML = I18N.t('servers.javaCheckFailed', { msg: escapeHtml(e.message) });
    }
  }
}

function renderJavaStatusBanner(data) {
  const el = document.getElementById('java-status-banner');
  if (!el) return;
  if (data && data.ok) {
    el.classList.add('hidden');
    el.innerHTML = '';
    return;
  }
  const reason = (data && data.reason) || 'No Java runtime was found on this system.';
  const minVer = (data && data.minJavaVersion) || 21;
  const hints = (data && data.hints) || [];
  const installMsg = data && data.install && data.install.message ? '<br><em>' + escapeHtml(data.install.message) + '</em>' : '';
  const hintBlock = hints.length
    ? '<br><code style="white-space:pre-line;">' + hints.map(escapeHtml).join('\n') + '</code>'
    : '';
  const installBtn = (data && data.autoInstallable)
    ? '<button class="btn btn--sm btn--primary" id="java-install-btn" onclick="installJava()">Install Java</button>'
    : '';
  el.classList.remove('hidden');
  el.innerHTML =
    '<div class="java-banner">' +
      '<div class="server-card-warning">' +
        '<strong>Java runtime missing</strong> — ' + escapeHtml(reason) +
        ' Minecraft needs Java ' + minVer + '+ to run the server.' +
        installMsg + hintBlock +
      '</div>' +
      (installBtn ? '<div class="java-banner-actions">' + installBtn + '</div>' : '') +
    '</div>';
}

async function installJava() {
  const btn = document.getElementById('java-install-btn');
  if (btn) { btn.disabled = true; btn.textContent = I18N.t('servers.javaInstallingTitle') + '…'; }
  
  // Create a progress overlay
  const overlay = document.createElement('div');
  overlay.className = 'java-install-overlay';
  overlay.innerHTML = `
    <div class="java-install-progress">
      <h3>${escapeHtml(I18N.t('servers.javaInstallingTitle'))}</h3>
      <div class="progress-bar"><div class="progress-fill" id="java-progress-fill" style="width: 0%"></div></div>
      <div class="progress-text" id="java-progress-text">${escapeHtml(I18N.t('servers.javaStarting'))}</div>
      <button class="btn btn--secondary btn--sm" id="java-cancel-btn">${escapeHtml(I18N.t('common.cancel'))}</button>
    </div>
  `;
  document.body.appendChild(overlay);
  
  const progressFill = document.getElementById('java-progress-fill');
  const progressText = document.getElementById('java-progress-text');
  const cancelBtn = document.getElementById('java-cancel-btn');
  
  let cancelled = false;
  cancelBtn.addEventListener('click', () => {
    cancelled = true;
    progressText.textContent = I18N.t('servers.javaCancelling');
    cancelBtn.disabled = true;
  });
  
  let installId = null;
  let lastMsg = '';
  const startTime = Date.now();
  const MAX_TIMEOUT = 5 * 60 * 1000; // 5 minutes
  
  try {
    const res = await postJSON('/server/java/install');
    if (res.status === 'in_progress') {
      showToast(res.message, 'info');
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('servers.installJava'); }
      overlay.remove();
      return;
    }
    if (res.status === 'already_installed') {
      showToast(res.message, 'info');
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('servers.installJava'); }
      overlay.remove();
      loadJavaStatus();
      loadServerManager();
      return;
    }
    installId = res.install_id;
    showToast(res.message || I18N.t('servers.javaStarted'), 'info');
  } catch (e) {
    showToast(I18N.t('servers.javaInstallFailed', { msg: e.message }), 'error');
    if (btn) { btn.disabled = false; btn.textContent = I18N.t('servers.installJava'); }
    overlay.remove();
    return;
  }
  
  const iv = setInterval(async () => {
    if (cancelled) {
      clearInterval(iv);
      overlay.remove();
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('servers.installJava'); }
      showToast(I18N.t('servers.javaCancelled'), 'info');
      return;
    }
    
    // Check timeout
    if (Date.now() - startTime > MAX_TIMEOUT) {
      clearInterval(iv);
      overlay.remove();
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('servers.installJava'); }
      showToast(I18N.t('servers.javaTimedOut'), 'error');
      return;
    }
    
    try {
      const data = await fetchJSON('/server/java/status?install_id=' + encodeURIComponent(installId));
      const inst = data && data.install;
      if (!inst) { 
        clearInterval(iv); 
        overlay.remove();
        if (btn) { btn.disabled = false; btn.textContent = I18N.t('servers.installJava'); } 
        return; 
      }
      
      // Update progress UI
      if (inst.message && inst.message !== lastMsg) {
        lastMsg = inst.message;
        progressText.textContent = inst.message;
        showToast(inst.message, 'info');
      }
      
      // Animate progress bar (indeterminate while installing)
      if (inst.installing && !inst.done) {
        const elapsed = Math.min((Date.now() - startTime) / MAX_TIMEOUT, 0.9);
        progressFill.style.width = (elapsed * 100) + '%';
      }
      
      if (inst.done) {
        clearInterval(iv);
        overlay.remove();
        if (inst.ok) {
          progressFill.style.width = '100%';
          progressText.textContent = I18N.t('servers.javaComplete');
          showToast(I18N.t('servers.javaNowAvailable') + (data.version ? ' (' + data.version + ')' : '') + '.', 'success');
        } else {
          showToast(I18N.t('servers.javaFailedDetails'), 'error');
        }
        if (btn) { btn.disabled = false; btn.textContent = I18N.t('servers.installJava'); }
        loadJavaStatus();
        loadServerManager();
      }
    } catch (e) {
      log('Java install status poll failed: ' + e.message, 'err');
    }
  }, 2000);
}

function renderServerManager() {
  const instancesEl = document.getElementById('server-instances');
  const versionsList = document.getElementById('server-versions-list');
  if (!instancesEl || !versionsList) return;

  if (!_serverManagerCache) {
    instancesEl.innerHTML = '<div class="text-muted server-loading">' + I18N.t('servers.loadingInstances') + '</div>';
    versionsList.innerHTML = '<p class="text-muted">' + I18N.t('servers.loadingVersions') + '</p>';
    return;
  }

  const instances = _serverManagerCache.instances || [];
  if (!instances.length) {
    instancesEl.innerHTML = '<div class="text-muted server-loading">' + I18N.t('servers.noInstances') + '</div>';
  } else {
    instancesEl.innerHTML = instances.map(inst => renderServerCard(inst)).join('');
  }

  renderVersionLibrary(versionsList);
  loadMcPlugins();
}

function renderServerCard(inst) {
  const notInstalled = !inst.hasJar;
  const state = notInstalled ? 'not-installed' : (inst.status || 'stopped');
  const stateLabel = notInstalled ? I18N.t('servers.notInstalled') : state.charAt(0).toUpperCase() + state.slice(1);
  const dotClass = 'server-status-dot--' + state;
  const instId = escapeHtml(inst.id);
  const versionDisplay = notInstalled ? I18N.t('servers.notInstalled') : escapeHtml(inst.version);
  const versionBadge = notInstalled
    ? '<span class="server-status-badge server-status-badge--missing">' + I18N.t('servers.missing') + '</span>'
    : `<span class="server-status-badge ${_versionBadgeClass(inst.version)}">${_versionBadgeLabel(inst.version)}</span>`;
  const notInstalledBanner = notInstalled
    ? '<div class="server-card-warning">' + I18N.t('servers.jarMissing') + '</div>'
    : '';
  return `<div class="server-card" data-instance-id="${instId}" ${notInstalled ? 'data-instance-not-installed="1"' : ''}>
    <div class="server-card-top">
      <div class="server-card-title">
        <span class="server-status-dot ${dotClass}"></span>
        <strong class="server-card-name">${escapeHtml(inst.name)}</strong>
        <span class="server-card-version-badge">
          ${versionDisplay}
          ${versionBadge}
        </span>
      </div>
      <div class="server-card-actions-top">
        <button class="btn btn--sm btn--success server-action-btn" onclick="serverCardAction('${instId}', 'start')" title="Start" ${state === 'running' || state === 'starting' || state === 'stopping' || notInstalled ? 'disabled' : ''}>
          <svg width="14" height="14" viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21" fill="currentColor"/></svg>
        </button>
        <button class="btn btn--sm btn--danger server-action-btn" onclick="serverCardAction('${instId}', 'stop')" title="Stop" ${state !== 'running' ? 'disabled' : ''}>
          <svg width="14" height="14" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" fill="currentColor"/></svg>
        </button>
        <button class="btn btn--sm btn--secondary server-action-btn" onclick="serverCardAction('${instId}', 'restart')" title="Restart" ${state !== 'running' ? 'disabled' : ''}>
          <svg width="14" height="14" viewBox="0 0 24 24"><path d="M17.65 6.35A7.96 7.96 0 0 0 12 4C7.58 4 4.01 7.58 4.01 12S7.58 20 12 20c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" fill="currentColor"/></svg>
        </button>
      </div>
    </div>
    ${notInstalledBanner}
    <div class="server-card-body">
      <div class="server-card-meta">
        <div class="server-card-meta-item">
          <span class="server-card-label">Status</span>
          <span class="server-card-value server-state-text server-state-text--${state}">${stateLabel}</span>
        </div>
        <div class="server-card-meta-item">
          <span class="server-card-label">Uptime</span>
          <span class="server-card-value server-uptime" data-instance="${instId}">—</span>
        </div>
        <div class="server-card-meta-item">
          <span class="server-card-label">Port</span>
          <span class="server-card-value code">${inst.port || '25565'}</span>
        </div>
        <div class="server-card-meta-item">
          <span class="server-card-label">Path</span>
          <span class="server-card-value code">${escapeHtml(inst.path || '—')}</span>
        </div>
      </div>
    </div>
    <div class="server-card-footer">
      <label class="server-auto-start-toggle" title="${I18N.t('servers.autoStartTooltip')}">
        <input type="checkbox" ${inst.auto_start ? 'checked' : ''} onchange="toggleAutoStart('${instId}', this.checked)">
        <span>${I18N.t('servers.autoStart')}</span>
      </label>
      <button class="btn btn--sm btn--secondary" onclick="openServerSwitchModal()">Switch Version</button>
      <button class="btn btn--sm btn--secondary" onclick="openServerFolder('${instId}')">Open Folder</button>
      ${instId !== 'default' ? '<button class="btn btn--sm btn--danger-ghost" onclick="deleteServerInstance(\'' + escapeHtml(instId) + '\')" title="Delete server">Delete</button>' : ''}
    </div>
  </div>`;
}

function renderVersionLibrary(versionsList) {
  const versions = _serverManagerCache.installed || [];
  const countEl = document.getElementById('version-count');
  if (countEl) countEl.textContent = versions.length + ' version' + (versions.length !== 1 ? 's' : '');

  if (!versions.length) {
    versionsList.innerHTML = '<p class="text-muted">' + I18N.t('servers.noVersions') + '</p>';
    return;
  }

  let html = '<div class="version-cards">';
  for (const v of versions) {
    const badgeClass = 'server-status-badge--' + (v.type === 'safe' ? 'safe' : v.type === 'custom' ? 'custom' : 'unsafe');
    const badgeLabel = v.type.toUpperCase();
    const sizeStr = v.size ? ' (' + (v.size / 1024 / 1024).toFixed(1) + ' MB)' : '';
    html += '<div class="version-card">' +
      '<div class="version-card-info">' +
        '<div class="version-card-version">' +
          '<strong>' + escapeHtml(v.version) + '</strong>' +
          '<span class="server-status-badge ' + badgeClass + '">' + badgeLabel + '</span>' +
        '</div>' +
        '<div class="version-card-path"><code>' + escapeHtml(v.path) + '</code> ' + sizeStr + '</div>' +
      '</div>' +
      '<div class="version-card-actions">' +
        '<button class="btn btn--sm btn--danger-ghost" onclick="serverManagerPromptRemove(\'' + escapeHtml(v.version) + '\')" title="Remove version">Remove</button>' +
      '</div>' +
    '</div>';
  }
  html += '</div>';
  versionsList.innerHTML = html;
}

function _versionBadgeClass(version) {
  if (!_serverManagerCache) return 'server-status-badge--unsafe';
  const found = (_serverManagerCache.installed || []).find(v => v.version === version);
  if (!found) {
    if ((_serverManagerCache.safe_versions || []).includes(version)) return 'server-status-badge--safe';
    return 'server-status-badge--unsafe';
  }
  return found.type === 'safe' ? 'server-status-badge--safe'
       : found.type === 'custom' ? 'server-status-badge--custom'
       : 'server-status-badge--unsafe';
}

function _versionBadgeLabel(version) {
  if (!_serverManagerCache) return I18N.t('servers.unsafe');
  const found = (_serverManagerCache.installed || []).find(v => v.version === version);
  if (!found) {
    if ((_serverManagerCache.safe_versions || []).includes(version)) return I18N.t('servers.safe');
    return I18N.t('servers.unsafe');
  }
  return found.type.toUpperCase();
}

async function serverManagerPromptSwitch(version) {
  if (_serverManagerCache?.current_version === version) {
    showToast(I18N.t('servers.versionAlreadyActive', { version }), 'info');
    return;
  }
  const installed = _serverManagerCache?.installed || [];
  const found = installed.find(v => v.version === version);
  const isSafe = found ? found.type === 'safe' : (_serverManagerCache?.safe_versions || []).includes(version);
  if (!isSafe) {
    const confirmed = await showConfirmDialog(
      I18N.t('servers.switchUntestedTitle'),
      I18N.t('servers.switchUntested', { version }),
      I18N.t('servers.switchAnyway'),
      'btn-danger',
      'text-danger'
    );
    if (!confirmed) return;
  } else {
    const confirmed = await showConfirmDialog(
      I18N.t('servers.switchTitle'),
      I18N.t('servers.switchConfirm', { version }),
      I18N.t('common.switch'),
      'btn-primary'
    );
    if (!confirmed) return;
  }
  try {
    closeServerSwitchModal();
    const res = await postJSON('/servers/switch', { version });
    showToast(res.message || I18N.t('servers.switched', { version }), 'success');
    await loadServerManager();
  } catch (e) {
    showToast(I18N.t('servers.switchFailed', { msg: e.message }), 'error');
  }
}

async function serverManagerPromptRemove(version) {
  const confirmed = await showConfirmDialog(
    I18N.t('servers.removeTitle'),
    I18N.t('servers.removeConfirm', { version }),
    I18N.t('servers.removeVersion'),
    'btn-danger',
    'text-danger'
  );
  if (!confirmed) return;
  try {
    const res = await fetch(API + '/servers/' + encodeURIComponent(version), { method: 'DELETE', headers: _withApiKey({}) });
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    const data = await res.json();
    showToast(data.message || I18N.t('servers.removed', { version }), 'success');
    await loadServerManager();
  } catch (e) {
    showToast(I18N.t('servers.removeFailed', { msg: e.message }), 'error');
  }
}

/* ─── Server Lifecycle UI Updates ─── */

async function updateServerLifecycleUI() {
  try {
    const cards = document.querySelectorAll('[data-instance-id]');
    for (const card of cards) {
      const instId = card.getAttribute('data-instance-id');
      const cardNotInstalled = card.getAttribute('data-instance-not-installed') === '1';
      let data;
      try {
        data = await fetchJSON('/server/' + instId + '/status');
      } catch (e) {
        continue;
      }
      const state = data.state || 'unknown';
      const uptime = data.uptime;

      const dot = card.querySelector('.server-status-dot');
      if (dot && !cardNotInstalled) dot.className = 'server-status-dot server-status-dot--' + state;

      const stateText = card.querySelector('.server-state-text');
      if (stateText && !cardNotInstalled) {
        stateText.textContent = state.charAt(0).toUpperCase() + state.slice(1);
        stateText.className = 'server-card-value server-state-text server-state-text--' + state;
      }

      const uptimeEl = card.querySelector('.server-uptime');
      if (uptimeEl && !cardNotInstalled) {
        if (uptime !== null && uptime !== undefined) {
          _serverUptimeData[instId] = { baseSeconds: uptime, lastFetch: Date.now() };
          uptimeEl.textContent = formatUptime(uptime);
        } else {
          delete _serverUptimeData[instId];
          uptimeEl.textContent = '—';
        }
      }

      const isTransitional = state === 'starting' || state === 'stopping';
      const actionDisabled = isTransitional || _serverActionInProgress;
      const startBtn = card.querySelector('.btn--success');
      const stopBtn = card.querySelector('.btn--danger');
      const restartBtn = card.querySelectorAll('.btn--secondary')[0];
      if (startBtn) startBtn.disabled = state === 'running' || actionDisabled || cardNotInstalled;
      if (stopBtn) stopBtn.disabled = state !== 'running' || actionDisabled;
      if (restartBtn) restartBtn.disabled = state !== 'running' || actionDisabled;
    }
    refreshConsoleInstanceSelector();
  } catch (e) {
    log('Server status poll failed: ' + e.message, 'err');
  }
}

async function toggleAutoStart(instanceId, enabled) {
  try {
    await putJSON('/servers/instances/' + encodeURIComponent(instanceId), { auto_start: enabled });
    showToast(I18N.t(enabled ? 'servers.autoStartEnabled' : 'servers.autoStartDisabled', { name: instanceId }), 'success');
  } catch (e) {
    showToast(I18N.t('servers.actionFailed', { msg: e.message }), 'error');
    await loadServerManager();
  }
}

async function serverCardAction(instanceId, action) {
  if (_serverActionInProgress) return;
  if (action === 'restart') {
    const confirmed = await showConfirmDialog(
      I18N.t('servers.restartTitle', { instance: instanceId }),
      I18N.t('servers.restartConfirm'),
      I18N.t('common.restart'),
      'btn-danger',
      'text-danger'
    );
    if (!confirmed) return;
  }
  _serverActionInProgress = true;
  document.querySelectorAll('.server-card-actions-top .server-action-btn').forEach(btn => { btn.disabled = true; });
  try {
    const endpoint = '/server/' + instanceId + '/' + action;
    const res = await postJSON(endpoint);
    showToast(res.message || I18N.t('servers.actionInProgress', { action }), 'info');
    loadServerManager();
  } catch (e) {
    showToast(I18N.t('servers.actionFailed', { action, msg: e.message }), 'error');
  } finally {
    _serverActionInProgress = false;
    updateServerLifecycleUI();
  }
}

/* ─── Server Manager: Instance Actions ─── */

async function openServerFolder(instanceId) {
  try {
    const res = await fetch(API + '/servers/instances/' + encodeURIComponent(instanceId) + '/open', { method: 'POST', headers: _withApiKey({}) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || I18N.t('servers.openFolderFailedTitle'));
    if (!data.opened) showToast(I18N.t('servers.folderPath', { path: data.path }), 'info');
  } catch (e) {
    showToast(I18N.t('servers.openFolderFailed', { msg: e.message }), 'error');
  }
}

async function deleteServerInstance(instanceId) {
  const inst = (_serverManagerCache?.instances || []).find(i => i.id === instanceId);
  const name = inst ? inst.name : instanceId;
  const confirmed = await showConfirmDialog(
    I18N.t('servers.deleteTitle'),
    I18N.t('servers.deleteConfirm', { name }),
    I18N.t('common.delete'), 'btn-danger', 'text-danger');
  if (!confirmed) return;
  try {
    const res = await fetch(API + '/servers/instances/' + encodeURIComponent(instanceId), { method: 'DELETE', headers: _withApiKey({}) });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || I18N.t('servers.deleteFailedTitle'));
    }
    showToast(I18N.t('servers.deleted', { name }), 'success');
    await loadServerManager();
  } catch (e) {
    showToast(I18N.t('servers.deleteFailed', { msg: e.message }), 'error');
  }
}

/* ─── Server Manager: Minecraft Plugins ─── */

let _mcPluginsCache = null;

function _mcPluginsInstanceId() {
  const sel = document.getElementById('mc-plugins-instance-select');
  return sel ? sel.value : '';
}

function _populateMcPluginsInstanceSelector() {
  const sel = document.getElementById('mc-plugins-instance-select');
  if (!sel) return;
  const instances = (_serverManagerCache?.instances || []);
  const prev = sel.value;
  sel.innerHTML = instances.length
    ? instances.map(inst => {
      return '<option value="' + escapeHtml(inst.id) + '">' + escapeHtml(inst.name) + ' (' + (inst.hasJar ? escapeHtml(inst.version) : I18N.t('servers.notInstalled')) + ')</option>';
    }).join('')
    : '<option value="">' + I18N.t('servers.noInstances') + '</option>';
  if (prev && sel.querySelector('option[value="' + prev + '"]')) {
    sel.value = prev;
  }
}

async function loadMcPlugins() {
  const instanceId = _mcPluginsInstanceId();
  const listEl = document.getElementById('mc-plugins-list');
  const countEl = document.getElementById('mc-plugins-count');
  if (!listEl) return;

  _populateMcPluginsInstanceSelector();

  if (!instanceId) {
    listEl.innerHTML = '<p class="text-muted">' + I18N.t('servers.selectInstance') + '</p>';
    if (countEl) countEl.textContent = '';
    return;
  }

  const instance = (_serverManagerCache?.instances || []).find(i => i.id === instanceId);
  if (instance && !instance.hasJar) {
    listEl.innerHTML = '<p class="text-muted">' + I18N.t('servers.mcPluginsNotAvailable') + '</p>';
    if (countEl) countEl.textContent = '';
    return;
  }

  try {
    const data = await fetchJSON('/server/' + encodeURIComponent(instanceId) + '/mc-plugins');
    _mcPluginsCache = data.plugins || [];
    renderMcPluginsList(listEl, countEl, instanceId);
  } catch (e) {
    listEl.innerHTML = '<p class="text-muted">' + I18N.t('servers.mcPluginsLoadFailed', { msg: escapeHtml(e.message) }) + '</p>';
    if (countEl) countEl.textContent = '';
  }
}

function renderMcPluginsList(listEl, countEl, instanceId) {
  const plugins = _mcPluginsCache || [];
  const enabledCount = plugins.filter(p => p.enabled).length;
  if (countEl) countEl.textContent = enabledCount + '/' + plugins.length + ' ' + I18N.t('servers.mcPluginsEnabled');

  if (!plugins.length) {
    listEl.innerHTML = '<p class="text-muted">' + I18N.t('servers.noMcPlugins') + '</p>';
    return;
  }

  let html = '<div class="mc-plugins-grid">';
  for (const p of plugins) {
    const name = escapeHtml(p.name);
    const safeId = p.name.replace(/[^A-Za-z0-9._-]/g, '_');
    html += '<div class="mc-plugin-card' + (p.enabled ? '' : ' mc-plugin-card--disabled') + '" data-plugin="' + name + '">' +
      '<div class="mc-plugin-card-body">' +
        '<div class="mc-plugin-name">' + name + '</div>' +
        '<div class="mc-plugin-filename code">' + escapeHtml(p.filename) + '</div>' +
      '</div>' +
      '<div class="mc-plugin-card-actions">' +
        (p.enabled
          ? '<button class="btn btn--sm btn--warning-ghost" onclick="toggleMcPlugin(\'' + escapeHtml(instanceId) + '\', \'' + safeId + '\', false)" title="Disable">' + I18N.t('common.disable') + '</button>'
          : '<button class="btn btn--sm btn--success-ghost" onclick="toggleMcPlugin(\'' + escapeHtml(instanceId) + '\', \'' + safeId + '\', true)" title="Enable">' + I18N.t('common.enable') + '</button>'
        ) +
        '<button class="btn btn--sm btn--danger-ghost" onclick="deleteMcPlugin(\'' + escapeHtml(instanceId) + '\', \'' + safeId + '\')" title="Delete">' + I18N.t('common.delete') + '</button>' +
      '</div>' +
    '</div>';
  }
  html += '</div>';
  listEl.innerHTML = html;
}

const _CRITICAL_MC_PLUGINS = ['MinecraftServerAPI-1.21.x', 'DelayedTNT'];
function _isCriticalMcPlugin(name) {
  return _CRITICAL_MC_PLUGINS.includes(name);
}

async function toggleMcPlugin(instanceId, pluginName, enable) {
  if (!enable && _isCriticalMcPlugin(pluginName)) {
    const confirmed = await showConfirmDialog(
      I18N.t('servers.mcPluginCriticalDisableTitle'),
      I18N.t('servers.mcPluginCriticalDisableConfirm', { name: pluginName }),
      I18N.t('common.disable'),
      'btn-danger',
      'text-danger'
    );
    if (!confirmed) return;
  }
  try {
    const action = enable ? 'enable' : 'disable';
    const res = await postJSON('/server/' + encodeURIComponent(instanceId) + '/mc-plugins/' + encodeURIComponent(pluginName) + '/' + action);
    showToast(res.message || I18N.t('servers.mcPlugin' + (enable ? 'Enabled' : 'Disabled'), { name: pluginName }), 'success');
    await loadMcPlugins();
  } catch (e) {
    showToast(I18N.t('servers.mcPluginActionFailed', { msg: e.message }), 'error');
  }
}

async function deleteMcPlugin(instanceId, pluginName) {
  if (_isCriticalMcPlugin(pluginName)) {
    const confirmed = await showConfirmDialog(
      I18N.t('servers.mcPluginCriticalDeleteTitle'),
      I18N.t('servers.mcPluginCriticalDeleteConfirm', { name: pluginName }),
      I18N.t('common.delete'),
      'btn-danger',
      'text-danger'
    );
    if (!confirmed) return;
  }
  const confirmed = await showConfirmDialog(
    I18N.t('servers.mcPluginDeleteTitle'),
    I18N.t('servers.mcPluginDeleteConfirm', { name: pluginName }),
    I18N.t('common.delete'),
    'btn-danger',
    'text-danger'
  );
  if (!confirmed) return;
  try {
    const res = await fetch(API + '/server/' + encodeURIComponent(instanceId) + '/mc-plugins/' + encodeURIComponent(pluginName), { method: 'DELETE', headers: _withApiKey({}) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || I18N.t('servers.mcPluginDeleteFailedTitle'));
    showToast(data.message || I18N.t('servers.mcPluginDeleted', { name: pluginName }), 'success');
    await loadMcPlugins();
  } catch (e) {
    showToast(I18N.t('servers.mcPluginDeleteFailed', { msg: e.message }), 'error');
  }
}

function uploadMcPlugin() {
  const instanceId = _mcPluginsInstanceId();
  if (!instanceId) {
    showToast(I18N.t('servers.selectInstance'), 'warning');
    return;
  }
  const input = document.getElementById('mc-plugins-file-input');
  if (input) {
    input.value = '';
    input.click();
  }
}

async function confirmUploadMcPlugin() {
  const instanceId = _mcPluginsInstanceId();
  const input = document.getElementById('mc-plugins-file-input');
  const file = input && input.files && input.files[0];
  if (!instanceId || !file) return;

  if (!file.name.toLowerCase().endsWith('.jar')) {
    showToast(I18N.t('servers.mcPluginUploadInvalid'), 'error');
    return;
  }

  showToast(I18N.t('servers.mcPluginUploading', { name: file.name }), 'info');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(API + '/server/' + encodeURIComponent(instanceId) + '/mc-plugins/upload', {
      method: 'POST',
      body: formData,
      headers: _withApiKey({}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || I18N.t('servers.mcPluginUploadFailed'));
    showToast(data.message || I18N.t('servers.mcPluginUploaded', { name: file.name }), 'success');
    await loadMcPlugins();
  } catch (e) {
    showToast(I18N.t('servers.mcPluginUploadFailed', { msg: e.message }), 'error');
  }
}

/* ─── Server Manager: Create Server Modal ─── */

async function openServerCreateModal() {
  const modal = document.getElementById('server-create-modal');
  const nameInput = document.getElementById('server-create-name');
  const versionSelect = document.getElementById('server-create-version');
  const portInput = document.getElementById('server-create-port');
  const confirmBtn = document.getElementById('server-create-confirm');
  const errorEl = document.getElementById('server-create-error');
  if (!modal) return;

  nameInput.value = '';
  portInput.value = '25565';
  errorEl.classList.add('hidden');
  confirmBtn.disabled = true;

  const installed = _serverManagerCache?.installed || [];
  if (!installed.length) {
    versionSelect.innerHTML = '<option value="">' + I18N.t('servers.noInstalledVersions') + '</option>';
  } else {
    versionSelect.innerHTML = installed.map(v =>
      `<option value="${escapeHtml(v.version)}">${escapeHtml(v.version)} (${v.type.toUpperCase()})</option>`
    ).join('');
  }
  confirmBtn.disabled = !nameInput.value.trim() || !versionSelect.value;
  modal.classList.remove('hidden');
}

function closeServerCreateModal() {
  document.getElementById('server-create-modal')?.classList.add('hidden');
}

async function confirmServerCreate() {
  const name = document.getElementById('server-create-name')?.value.trim();
  const version = document.getElementById('server-create-version')?.value;
  const port = parseInt(document.getElementById('server-create-port')?.value, 10);
  if (!name || !version || isNaN(port)) return;
  closeServerCreateModal();
  try {
    const res = await postJSON('/servers/instances', { name, version, port });
    showToast(res.message || I18N.t('servers.created'), 'success');
    await loadServerManager();
  } catch (e) {
    showToast(I18N.t('servers.createFailed', { msg: e.message }), 'error');
  }
}

function validateServerCreateForm() {
  const nameInput = document.getElementById('server-create-name');
  const versionSelect = document.getElementById('server-create-version');
  const portInput = document.getElementById('server-create-port');
  const confirmBtn = document.getElementById('server-create-confirm');
  const errorEl = document.getElementById('server-create-error');
  const name = nameInput?.value.trim();
  const version = versionSelect?.value;
  const port = parseInt(portInput?.value, 10);
  const instances = (_serverManagerCache?.instances || []);

  let error = '';
  if (name && instances.some(i => i.name.toLowerCase() === name.toLowerCase())) {
    error = I18N.t('servers.createFailed', { msg: I18N.t('servers.nameExists') });
  } else if (!isNaN(port) && instances.some(i => i.port === port)) {
    error = I18N.t('servers.createFailed', { msg: I18N.t('servers.portInUse', { port }) });
  }

  if (errorEl) {
    errorEl.textContent = error;
    errorEl.classList.toggle('hidden', !error);
  }
  if (confirmBtn) confirmBtn.disabled = !name || !version || !!error;
}

/* ─── Server Manager: Download Modal ─── */
let _serverDownloadVersions = [];

async function openServerDownloadModal() {
  const modal = document.getElementById('server-download-modal');
  const select = document.getElementById('server-download-version');
  const confirmBtn = document.getElementById('server-download-confirm');
  const errorEl = document.getElementById('server-download-error');
  if (!modal || !select) return;

  select.innerHTML = '<option value="">' + I18N.t('servers.loadingVersions') + '</option>';
  confirmBtn.disabled = true;
  errorEl.classList.add('hidden');
  modal.classList.remove('hidden');

  try {
    const data = await fetchJSON('/versions');
    _serverDownloadVersions = data.versions || [];
    const safeSet = new Set(data.safe_versions || ['1.21.11']);
    select.innerHTML = _serverDownloadVersions.map(v => {
      const label = v.version + (safeSet.has(v.version) ? I18N.t('servers.safeTag') : I18N.t('servers.untestedTag'));
      return `<option value="${escapeHtml(v.version)}">${escapeHtml(label)}</option>`;
    }).join('');
    confirmBtn.disabled = false;
  } catch (e) {
    select.innerHTML = '<option value="">' + I18N.t('servers.loadVersionsFailed') + '</option>';
    errorEl.textContent = I18N.t('servers.paperVersionsFailed', { msg: e.message });
    errorEl.classList.remove('hidden');
  }
}

function closeServerDownloadModal() {
  document.getElementById('server-download-modal')?.classList.add('hidden');
}

/* ─── Server Manager: Switch Version Modal ─── */

function openServerSwitchModal() {
  const modal = document.getElementById('server-switch-modal');
  const list = document.getElementById('server-switch-list');
  if (!modal || !list) return;

  const installed = _serverManagerCache?.installed || [];
  const safeVersions = _serverManagerCache?.safe_versions || [];
  const currentVersion = _serverManagerCache?.current_version;

  if (!installed.length) {
    list.innerHTML = '<p class="text-muted">' + I18N.t('servers.downloadOneFirst') + '</p>';
  } else {
    let html = '';
    for (const v of installed) {
      const badgeClass = 'server-status-badge--' + (v.type === 'safe' ? 'safe' : v.type === 'custom' ? 'custom' : 'unsafe');
      const badgeLabel = v.type.toUpperCase();
      const isCurrent = currentVersion && v.version === currentVersion;
      if (isCurrent) {
        html += '<div class="version-card version-card--active">' +
          '<div class="version-card-info">' +
            '<div class="version-card-version">' +
              '<strong>' + escapeHtml(v.version) + '</strong>' +
              '<span class="server-status-badge ' + badgeClass + '">' + badgeLabel + '</span>' +
              '<span class="server-status-badge server-status-badge--active">CURRENT</span>' +
            '</div>' +
            '<div class="version-card-path"><code>' + escapeHtml(v.path) + '</code></div>' +
          '</div>' +
          '<div class="version-card-actions">' +
            '<span class="text-muted" style="font-size:var(--text-xs);">Active version</span>' +
          '</div>' +
        '</div>';
      } else {
        html += '<div class="version-card" style="cursor:pointer;" onclick="serverManagerPromptSwitch(\'' + escapeHtml(v.version) + '\')">' +
          '<div class="version-card-info">' +
            '<div class="version-card-version">' +
              '<strong>' + escapeHtml(v.version) + '</strong>' +
              '<span class="server-status-badge ' + badgeClass + '">' + badgeLabel + '</span>' +
            '</div>' +
            '<div class="version-card-path"><code>' + escapeHtml(v.path) + '</code></div>' +
          '</div>' +
          '<div class="version-card-actions">' +
            '<span class="text-muted" style="font-size:var(--text-xs);">Click to switch</span>' +
          '</div>' +
        '</div>';
      }
    }
    list.innerHTML = html;
  }

  modal.classList.remove('hidden');
}

function closeServerSwitchModal() {
  document.getElementById('server-switch-modal')?.classList.add('hidden');
}

async function confirmServerDownload() {
  const select = document.getElementById('server-download-version');
  const version = select?.value;
  if (!version) return;
  closeServerDownloadModal();
  showToast(I18N.t('servers.downloading', { version }), 'info');
  try {
    const res = await postJSON('/servers/download', { version });
    if (res.status === 'already_installed') {
      showToast(
        I18N.t('servers.versionAlreadyActive', { version }),
        'info'
      );
    } else {
      showToast(res.message || I18N.t('servers.downloaded', { version }), 'success');
    }
    await loadServerManager();
  } catch (e) {
    showToast(I18N.t('servers.downloadFailed', { msg: e.message }), 'error');
  }
}

/* ─── Server Manager: Custom Jar Modal ─── */
function openServerCustomModal() {
  const modal = document.getElementById('server-custom-modal');
  const nameInput = document.getElementById('server-custom-name');
  const fileInput = document.getElementById('server-custom-file');
  const confirmBtn = document.getElementById('server-custom-confirm');
  const errorEl = document.getElementById('server-custom-error');
  if (!modal) return;

  if (nameInput) nameInput.value = '';
  if (fileInput) fileInput.value = '';
  if (confirmBtn) confirmBtn.disabled = true;
  if (errorEl) errorEl.classList.add('hidden');
  modal.classList.remove('hidden');
}

function closeServerCustomModal() {
  document.getElementById('server-custom-modal')?.classList.add('hidden');
}

function validateServerCustomForm() {
  const name = document.getElementById('server-custom-name')?.value?.trim();
  const file = document.getElementById('server-custom-file')?.files?.[0];
  const confirmBtn = document.getElementById('server-custom-confirm');
  if (confirmBtn) confirmBtn.disabled = !(name && file && file.name.endsWith('.jar'));
}

async function confirmServerCustom() {
  const nameInput = document.getElementById('server-custom-name');
  const fileInput = document.getElementById('server-custom-file');
  const name = nameInput?.value?.trim();
  const file = fileInput?.files?.[0];
  if (!name || !file) return;

  closeServerCustomModal();
  showToast(I18N.t('servers.importing', { name }), 'info');

  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', name);

  try {
    const res = await fetch(API + '/servers/custom', {
      method: 'POST',
      body: formData,
      headers: _withApiKey({}),
    });
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    const data = await res.json();
    showToast(data.message || I18N.t('servers.imported', { name }), 'success');
    await loadServerManager();
  } catch (e) {
    showToast(I18N.t('servers.importFailed', { msg: e.message }), 'error');
  }
}

function renderOverlayUrls() {
  const container = document.getElementById('overlay-urls');
  if (!container) return;
  let html = '<h3 class="overlay-section-title">' + I18N.t('overlays.builtin') + '</h3>';
  const base = location.origin + '/api/v1/overlay';
  const overlayNames = ['default'];
  if (currentConfig.overlay && Array.isArray(currentConfig.overlay.overlays)) {
    for (const o of currentConfig.overlay.overlays) {
      if (o.name && !overlayNames.includes(o.name)) overlayNames.push(o.name);
    }
  }
  for (const name of overlayNames) {
    const u = `${base}?overlay=${encodeURIComponent(name)}&chroma=1`;
    const preview = `${base}?overlay=${encodeURIComponent(name)}&chroma=0`;
    html += `<div class="card overlay-item" data-overlay="${escapeHtml(name)}">
      <div class="url-row">
        <span class="overlay-name">${escapeHtml(name)}</span>
        <code>${u}</code>
        <button class="btn-copy" onclick="copyUrl(this,'${u}')">${I18N.t('common.copy')}</button>
        <button class="btn-test" onclick="testOverlay('${encodeURIComponent(name)}', this)">${I18N.t('overlays.test')}</button>
      </div>
      <iframe class="overlay-preview" src="${preview}" title="${escapeHtml(I18N.t('overlays.preview'))}" loading="lazy"></iframe>
    </div>`;
  }
  // Plugin overlay URLs
  const en = currentPlugins.filter(p => p.enabled && p.port > 0);
  if (en.length) {
    html += '<h3 class="overlay-section-title">' + I18N.t('overlays.plugins') + '</h3>';
    html += en.map(p => {
      const u = `http://localhost:${p.port}`;
      return `<div class="card overlay-item" data-overlay="${escapeHtml(p.name)}">
        <div class="url-row">
          <span class="overlay-name">${escapeHtml(p.display_name || p.name)}</span>
          <code>${u}</code>
          <button class="btn-copy" onclick="copyUrl(this,'${u}')">${I18N.t('common.copy')}</button>
        </div>
        <iframe class="overlay-preview" src="${u}" title="${escapeHtml(I18N.t('overlays.preview'))}" loading="lazy"></iframe>
      </div>`;
    }).join('');
  }
  container.innerHTML = html;
}

async function testOverlay(encodedName, btn) {
  const overlayName = decodeURIComponent(encodedName);
  const el = btn;
  const original = el ? el.textContent : '';
  if (el) {
    el.disabled = true;
    el.textContent = I18N.t('overlays.testing');
  }
  try {
    await postJSON('/overlay/display', {
      overlay_name: overlayName,
      title: I18N.t('overlays.testTitle'),
      subtitle: I18N.t('overlays.testSubtitle'),
      duration: 3,
    });
    showToast(I18N.t('overlays.testSent', { name: overlayName }), 'success');
    log(`[OVERLAY TEST] ${overlayName}: ${I18N.t('overlays.testTitle')}`, 'info');
  } catch (e) {
    showToast(I18N.t('overlays.testFailed') + ': ' + e.message, 'error');
    log('Overlay test failed: ' + e.message, 'err');
  } finally {
    if (el) {
      el.disabled = false;
      el.textContent = original;
    }
  }
}

/* ─── Revenue View ─── */

let _revenueData = { entries: [], file: {} };

function _revenueRound2(value) {
  return Math.round(value * 100) / 100;
}

async function loadRevenueView() {
  try {
    const data = await fetchJSON('/revenue');
    _revenueData = data && Array.isArray(data.entries) ? data : { entries: [], file: {} };
    renderRevenueView();
  } catch (e) {
    log('Revenue load failed: ' + e.message, 'err');
    const chart = document.getElementById('revenue-chart');
    const wrap = document.getElementById('revenue-table-wrap');
    if (chart) chart.innerHTML = '<p class="text-muted">' + I18N.t('revenue.failedLoad') + '</p>';
    if (wrap) wrap.innerHTML = '';
  }
}

function _revenueISODate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function revenueSetPeriod(days) {
  const from = document.getElementById('revenue-from');
  const to = document.getElementById('revenue-to');
  if (days > 0) {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - (days - 1));
    from.value = _revenueISODate(start);
    to.value = _revenueISODate(end);
  } else {
    from.value = '';
    to.value = '';
  }
  document.querySelectorAll('.revenue-period').forEach(el => {
    el.classList.toggle('active', Number(el.dataset.days) === days);
  });
  revenueApplyFilters();
}

function revenueClearFilters() {
  document.getElementById('revenue-from').value = '';
  document.getElementById('revenue-to').value = '';
  document.querySelectorAll('.revenue-period').forEach(el => el.classList.remove('active'));
  revenueApplyFilters();
}

function revenueApplyFilters() {
  renderRevenueView();
}

function filterRevenueEntries(entries, from, to) {
  return (entries || []).filter(e => {
    if (from && e.date < from) return false;
    if (to && e.date > to) return false;
    return true;
  }).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

function computeRevenueStats(entries) {
  const values = (entries || []).map(e => e.estimated_revenue_usd);
  const count = values.length;
  if (!count) {
    return {
      count: 0,
      totalUsd: 0,
      averageUsd: 0,
      best: null,
      worst: null,
      lastChangeUsd: null,
      last7Usd: 0,
      prev7Usd: 0,
      delta7Usd: 0,
    };
  }
  let best = null;
  let worst = null;
  for (const e of entries) {
    if (!best || e.estimated_revenue_usd > best.value) best = { date: e.date, value: e.estimated_revenue_usd };
    if (!worst || e.estimated_revenue_usd < worst.value) worst = { date: e.date, value: e.estimated_revenue_usd };
  }
  const total = values.reduce((s, v) => s + v, 0);
  const last = values[count - 1];
  const prev = values[count - 2];
  const last7 = values.slice(-7).reduce((s, v) => s + v, 0);
  const prev7 = values.slice(-14, -7).reduce((s, v) => s + v, 0);
  return {
    count,
    totalUsd: _revenueRound2(total),
    averageUsd: _revenueRound2(total / count),
    best,
    worst,
    lastChangeUsd: count >= 2 ? _revenueRound2(last - prev) : null,
    last7Usd: _revenueRound2(last7),
    prev7Usd: _revenueRound2(prev7),
    delta7Usd: _revenueRound2(last7 - prev7),
  };
}

function formatCurrency(value) {
  const v = Number(value) || 0;
  const neg = v < 0;
  const abs = Math.abs(v);
  const parts = abs.toFixed(2).split('.');
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return (neg ? '-' : '') + '$' + parts.join('.');
}

function formatCurrencyDelta(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const sign = value > 0 ? '+' : '';
  return sign + formatCurrency(value);
}

function renderRevenueSummary(entries) {
  const el = document.getElementById('revenue-summary');
  if (!el) return;
  const stats = computeRevenueStats(entries);
  const cards = [
    { label: I18N.t('revenue.totalFiltered'), value: formatCurrency(stats.totalUsd) },
    { label: I18N.t('revenue.daysWithRevenue'), value: String(stats.count) },
    { label: I18N.t('revenue.averagePerDay'), value: formatCurrency(stats.averageUsd) },
    {
      label: I18N.t('revenue.bestDay'),
      value: stats.best
        ? formatCurrency(stats.best.value) + ' <span class="text-muted">' + escapeHtml(stats.best.date) + '</span>'
        : '—',
    },
    {
      label: I18N.t('revenue.worstDay'),
      value: stats.worst
        ? formatCurrency(stats.worst.value) + ' <span class="text-muted">' + escapeHtml(stats.worst.date) + '</span>'
        : '—',
    },
    { label: I18N.t('revenue.last7Days'), value: formatCurrency(stats.last7Usd) },
    {
      label: I18N.t('revenue.last7VsPrev7'),
      value: formatCurrencyDelta(stats.delta7Usd),
      delta: stats.delta7Usd,
    },
  ];
  el.innerHTML = cards.map(c =>
    '<div class="status-card">' +
      '<span class="status-card__label">' + escapeHtml(c.label) + '</span>' +
      '<span class="status-card__value' + (c.delta == null ? '' : (c.delta >= 0 ? ' success' : ' danger')) + '">' + c.value + '</span>' +
    '</div>'
  ).join('');
}

function renderRevenueChart(entries) {
  const el = document.getElementById('revenue-chart');
  if (!el) return;
  if (!entries.length) {
    el.innerHTML = '<p class="text-muted">' + I18N.t('revenue.noData') + '</p>';
    return;
  }
  const max = Math.max(...entries.map(e => e.estimated_revenue_usd), 0.01);
  const labelEvery = Math.ceil(entries.length / 12);
  el.innerHTML = entries.map((e, i) => {
    const h = Math.max(4, Math.round((e.estimated_revenue_usd / max) * 100));
    const label = i % labelEvery === 0 || i === entries.length - 1 ? e.date.slice(5) : '';
    return '<div class="revenue-bar" title="' + escapeHtml(e.date) + ': ' + formatCurrency(e.estimated_revenue_usd) + '">' +
      '<div class="revenue-bar-fill" style="height:' + h + '%"></div>' +
      '<span class="revenue-bar-label">' + escapeHtml(label) + '</span>' +
    '</div>';
  }).join('');
}

function renderRevenueTable(entries) {
  const wrap = document.getElementById('revenue-table-wrap');
  if (!wrap) return;
  if (!entries.length) {
    wrap.innerHTML = '<p class="text-muted">' + I18N.t('revenue.noData') + '</p>';
    return;
  }
  let html = '<table class="plugin-table"><thead><tr><th>Date</th><th>Revenue</th><th>Change</th></tr></thead><tbody>';
  let prev = null;
  for (const e of entries) {
    const delta = prev != null ? e.estimated_revenue_usd - prev : null;
    const deltaHtml = delta == null
      ? '—'
      : '<span class="revenue-delta ' + (delta >= 0 ? 'revenue-delta--up' : 'revenue-delta--down') + '">' + formatCurrencyDelta(delta) + '</span>';
    html += '<tr>' +
      '<td data-label="Date">' + escapeHtml(e.date) + '</td>' +
      '<td data-label="Revenue">' + formatCurrency(e.estimated_revenue_usd) + '</td>' +
      '<td data-label="Change">' + deltaHtml + '</td>' +
    '</tr>';
    prev = e.estimated_revenue_usd;
  }
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function renderRevenueView() {
  const fromEl = document.getElementById('revenue-from');
  const toEl = document.getElementById('revenue-to');
  const from = fromEl ? fromEl.value : '';
  const to = toEl ? toEl.value : '';
  const entries = filterRevenueEntries(_revenueData.entries, from, to);
  renderRevenueSummary(entries);
  renderRevenueChart(entries);
  renderRevenueTable(entries);
}

/* ─── Sessions ─── */
let _sessionsData = { total: 0, sessions: [], total_gifts: 0, total_gift_value_usd: 0, total_likes: 0, total_follows: 0, total_comments: 0, total_shares: 0, total_joins: 0 };

async function loadSessions() {
  try {
    const data = await fetchJSON('/sessions');
    _sessionsData = data && Array.isArray(data.sessions) ? data : { total: 0, sessions: [] };
    renderSessionsView();
  } catch (e) {
    log('Sessions load failed: ' + e.message, 'err');
    const wrap = document.getElementById('sessions-table-wrap');
    const summary = document.getElementById('sessions-summary');
    if (wrap) wrap.innerHTML = '<p class="text-muted">' + I18N.t('sessions.failedLoad') + '</p>';
    if (summary) summary.innerHTML = '';
  }
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  return h > 0 ? h + 'h ' + mm + 'm ' + ss + 's' : (m > 0 ? m + 'm ' + ss + 's' : s + 's');
}

function renderSessionsSummary() {
  const el = document.getElementById('sessions-summary');
  if (!el) return;
  const d = _sessionsData;
  const cards = [
    { label: I18N.t('sessions.total'), value: String(d.total) },
    { label: I18N.t('sessions.totalGifts'), value: String(d.total_gifts || 0) },
    { label: I18N.t('sessions.totalGiftValue'), value: formatCurrency(d.total_gift_value_usd) },
    { label: I18N.t('sessions.totalLikes'), value: String(d.total_likes || 0) },
    { label: I18N.t('sessions.totalFollows'), value: String(d.total_follows || 0) },
    { label: I18N.t('sessions.totalComments'), value: String(d.total_comments || 0) },
    { label: I18N.t('sessions.totalShares'), value: String(d.total_shares || 0) },
    { label: I18N.t('sessions.totalJoins'), value: String(d.total_joins || 0) },
  ];
  el.innerHTML = cards.map(c =>
    '<div class="status-card">' +
      '<span class="status-card__label">' + escapeHtml(c.label) + '</span>' +
      '<span class="status-card__value">' + c.value + '</span>' +
    '</div>'
  ).join('');
}

function renderSessionsTable() {
  const wrap = document.getElementById('sessions-table-wrap');
  if (!wrap) return;
  const sessions = _sessionsData.sessions || [];
  if (!sessions.length) {
    wrap.innerHTML = '<p class="text-muted">' + I18N.t('sessions.noData') + '</p>';
    return;
  }
  const reversed = [...sessions].reverse();
  const rows = reversed.map(s =>
    '<tr>' +
      '<td data-label="' + I18N.t('sessions.colStart') + '">' + escapeHtml(s.start || '') + '</td>' +
      '<td data-label="' + I18N.t('sessions.colDuration') + '">' + formatDuration(s.duration_seconds) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colGifts') + '">' + String(s.gifts || 0) + ' <span class="text-muted">(' + formatCurrency(s.gift_value_usd) + ')</span></td>' +
      '<td data-label="' + I18N.t('sessions.colLikes') + '">' + String(s.likes || 0) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colFollows') + '">' + String(s.follows || 0) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colComments') + '">' + String(s.comments || 0) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colShares') + '">' + String(s.shares || 0) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colJoins') + '">' + String(s.joins || 0) + '</td>' +
    '</tr>'
  ).join('');
  wrap.innerHTML = '<table class="plugin-table"><thead><tr>' +
    '<th>' + I18N.t('sessions.colStart') + '</th>' +
    '<th>' + I18N.t('sessions.colDuration') + '</th>' +
    '<th>' + I18N.t('sessions.colGifts') + '</th>' +
    '<th>' + I18N.t('sessions.colLikes') + '</th>' +
    '<th>' + I18N.t('sessions.colFollows') + '</th>' +
    '<th>' + I18N.t('sessions.colComments') + '</th>' +
    '<th>' + I18N.t('sessions.colShares') + '</th>' +
    '<th>' + I18N.t('sessions.colJoins') + '</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>';
}

function renderSessionsView() {
  renderSessionsSummary();
  renderSessionsTable();
}

async function downloadSessionsReport() {
  try {
    showToast(I18N.t('sessions.downloading'), 'info');
    const resp = await fetch(API + '/sessions/report', { headers: _withApiKey({}) });
    if (!resp.ok) await _throwResError(resp);
    const content = await resp.text();
    const filename = 'tiktok2mc-session-report-' + new Date().toISOString().slice(0, 10) + '.md';

    if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.download_file) {
      const path = await pywebview.api.download_file(content, filename);
      if (path && !path.startsWith('error:')) {
        showToast(I18N.t('sessions.reportSaved', { path }), 'success');
      } else {
        showToast(I18N.t('sessions.downloadFailed'), 'error');
      }
      return;
    }

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(I18N.t('sessions.reportSaved', { path: filename }), 'success');
  } catch (e) {
    showToast(e.message || I18N.t('sessions.downloadFailed'), 'error');
  }
}

/* ─── Backups ─── */
let _backupsData = { categories: [], total: 0 };

async function loadBackups() {
  try {
    const data = await fetchJSON('/backups');
    _backupsData = data && Array.isArray(data.categories) ? data : { categories: [], total: 0 };
    renderBackups();
  } catch (e) {
    log('Backups load failed: ' + e.message, 'err');
    const root = document.getElementById('backups-root');
    if (root) root.innerHTML = '<p class="text-muted">' + I18N.t('backups.failedLoad') + '</p>';
  }
}

function _formatBytes(n) {
  const v = Number(n) || 0;
  if (v < 1024) return v + ' B';
  if (v < 1048576) return (v / 1024).toFixed(1) + ' KB';
  return (v / 1048576).toFixed(1) + ' MB';
}

function _backupCategoryLabel(category) {
  if (category === 'config') return I18N.t('backups.catConfig');
  if (category === 'actions') return I18N.t('backups.catActions');
  if (category === 'event_commands') return I18N.t('backups.catEventCommands');
  if (category === 'plugin_registry') return I18N.t('backups.catPluginRegistry');
  if (category === 'migration') return I18N.t('backups.catMigration');
  if (category === '_other') return I18N.t('backups.catOther');
  if (category === 'hook_registry') return I18N.t('backups.catHookRegistry');
  if (category.startsWith('plugins/')) return I18N.t('backups.catPlugin') + ': ' + escapeHtml(category.slice('plugins/'.length));
  return escapeHtml(category);
}

function renderBackups() {
  const root = document.getElementById('backups-root');
  if (!root) return;
  if (!_backupsData.categories.length) {
    root.innerHTML = '<p class="text-muted">' + I18N.t('backups.empty') + '</p>';
    return;
  }
  const colWhen = I18N.t('backups.colWhen');
  const colFile = I18N.t('backups.colFile');
  const colSize = I18N.t('backups.colSize');
  const colAction = I18N.t('backups.colAction');
  const html = _backupsData.categories.map(cat => {
    const needsCustomTarget = cat.category === '_other' || cat.category === 'hook_registry';
    const rows = cat.entries.map(e => {
      const restoreBtn = e.restorable
        ? `<button class="btn btn--secondary btn--sm" onclick="restoreBackup('${e.category}', '${e.filename}')">${I18N.t('backups.restore')}</button>`
        : `<button class="btn btn--secondary btn--sm" onclick="restoreBackupCustom('${e.category}', '${e.filename}')">${I18N.t('backups.restore')}</button>`;
      return '<tr>' +
        '<td data-label="' + colWhen + '">' + escapeHtml(e.label || '—') + '</td>' +
        '<td class="backup-filename" data-label="' + colFile + '">' + escapeHtml(e.filename) + '</td>' +
        '<td data-label="' + colSize + '">' + _formatBytes(e.size) + '</td>' +
        '<td class="backup-actions" data-label="' + colAction + '">' + restoreBtn + '</td>' +
        '</tr>';
    }).join('');
    return '<section class="view-section backup-category">' +
      '<h3>' + _backupCategoryLabel(cat.category) + ' <span class="backup-count">' + cat.count + '</span></h3>' +
      '<div class="backup-table-wrap">' +
      '<table class="backup-table"><thead><tr>' +
      '<th>' + colWhen + '</th>' +
      '<th>' + colFile + '</th>' +
      '<th>' + colSize + '</th>' +
      '<th></th></tr></thead><tbody>' + rows + '</tbody></table>' +
      '</div></section>';
  }).join('');
  root.innerHTML = html;
}

function restoreBackup(category, filename) {
  showConfirmDialog(
    I18N.t('backups.restoreTitle'),
    I18N.t('backups.restoreWarning', { filename }),
    I18N.t('backups.restore'),
    'btn-danger'
  ).then(confirmed => {
    if (!confirmed) return;
    postJSON('/backups/restore', { category, filename })
      .then(() => {
        showToast(I18N.t('backups.restored'), 'success');
        loadBackups();
      })
      .catch(e => showToast(e.message, 'error'));
  });
}

async function restoreBackupCustom(category, filename) {
  const target = await showPromptDialog(
    I18N.t('backups.restoreTitle'),
    I18N.t('backups.restoreCustomTarget', { filename }),
    '',
    I18N.t('backups.restore'),
    'btn-danger'
  );
  if (!target) return;
  const confirmed = await showConfirmDialog(
    I18N.t('backups.restoreTitle'),
    I18N.t('backups.restoreCustomWarning', { filename, target }),
    I18N.t('backups.restore'),
    'btn-danger'
  );
  if (!confirmed) return;
  try {
    await postJSON('/backups/restore', { category, filename, target });
    showToast(I18N.t('backups.restored'), 'success');
    loadBackups();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function createBackupsNow() {
  try {
    const res = await postJSON('/backups/create', { targets: ['config', 'actions', 'plugin_registry'] });
    const count = res.created ? res.created.length : 0;
    showToast(count > 0 ? I18N.t('backups.created', { count }) : I18N.t('backups.upToDate'), count > 0 ? 'success' : 'info');
    loadBackups();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

/* ─── Config Bundle ─── */

function _arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function exportConfigBundle() {
  try {
    showToast(I18N.t('backups.bundleExporting'), 'info');
    const resp = await fetch(API + '/config-bundle', { headers: _withApiKey({}) });
    if (!resp.ok) await _throwResError(resp);
    const buf = await resp.arrayBuffer();
    const filename = 'tiktok2mc-config-bundle.zip';

    if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.download_file_b64) {
      const path = await pywebview.api.download_file_b64(_arrayBufferToBase64(buf), filename);
      if (path && !path.startsWith('error:')) {
        showToast(I18N.t('backups.bundleExportedPath', { path }), 'success');
      } else {
        showToast(I18N.t('backups.bundleExportFailed'), 'error');
      }
      return;
    }

    const blob = new Blob([buf], { type: 'application/zip' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(I18N.t('backups.bundleExportedPath', { path: filename }), 'success');
  } catch (e) {
    showToast(e.message || I18N.t('backups.bundleExportFailed'), 'error');
  }
}

function importConfigBundle() {
  const input = document.getElementById('bundle-file-input');
  if (!input) return;
  input.value = '';
  input.onchange = () => {
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;
    showConfirmDialog(
      I18N.t('backups.bundleImportTitle'),
      I18N.t('backups.bundleImportWarning'),
      I18N.t('backups.bundleImport'),
      'btn-primary'
    ).then(confirmed => {
      if (confirmed) _uploadConfigBundle(file);
    });
  };
  input.click();
}

async function _uploadConfigBundle(file) {
  try {
    showToast(I18N.t('backups.bundleImporting'), 'info');
    const form = new FormData();
    form.append('file', file, file.name || 'bundle.zip');
    const resp = await fetch(API + '/config-bundle/import', {
      method: 'POST',
      headers: _withApiKey({}),
      body: form
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(body.detail || I18N.t('backups.bundleImportFailed', { msg: resp.status }));
    }
    showToast(I18N.t('backups.bundleImported', { count: body.count || 0 }), 'success');
    loadBackups();
  } catch (e) {
    showToast(e.message || I18N.t('backups.bundleImportFailed', { msg: '' }), 'error');
  }
}

function _currentOS() {
  const p = (navigator.platform || '').toLowerCase();
  return p.includes('win') ? 'windows' : 'linux';
}

function _platformLabel(platform) {
  if (!platform || platform === 'all') return I18N.t('plugins.platformAll');
  if (platform === 'linux') return I18N.t('plugins.platformLinux');
  if (platform === 'windows') return I18N.t('plugins.platformWindows');
  return platform;
}

function _isPlatformCompatible(plugin) {
  const pp = plugin.platform || 'all';
  return pp === 'all' || pp === _currentOS();
}

function renderPluginManager() {
  const tableDiv = document.getElementById('plugin-manager-table');
  if (!tableDiv) return;
  if (!currentPlugins.length) {
    tableDiv.innerHTML = '<p class="muted">' + I18N.t('plugins.noPlugins') + '</p>';
    return;
  }
  let html = '<table class="plugin-table"><thead><tr><th>Name</th><th>Version</th><th>' + I18N.t('plugins.platform') + '</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
  for (const p of currentPlugins) {
    const status = getPluginStatus(p);
    const hasError = !!p.error;
    const compatible = _isPlatformCompatible(p);
    const errorTitle = hasError ? ` title="${escapeHtml(p.error)}"` : '';
    const enableDisabled = hasError || !compatible ? ' disabled' : '';
    const platformBadge = !compatible
      ? '<span class="plugin-status status-disabled" title="' + I18N.t('plugins.platformIncompatible') + '">' + _platformLabel(p.platform) + ' ⚠️</span>'
      : (p.platform && p.platform !== 'all' ? '<span class="plugin-status status-info">' + _platformLabel(p.platform) + '</span>' : '<span class="text-muted">—</span>');
    const action = p.enabled
      ? `<button class="btn btn-danger" style="padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="promptDisablePlugin('${escapeHtml(p.name)}', '${escapeHtml(p.display_name || p.name)}')">${I18N.t('common.disable')}</button>`
      : `<button class="btn btn-primary" style="padding:0.3rem 0.6rem;font-size:0.8rem;"${enableDisabled} onclick="promptEnablePlugin('${escapeHtml(p.name)}', '${escapeHtml(p.display_name || p.name)}')">${I18N.t('common.enable')}</button>`;
    const editDisabled = hasError ? ' disabled' : '';
    html += `<tr${errorTitle}>
      <td data-label="Name">${escapeHtml(p.display_name || p.name)}${hasError ? ' <span class="status-error-indicator" title="' + escapeHtml(p.error) + '">⚠️</span>' : ''}</td>
      <td data-label="Version">${p.version || '-'}</td>
      <td data-label="${I18N.t('plugins.platform')}">${platformBadge}</td>
      <td data-label="Status"><span class="plugin-status ${status.cls}">${status.label}</span></td>
      <td data-label="Actions">${action} <button class="btn btn-secondary" style="padding:0.3rem 0.6rem;font-size:0.8rem;"${editDisabled} onclick="pluginEditor.openInline('${escapeHtml(p.name)}', '${escapeHtml(p.display_name || p.name)}')">Edit Config</button> <button class="btn btn-secondary" style="padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="openReadmeModal('${escapeHtml(p.name)}', '${escapeHtml(p.display_name || p.name)}')">Readme</button></td>
    </tr>`;
    if (hasError) {
      html += `<tr class="error-detail-row"><td colspan="5"><span class="error-detail">${escapeHtml(p.error)}</span></td></tr>`;
    }
  }
  html += '</tbody></table>';
  tableDiv.innerHTML = html;
}

/* ─── Plugin Dashboard Pages (manifest: dashboard_ui) ─── */

const PLUGIN_PAGE_PREFIX = 'plugindash-';

const _PLUGIN_PAGE_ICON = '<svg class="nav-icon" viewBox="0 0 24 24" width="20" height="20"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.488.488 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1115.6 12 3.611 3.611 0 0112 15.6z" fill="currentColor"/></svg>';

function pluginPageViewId(name) {
  return PLUGIN_PAGE_PREFIX + name;
}

function _currentGuiTheme() {
  return document.documentElement.getAttribute('data-theme') || 'dark';
}

function _pluginPageUrl(name, theme) {
  let url = API + '/plugins/' + encodeURIComponent(name) + '/dashboard';
  if (theme) url += '?theme=' + encodeURIComponent(theme);
  return url;
}

function _retargetPluginFrames(theme) {
  document.querySelectorAll('.plugin-page-frame').forEach(f => {
    if (!f.dataset.pluginName) return;
    const url = _pluginPageUrl(f.dataset.pluginName, theme);
    if (f.src) {
      f.src = url;
    } else {
      f.dataset.src = url;
    }
  });
}

function renderPluginPagesNav() {
  const nav = document.querySelector('.sidebar-nav');
  const main = document.getElementById('dashboard');
  if (!nav || !main) return;
  const pages = currentPlugins.filter(p => p.dashboard_ui && p.enabled && !p.error);
  const desiredIds = pages.map(p => pluginPageViewId(p.name));
  const existingIds = [...nav.querySelectorAll('.nav-item[data-plugin-page]')]
    .map(b => b.getAttribute('data-view'));
  // Unchanged page set -> leave DOM alone so the active tab and any
  // already-loaded plugin iframes survive the periodic loadPlugins() poll.
  if (existingIds.length === desiredIds.length &&
      desiredIds.every((id, i) => id === existingIds[i])) return;
  const activeId = main.querySelector('.view.active[data-plugin-page]')?.id || null;
  const frameSrcs = {};
  main.querySelectorAll('.view[data-plugin-page]').forEach(v => {
    const f = v.querySelector('iframe');
    if (f && f.src) frameSrcs[v.id] = f.src;
  });
  document.querySelectorAll('.nav-item[data-plugin-page]').forEach(el => el.remove());
  document.querySelectorAll('.view[data-plugin-page]').forEach(el => el.remove());
  const theme = _currentGuiTheme();
  for (const p of pages) {
    const label = p.display_name || p.name;
    const viewId = pluginPageViewId(p.name);
    const url = _pluginPageUrl(p.name, theme);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'nav-item';
    btn.setAttribute('data-view', viewId);
    btn.setAttribute('data-plugin-page', '1');
    btn.title = label;
    btn.innerHTML = _PLUGIN_PAGE_ICON +
      '<span class="nav-label">' + escapeHtml(label) + '</span>';
    btn.onclick = () => openPluginDashboard(p.name);
    nav.appendChild(btn);

    const view = document.createElement('div');
    view.className = 'view';
    view.id = 'view-' + viewId;
    view.setAttribute('data-plugin-page', '1');
    view.innerHTML =
      '<div class="view-header"><h2>' + escapeHtml(label) + '</h2>' +
      '<a class="btn btn--secondary" href="' + url + '" target="_blank" rel="noopener">' +
      I18N.t('plugins.pageOpenExternal') + '</a></div>' +
      '<iframe class="plugin-page-frame" title="' + escapeHtml(label) + '" loading="lazy"></iframe>';
    const frame = view.querySelector('iframe');
    frame.dataset.pluginName = p.name;
    const prevSrc = frameSrcs['view-' + viewId];
    if (prevSrc) {
      frame.src = prevSrc; // keep already-loaded page instead of reloading
    } else {
      frame.dataset.src = url; // lazy-load on first open
    }
    main.appendChild(view);
  }
  if (activeId) {
    // Restore the previously active plugin tab after a rebuild
    const vid = activeId.replace(/^view-/, '');
    nav.querySelector(`.nav-item[data-view="${vid}"]`)?.classList.add('active');
    document.getElementById(activeId)?.classList.add('active');
  }
}

function openPluginDashboard(name) {
  const view = document.getElementById('view-' + pluginPageViewId(name));
  if (!view) return;
  const frame = view.querySelector('iframe');
  if (frame && !frame.src && frame.dataset.src) frame.src = frame.dataset.src;
  switchView(pluginPageViewId(name));
}

/* ─── Plugin View ─── */

function openInlinePluginConfig(pluginName, displayName) {  _hideAllEditors();
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelector('.nav-item[data-view="plugins"]')?.classList.add('active');
  pluginEditor.openInline(pluginName, displayName);
}

function closeInlinePluginConfig() {
  pluginEditor.closeInline();
}

function copyUrl(btn, url) {
  navigator.clipboard.writeText(url).then(() => {
    btn.textContent = I18N.t('common.copied');
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = I18N.t('common.copy'); btn.classList.remove('copied'); }, 1500);
  });
}

function isBuiltinPlugin(name) {
  // Bundled status comes from the plugin manifest ("bundled": true) via
  // GET /plugins — the frontend must not hardcode plugin names.
  const plugin = currentPlugins.find(p => p.name === name);
  return !!(plugin && plugin.bundled);
}

async function promptEnablePlugin(name, displayName) {
  const plugin = currentPlugins.find(p => p.name === name);
  if (plugin && !_isPlatformCompatible(plugin)) {
    showToast(I18N.t('plugins.platformCannotEnable', { platform: _platformLabel(plugin.platform), current: _currentOS() }), 'error');
    return;
  }
  const isBuiltin = isBuiltinPlugin(name);
  let message = I18N.t('plugins.enableConfirm', { name: displayName || name });
  if (!isBuiltin) {
    message = I18N.t('plugins.enableExternalWarning');
  }
  const confirmed = await showConfirmDialog(
    I18N.t('plugins.enableTitle'),
    message,
    I18N.t('common.enable'),
    isBuiltin ? 'btn-primary' : 'btn-danger',
    isBuiltin ? '' : 'text-danger'
  );
  if (!confirmed) return;
  try {
    await postJSON(`/plugins/${name}/enable`, {});
    await loadPlugins();
    showToast(I18N.t('plugins.enabledToast', { name: displayName || name }), 'success');
    log(`Plugin ${name} enabled`);
  } catch (e) {
    const msg = I18N.t('plugins.enableFailed', { name: displayName || name, msg: e.message });
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

async function promptDisablePlugin(name, displayName) {
  const confirmed = await showConfirmDialog(
    I18N.t('plugins.disableTitle'),
    I18N.t('plugins.disableConfirm', { name: displayName || name }),
    I18N.t('common.disable'),
    'btn-danger'
  );
  if (!confirmed) return;
  try {
    await postJSON(`/plugins/${name}/disable`, {});
    await loadPlugins();
    showToast(I18N.t('plugins.disabledToast', { name: displayName || name }), 'info');
    log(`Plugin ${name} disabled`);
  } catch (e) {
    const msg = I18N.t('plugins.disableFailed', { name: displayName || name, msg: e.message });
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

async function restartPlugin(name, displayName) {
  try {
    log(`Restarting plugin ${name}...`);
    await postJSON(`/plugins/${name}/disable`, {});
    await loadPlugins();
    // Small delay to let the stop signal be processed
    await new Promise(r => setTimeout(r, 800));
    await postJSON(`/plugins/${name}/enable`, {});
    await loadPlugins();
    showToast(I18N.t('plugins.restartedToast', { name: displayName || name }), 'success');
    log(`Plugin ${name} restarted successfully.`);
  } catch (e) {
    const msg = I18N.t('plugins.restartFailed', { name: displayName || name, msg: e.message });
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

/* ─── Plugin README Modal ─── */

async function openReadmeModal(pluginName, displayName) {
  const modal = document.getElementById('readme-modal');
  const title = document.getElementById('readme-modal-title');
  const body = document.getElementById('readme-modal-body');
  if (!modal || !title || !body) return;

  title.textContent = displayName || pluginName;
  body.innerHTML = '<p class="muted">Loading…</p>';
  modal.classList.remove('hidden');

  try {
    const res = await fetch(`${API}/plugins/${encodeURIComponent(pluginName)}/readme`, { headers: _withApiKey({}) });
    if (!res.ok) {
      body.innerHTML = '<p class="muted">No README available for this plugin.</p>';
      return;
    }
    const md = await res.text();
    body.innerHTML = typeof marked !== 'undefined'
      ? sanitizeMarkdownHtml(marked.parse(md))
      : escapeHtml(md);
  } catch {
    body.innerHTML = '<p class="muted">Failed to load README.</p>';
  }
}

function closeReadmeModal() {
  document.getElementById('readme-modal')?.classList.add('hidden');
}

/* ─── Hook Management ─── */

function getHookStatus(h) {
  if (h.error) return { label: I18N.t('common.error'), cls: 'status-error' };
  if (!h.enabled) return { label: I18N.t('common.disabled'), cls: 'status-disabled' };
  return { label: I18N.t('common.enabled'), cls: 'status-enabled' };
}

async function loadHooks() {
  try {
    const data = await fetchJSON('/hooks');
    currentHooks = data.hooks || [];
    renderHookManager();
  } catch (e) {
    log('Hooks load failed: ' + e.message, 'err');
  }
}

async function refreshHooks() {
  try {
    await postJSON('/hooks/discover', {});
    await loadHooks();
    showToast(I18N.t('plugins.refreshed'), 'success');
  } catch (e) {
    showToast(I18N.t('hooks.refreshFailed', { msg: e.message }), 'error');
  }
}

function renderHookManager() {
  const tableDiv = document.getElementById('hook-manager-table');
  if (!tableDiv) return;
  if (!currentHooks.length) {
    tableDiv.innerHTML = '<p class="muted">' + I18N.t('hooks.noHooks') + '</p>';
    return;
  }
  let html = '<table class="plugin-table"><thead><tr><th>Name</th><th>Version</th><th>Plugin</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
  for (const h of currentHooks) {
    const status = getHookStatus(h);
    const hasError = !!h.error;
    const errorTitle = hasError ? ` title="${escapeHtml(h.error)}"` : '';
    const enableDisabled = hasError || h.enabled ? ' disabled' : '';
    const action = h.enabled
      ? `<button class="btn btn-danger" style="padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="promptDisableHook('${h.name}', '${escapeHtml(h.display_name || h.name)}')">${I18N.t('common.disable')}</button>`
      : `<button class="btn btn-primary" style="padding:0.3rem 0.6rem;font-size:0.8rem;"${enableDisabled} onclick="promptEnableHook('${h.name}', '${escapeHtml(h.display_name || h.name)}')">${I18N.t('common.enable')}</button>`;
    const editDisabled = hasError ? ' disabled' : '';
    const canEdit = h.config_schema;
    html += `<tr${errorTitle}>
      <td data-label="Name">${escapeHtml(h.display_name || h.name)}${hasError ? ' <span class="status-error-indicator" title="' + escapeHtml(h.error) + '">⚠️</span>' : ''}</td>
      <td data-label="Version">${h.version || '-'}</td>
      <td data-label="Plugin">${h.plugin || '-'}</td>
      <td data-label="Status"><span class="plugin-status ${status.cls}">${status.label}</span></td>
      <td data-label="Actions">${action}${canEdit ? ` <button class="btn btn-secondary" style="padding:0.3rem 0.6rem;font-size:0.8rem;"${editDisabled} onclick="openInlineHookConfig('${h.name}', '${escapeHtml(h.display_name || h.name)}')">Edit Config</button>` : ''}</td>
    </tr>`;
    if (hasError) {
      html += `<tr class="error-detail-row"><td colspan="5"><span class="error-detail">${escapeHtml(h.error)}</span></td></tr>`;
    }
  }
  html += '</tbody></table>';
  tableDiv.innerHTML = html;
}

async function promptEnableHook(name, displayName) {
  const confirmed = await showConfirmDialog(
    I18N.t('hooks.enableTitle'),
    I18N.t('hooks.enableConfirm', { name: displayName || name }),
    I18N.t('common.enable'),
    'btn-primary'
  );
  if (!confirmed) return;
  try {
    await postJSON(`/hooks/${name}/enable`, {});
    showToast(I18N.t('hooks.enabledToast', { name: displayName || name }), 'success');
    log(`Hook ${name} enabled (restart required)`);
    await loadHooks();
  } catch (e) {
    const msg = I18N.t('hooks.enableFailed', { name: displayName || name, msg: e.message });
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

async function promptDisableHook(name, displayName) {
  const confirmed = await showConfirmDialog(
    I18N.t('hooks.disableTitle'),
    I18N.t('hooks.disableConfirm', { name: displayName || name }),
    I18N.t('common.disable'),
    'btn-danger'
  );
  if (!confirmed) return;
  try {
    await postJSON(`/hooks/${name}/disable`, {});
    showToast(I18N.t('hooks.disabledToast', { name: displayName || name }), 'info');
    log(`Hook ${name} disabled (restart required)`);
    await loadHooks();
  } catch (e) {
    const msg = I18N.t('hooks.disableFailed', { name: displayName || name, msg: e.message });
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

/* ─── Hook Nav ─── */

function openInlineHookConfig(hookName, displayName) {
  _hideAllEditors();
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelector('.nav-item[data-view="hooks"]')?.classList.add('active');
  hookEditor.openInline(hookName, displayName);
}

function closeInlineHookConfig() {
  hookEditor.closeInline();
}

/* ─── Hook Config Editor ─── */

class HookConfigEditor {
  constructor() {
    this.hookName = null;
    this.displayName = null;
    this.config = {};
    this.schema = null;
    this.original = {};
    this.errors = new Map();
    this.searchQuery = '';
    this.sidebar = document.getElementById('hooks-config-sidebar');
    this.content = document.getElementById('hooks-config-content');
    this.searchInput = document.getElementById('hooks-config-search');
    this.saveBtn = document.getElementById('hooks-config-save');
    this.activeCategory = null;
    this.hasSchema = false;
    this._advancedMode = localStorage.getItem('hook_config_advanced_mode') === 'true';
  }

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

  async openInline(hookName, displayName) {
    this.hookName = hookName;
    this.displayName = displayName || hookName;
    this.searchQuery = '';
    this.searchInput.value = '';
    this.errors.clear();

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

  onInlineSearch(query) {
    this.searchQuery = query.toLowerCase();
    this.renderContent();
  }

  isDirty() {
    return JSON.stringify(this.config) !== JSON.stringify(this.original);
  }

  _updateSaveButton() {
    const btn = document.getElementById('hooks-config-save');
    if (!btn) return;
    const dirty = this.isDirty();
    btn.disabled = !dirty;
    btn.style.opacity = dirty ? '1' : '0.5';
    btn.style.cursor = dirty ? 'pointer' : 'not-allowed';
  }

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

  _detachInputListeners() {
    if (!this._inputHandler) return;
    this.content.removeEventListener('input', this._inputHandler);
    this.content.removeEventListener('change', this._inputHandler);
    this._inputHandler = null;
    if (this._inputTimer) { clearTimeout(this._inputTimer); this._inputTimer = null; }
  }

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

  _hideInline() {
    document.getElementById('hooks-config-section').classList.add('hidden');
    document.getElementById('hook-list-section').classList.remove('hidden');
    document.getElementById('hook-review-modal').classList.add('hidden');
    document.querySelector('.nav-item[data-view="hooks"]')?.classList.add('active');
  }

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

  render() {
    this.renderSidebar();
    this.renderContent();
    this.setupScrollSpy();
  }

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

  categoryMatchesSearch(cat, fields) {
    const q = this.searchQuery;
    if (cat.toLowerCase().includes(q)) return true;
    return fields.some(f => this.fieldMatchesSearch(f));
  }

  fieldMatchesSearch(field) {
    const q = this.searchQuery;
    const label = (field.label || field.key || '').toLowerCase();
    const help = (field.help || '').toLowerCase();
    return label.includes(q) || help.includes(q);
  }

  onSearch(q) {
    this.searchQuery = q.trim().toLowerCase();
    this.render();
  }

  getConfigValue(path) {
    const keys = path.split('.');
    let target = this.config;
    for (let i = 0; i < keys.length - 1; i++) {
      if (target === undefined || target === null) return undefined;
      target = target[keys[i]];
    }
    return target !== undefined && target !== null ? target[keys[keys.length - 1]] : undefined;
  }

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

  removeArrayItem(path, index) {
    const arr = this.getConfigValue(path) || [];
    arr.splice(index, 1);
    this.setConfigValue(path, arr);
    this.render();
  }

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

  removeTagByIndex(path, idx) {
    const arr = this.getConfigValue(path) || [];
    if (idx >= 0 && idx < arr.length) { arr.splice(idx, 1); this.setConfigValue(path, arr); this.render(); }
  }

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

  parseRawJson() {
    const raw = document.getElementById('hook-raw-json').value;
    try {
      this.config = JSON.parse(raw);
      this.errors.clear();
      this.showToast(I18N.t('editor.jsonValid'), 'info');
    } catch (e) {
      this.showToast(I18N.t('editor.jsonInvalid', { msg: e.message }), 'error');
    }
  }

  findFieldByPath(path) {
    if (!this.schema || !this.schema.fields) return null;
    return this.schema.fields.find(f => f.key === path) || null;
  }

  collect() {
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
        try { this.setConfigValue(path, JSON.parse(el.value)); } catch (e) {}
      } else {
        this.setConfigValue(path, el.value);
      }
    });
  }

  validate() {
    this.errors.clear();
    if (!this.hasSchema) {
      try { JSON.stringify(this.config); return true; }
      catch (e) { this.showToast(I18N.t('hooks.invalidJson'), 'error'); return false; }
    }
    let ok = true;
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

  fieldHasError(path) {
    for (const [epath, _] of this.errors) {
      if (epath === path || epath.startsWith(path + '.')) return true;
    }
    return false;
  }

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

  hideReview() {
    document.getElementById('hook-review-modal').classList.add('hidden');
  }

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

  scrollTo(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (id.startsWith('hook_cat_')) {
      this.activeCategory = id.substring(9).replace(/_/g, ' ');
      this.renderSidebar();
    }
  }

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

  showToast(msg, type) {
    const c = document.getElementById('toast-container');
    const t = document.createElement('div');
    t.className = 'toast ' + type;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.remove(), 4000);
  }
}

const hookEditor = new HookConfigEditor();

async function promptShutdown() {
  const confirmed = await showConfirmDialog(
    I18N.t('dialog.shutdownTitle'),
    I18N.t('dialog.shutdownMessage'),
    I18N.t('dialog.shutdown'),
    'btn-danger'
  );
  if (!confirmed) return;
  startLocalShutdownCountdown();
}

function openConfigEditor() {
  // Ensure currentConfig is loaded before opening
  if (currentConfig && Object.keys(currentConfig).length > 0) {
    editor.open(currentConfig);
  } else {
    // Reload config first
    fetchJSON('/config').then(data => {
      currentConfig = data.config || {};
      editor.open(currentConfig);
    }).catch(() => {
      editor.open(currentConfig); // open with whatever we have
    });
  }
}

async function loadConfig() {
  try {
    const data = await fetchJSON('/config');
    currentConfig = data.config || {};
  } catch (e) {
    log('Config load failed: ' + e.message, 'err');
    return;
  }
  const el = document.getElementById('config-summary');
  if (!el) return;
  const tiktok = currentConfig.tiktok || {};
  const rcon = currentConfig.rcon || {};
  el.innerHTML = `
    <div class="field-row"><span>${I18N.t('wizard.tiktokUserLabel')}</span><span>${escapeHtml(tiktok.user || '—')}</span></div>
    <div class="field-row"><span>${I18N.t('config.serverHost')}</span><span>${escapeHtml(currentConfig.server_host || '—')}</span></div>
    <div class="field-row"><span>${I18N.t('config.rconEnabled')}</span><span>${rcon.enabled ? I18N.t('common.yes') : I18N.t('common.no')}</span></div>
    <div class="field-row"><span>${I18N.t('config.controlMethod')}</span><span>${escapeHtml(currentConfig.control_method || '—')}</span></div>`;
}

/* ─── Wizard (preserved) ─── */
function isFirstRun(cfg) {
  const tiktok = cfg.tiktok || {};
  const rcon = cfg.rcon || {};
  return tiktok.user === 'your_tiktok_username' || !rcon.password;
}
function showWizard() {
  document.getElementById('wizard').classList.remove('hidden');
  document.getElementById('dashboard').classList.add('hidden');
  const rawTiktokUser = (currentConfig.tiktok || {}).user || '';
  const rawRconPassword = (currentConfig.rcon || {}).password || '';
  const tiktokOk = rawTiktokUser && rawTiktokUser !== 'your_tiktok_username';
  const rconOk = !!rawRconPassword;
  // Skip already-configured steps
  wizardStep = tiktokOk ? 1 : 0;
  wizardData = {
    tiktok_user: tiktokOk ? rawTiktokUser : '',
    rcon_password: rconOk ? rawRconPassword : '',
  };
  renderWizardStep();
}
function hideWizard() {
  document.getElementById('wizard').classList.add('hidden');
  document.getElementById('dashboard').classList.remove('hidden');
}
let _restartPending = false;

function showRestartDialog(title, message) {
  const card = document.querySelector('#restart-dialog .wizard-card');
  card.innerHTML = `
    <h2 style="border:none;padding:0;">${escapeHtml(title || I18N.t('wizard.restartRequired'))}</h2>
    <p class="muted" style="margin-bottom:1.5rem;">${escapeHtml(message || I18N.t('wizard.restartMessage'))}</p>
    <div style="display:flex;gap:1rem;justify-content:center;">
      <button class="btn btn-primary" id="btn-restart-now">${I18N.t('restart.now')}</button>
      <button class="btn btn-secondary" id="btn-restart-later">${I18N.t('restart.later')}</button>
    </div>
  `;
  // Re-attach listeners since we replaced the innerHTML
  document.getElementById('btn-restart-now').addEventListener('click', triggerRestart);
  document.getElementById('btn-restart-later').addEventListener('click', () => { hideRestartDialog(); loadConfig(); });
  document.getElementById('wizard').classList.add('hidden');
  document.getElementById('restart-dialog').classList.remove('hidden');
}
function hideRestartDialog() {
  document.getElementById('restart-dialog').classList.add('hidden');
  document.getElementById('wizard').classList.add('hidden');
  document.getElementById('dashboard').classList.remove('hidden');
  updateRestartBanner();
}

function updateRestartBanner() {
  const banner = document.getElementById('restart-pending-banner');
  if (banner) {
    banner.classList.toggle('hidden', !_restartPending);
  }
}
function renderWizardStep() {
  const steps = document.getElementById('wizard-steps');
  const content = document.getElementById('wizard-content');
  const backBtn = document.getElementById('wizard-back');
  const nextBtn = document.getElementById('wizard-next');
  // Only 2 configurable steps + review: tiktok, rcon, review
  const totalSteps = 3;
  steps.innerHTML = [0, 1, 2].map(i => `<div class="step-dot ${i === wizardStep ? 'active' : i < wizardStep ? 'done' : ''}"></div>`).join('');
  backBtn.disabled = wizardStep === 0;
  backBtn.style.visibility = wizardStep === 0 ? 'hidden' : 'visible';
  nextBtn.textContent = wizardStep === 2 ? I18N.t('wizard.save') : I18N.t('wizard.next');
  if (wizardStep === 0) {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">${I18N.t('wizard.step0Hint')}</p>
      <div class="form-group"><label>${I18N.t('wizard.tiktokUser')}</label>
      <input type="text" id="w-tiktok-user" value="${escapeHtml(wizardData.tiktok_user)}" placeholder="${I18N.t('wizard.tiktokUserPlaceholder')}">
      <div class="inline-error" id="err-tiktok-user">${I18N.t('wizard.tiktokUserError')}</div>
      <div class="hint">${I18N.t('wizard.tiktokUserHint')}</div></div>`;
  } else if (wizardStep === 1) {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">${I18N.t('wizard.step1Hint')}</p>
      <div class="form-group"><label>${I18N.t('wizard.rconPassword')} <span style="color:var(--color-danger);">*</span></label>
      <input type="password" id="w-rcon-password" value="${escapeHtml(wizardData.rcon_password)}" placeholder="${I18N.t('wizard.passwordPlaceholder')}" oninput="updatePasswordMeter()">
      <div class="inline-error" id="err-rcon-password">${I18N.t('wizard.passwordError')}</div>
      <div class="strength-meter"><div class="strength-segment"></div><div class="strength-segment"></div><div class="strength-segment"></div></div>
      <div class="strength-label" id="strength-label">${I18N.t('wizard.strengthEnter')}</div>
      <div class="hint">${I18N.t('wizard.strengthHint')}</div></div>`;
    setTimeout(updatePasswordMeter, 0);
  } else {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">${I18N.t('wizard.step2Hint')}</p>
      <div style="background:var(--input-bg);padding:1rem;border-radius:8px;margin-bottom:1rem;">
      <div class="field-row"><span>${I18N.t('wizard.tiktokUserLabel')}</span><span>${escapeHtml(wizardData.tiktok_user || '—')}</span></div>
      <div class="field-row"><span>${I18N.t('wizard.rconPasswordLabel')}</span><span>${wizardData.rcon_password ? '********' : I18N.t('common.notSet')}</span></div></div>
      <p class="muted" style="font-size:0.85rem;margin:0;">${I18N.t('wizard.pluginsDisabledHint')}</p>`;
  }
}
function validatePassword(pass) {
  const issues = [];
  if (pass.length < 8) issues.push(I18N.t('pass.minLength'));
  if (!/[A-Z]/.test(pass)) issues.push(I18N.t('pass.upper'));
  if (!/[a-z]/.test(pass)) issues.push(I18N.t('pass.lower'));
  if (!/[0-9]/.test(pass)) issues.push(I18N.t('pass.number'));
  if (!/[^A-Za-z0-9]/.test(pass)) issues.push(I18N.t('pass.special'));
  return issues;
}
function getPasswordStrength(pass) {
  let score = 0;
  if (pass.length >= 8) score++;
  if (pass.length >= 12) score++;
  if (/[A-Z]/.test(pass)) score++;
  if (/[a-z]/.test(pass)) score++;
  if (/[0-9]/.test(pass)) score++;
  if (/[^A-Za-z0-9]/.test(pass)) score++;
  if (score <= 2) return 'weak';
  if (score <= 4) return 'medium';
  return 'strong';
}
function updatePasswordMeter() {
  const pass = document.getElementById('w-rcon-password').value;
  const strength = getPasswordStrength(pass);
  const segments = document.querySelectorAll('.strength-segment');
  const label = document.getElementById('strength-label');
  segments.forEach(s => s.className = 'strength-segment');
  if (pass.length > 0) {
    if (strength === 'weak') { segments[0].classList.add('weak'); label.textContent = I18N.t('wizard.weak'); label.style.color = 'var(--danger)'; }
    else if (strength === 'medium') { segments[0].classList.add('medium'); segments[1].classList.add('medium'); label.textContent = I18N.t('wizard.medium'); label.style.color = 'var(--warning)'; }
    else { segments.forEach(s => s.classList.add('strong')); label.textContent = I18N.t('wizard.strong'); label.style.color = 'var(--success)'; }
  } else { label.textContent = I18N.t('wizard.strengthEnter'); label.style.color = 'var(--text-secondary)'; }
}
async function wizardNext() {
  document.querySelectorAll('.inline-error').forEach(el => el.classList.remove('visible'));
  document.querySelectorAll('input').forEach(el => el.classList.remove('invalid'));
  if (wizardStep === 0) {
    const userInput = document.getElementById('w-tiktok-user');
    const user = userInput.value.trim();
    if (!user || user.toLowerCase() === 'your_tiktok_username') {
      userInput.classList.add('invalid');
      document.getElementById('err-tiktok-user').classList.add('visible');
      return;
    }
    wizardData.tiktok_user = user;
  } else if (wizardStep === 1) {
    const passInput = document.getElementById('w-rcon-password');
    const pass = passInput.value.trim();
    if (!pass) {
      passInput.classList.add('invalid');
      document.getElementById('err-rcon-password').classList.add('visible');
      return;
    }
    wizardData.rcon_password = pass;
  }
  if (wizardStep === 2) { await wizardSave(); return; }
  wizardStep++;
  renderWizardStep();
}

async function wizardSave() {
  const nextBtn = document.getElementById('wizard-next');
  nextBtn.disabled = true;
  nextBtn.textContent = I18N.t('wizard.saving');
  try {
    const cfgData = await fetchJSON('/config');
    const cfg = cfgData.config || {};
    if (!cfg.tiktok) cfg.tiktok = {};
    cfg.tiktok.user = wizardData.tiktok_user;
    if (!cfg.rcon) cfg.rcon = {};
    if (wizardData.rcon_password && wizardData.rcon_password !== '__REDACTED__') {
      cfg.rcon.password = wizardData.rcon_password;
    }
    cfg.rcon.enabled = true;
    await putJSON('/config', { config: cfg, backup: true });
    await postJSON('/reload', {});
    if (cfg.rcon && cfg.rcon.password) {
      await postJSON('/server/restart', {});
      log('Setup saved and Minecraft Server restart requested.');
    } else {
      log('Setup saved and applied.');
    }
    hideWizard();
    await loadConfig();
    showToast(I18N.t('wizard.setupComplete'), 'success');
  } catch (e) {
    log('Failed to save setup: ' + e.message, 'err');
    showToast(I18N.t('wizard.saveFailed', { msg: e.message }), 'error');
  } finally { nextBtn.disabled = false; nextBtn.textContent = I18N.t('wizard.save'); }
}
function _showRestartOverlay() {
  _stopDashboardPolling();
  if (_sseSource) { _sseSource.close(); _sseSource = null; }
  const card = document.querySelector('#restart-dialog .wizard-card');
  if (card) {
    card.innerHTML = '<h2 style="border:none;padding:0;">' + I18N.t('wizard.restarting') + '</h2><p class="muted">' + I18N.t('wizard.restartWait') + '</p>';
  }
  document.getElementById('restart-dialog').classList.remove('hidden');
}

async function triggerRestart() {
  _restartPending = true;
  updateRestartBanner();
  try {
    const res = await fetch(API + '/restart', { method: 'POST', headers: _withApiKey({}) });
    if (res.ok) {
      _showRestartOverlay();
      // The supervisor keeps the API server alive and publishes
      // server.restarting / server.started events via SSE.  If the
      // browser misses the events, fall back to a timeout.
      _waitForRestartCompletion();
    } else {
      _restartPending = false;
      updateRestartBanner();
      showToast(I18N.t('wizard.restartSignalFailed'), 'error');
      document.getElementById('restart-dialog').classList.add('hidden');
    }
  } catch (e) {
    _restartPending = false;
    updateRestartBanner();
    showToast(I18N.t('wizard.restartSignalFailed'), 'error');
    document.getElementById('restart-dialog').classList.add('hidden');
  }
}

function _waitForRestartCompletion(timeoutMs = 90000) {
  const start = Date.now();
  const timer = setInterval(() => {
    if (!_restartPending) {
      clearInterval(timer);
      return;
    }
    if (Date.now() - start > timeoutMs) {
      clearInterval(timer);
      _restartPending = false;
      updateRestartBanner();
      const card = document.querySelector('#restart-dialog .wizard-card');
      if (card) {
        card.innerHTML =
          '<h2 style="border:none;padding:0;">Restart Timed Out</h2>' +
          '<p class="muted">The tool did not report restart completion within 90 seconds. Please close and reopen the GUI manually.</p>';
      }
    }
  }, 1000);
}
function dismissRestartBanner() {
  _restartPending = false;
  updateRestartBanner();
}
function setRestartPending(pending) {
  _restartPending = pending;
  updateRestartBanner();
}
document.getElementById('wizard-back').addEventListener('click', () => { if (wizardStep > 0) { wizardStep--; renderWizardStep(); } });
document.getElementById('wizard-next').addEventListener('click', wizardNext);

/* ─── Config Editor ─── */

const SECTION_ORDER = [
  'tiktok','rcon','server_host','control_method',
  'api','java','mc_version','minecraft_server_api',
  'console','overlay','theme',
  'update','shutdown','auto_update_config','show_sudo_warning','gui',
  'plugin_sandbox',
  'port_policy','api_key',
  'outbound',
  'like_triggers'
];

const CATEGORIES = {
  'Connection': ['tiktok','rcon','server_host','control_method','api'],
  'Minecraft': ['java','mc_version','minecraft_server_api'],
  'System': ['console','overlay','theme','update','shutdown','auto_update_config','show_sudo_warning','gui','plugin_sandbox','port_policy','api_key'],
  'Integration': ['outbound'],
  'Chat & Commands': ['like_triggers']
};

const SECTION_META = {
  tiktok: { title: 'TikTok Live', desc: 'Connect the tool to your TikTok live stream. Set your username and connection behavior.', category: 'Connection' },
  rcon: { title: 'Remote Console (RCON)', desc: 'RCON allows the tool to send commands to your Minecraft server. Keep this enabled.', category: 'Connection' },
  api: { title: 'API Server', desc: 'Configuration for the central API server that powers the dashboard and internal communication.', category: 'Connection' },
  java: { title: 'Minecraft Server', desc: 'Controls how much RAM the Minecraft server uses and which port it runs on.', category: 'Minecraft' },
  mc_version: { title: 'Minecraft Version', desc: 'The Minecraft version the server runs on. Used for version-aware features.', category: 'Minecraft' },
  random_triggers: { title: 'Random Trigger Filter', desc: 'Controls which triggers can be selected by the $random action in data/actions.mca.', category: 'Chat & Commands' },
  like_triggers: { title: 'Like Triggers', desc: 'Fire actions when total stream likes reach a threshold. Each trigger activates at a defined interval and runs a command from actions.mca.', category: 'Chat & Commands' },
  console: { title: 'Console Visibility', desc: 'Controls which windows and processes are shown when the tool starts.', category: 'System' },
  minecraft_server_api: { title: 'Minecraft Server API', desc: 'Handles communication between the tool and the Minecraft server. Required for player death/respawn detection.', category: 'Minecraft' },
  gui: { title: 'Dashboard', desc: 'The graphical user interface is served by the central API server and shown in a window.', category: 'System' },
  overlay: { title: 'Overlay Text', desc: 'Overlay subsystem for displaying text messages on stream.', category: 'System' },
  theme: { title: 'Overlay Colors', desc: 'Customize colors for overlays. All values are CSS hex codes like #ff0000.', category: 'System' },
  update: { title: 'Auto-Updater', desc: 'Checks for new versions on startup and installs them automatically. Strongly recommended.', category: 'System' },
  shutdown: { title: 'Auto-Shutdown', desc: 'Automatically shuts down the tool after your live stream ends.', category: 'System' },
  server_host: { title: 'Server Address', desc: 'Controls which network interfaces the tool listens on.', category: 'Connection' },
  control_method: { title: 'Control Method', desc: 'How the tool communicates with your streaming software.', category: 'Connection' },
  auto_update_config: { title: 'Auto-Update Config', desc: 'Automatically merge new options when the tool updates.', category: 'System' },
  show_sudo_warning: { title: 'Sudo Warning', desc: 'Linux only. Warns if running without sudo, which can cause permission issues.', category: 'System' },
  port_policy: { title: 'Port Policy', desc: 'Controls what happens when a required port is already in use. Can auto-resolve to the next free port.', category: 'System' },
  api_key: { title: 'API Key', desc: 'Optional API key for authentication when the server is exposed beyond localhost.', category: 'System' },
  plugin_sandbox: { title: 'Plugin Sandbox', desc: 'Restricts plugin subprocess resources to limit the impact of misbehaving or compromised plugins.', category: 'System' },
  outbound: { title: 'Outbound Webhooks', desc: 'Send stream events to external services in real time — e.g. announce every gift, follow or subscriber automatically in your Discord server. Add a channel, paste its webhook URL, pick the events and switch it on.', category: 'Integration' },
};

const SECTION_META_DE = {
  tiktok: { title: 'TikTok Live', desc: 'Verbinde das Tool mit deinem TikTok-Live-Stream. Lege deinen Benutzernamen und das Verbindungsverhalten fest.' },
  rcon: { title: 'Remote Console (RCON)', desc: 'RCON erlaubt dem Tool, Befehle an deinen Minecraft-Server zu senden. Lasse diese Option aktiviert.' },
  api: { title: 'API-Server', desc: 'Konfiguration des zentralen API-Servers, der das Dashboard und die interne Kommunikation antreibt.' },
  java: { title: 'Minecraft-Server', desc: 'Steuert, wie viel RAM der Minecraft-Server verwendet und auf welchem Port er läuft.' },
  mc_version: { title: 'Minecraft-Version', desc: 'Die Minecraft-Version, auf der der Server läuft. Wird für versionsabhängige Funktionen verwendet.' },
  random_triggers: { title: 'Zufalls-Trigger-Filter', desc: 'Steuert, welche Trigger für die $random-Aktion in data/actions.mca ausgewählt werden können.' },
  like_triggers: { title: 'Like-Trigger', desc: 'Lösen Aktionen aus, wenn die Gesamtzahl der Stream-Likes einen Schwellenwert erreicht. Jeder Trigger wird bei einem definierten Intervall aktiviert und führt einen Befehl aus actions.mca aus.' },
  console: { title: 'Konsolen-Sichtbarkeit', desc: 'Steuert, welche Fenster und Prozesse beim Start des Tools angezeigt werden.' },
  minecraft_server_api: { title: 'Minecraft-Server-API', desc: 'Übernimmt die Kommunikation zwischen dem Tool und dem Minecraft-Server. Erforderlich für die Spieler-Tod-/Wiederbelebungs-Erkennung.' },
  gui: { title: 'Dashboard', desc: 'Die grafische Benutzeroberfläche wird vom zentralen API-Server bereitgestellt und in einem Fenster angezeigt.' },
  overlay: { title: 'Overlay-Text', desc: 'Overlay-Subsystem zur Anzeige von Textnachrichten im Stream.' },
  theme: { title: 'Overlay-Farben', desc: 'Passe die Farben für Overlays an. Alle Werte sind CSS-Hex-Codes wie #ff0000.' },
  update: { title: 'Auto-Updater', desc: 'Überprüft beim Start auf neue Versionen und installiert sie automatisch. Dringend empfohlen.' },
  shutdown: { title: 'Auto-Herunterfahren', desc: 'Fährt das Tool automatisch herunter, nachdem dein Live-Stream endet.' },
  server_host: { title: 'Server-Adresse', desc: 'Steuert, an welchen Netzwerkschnittstellen das Tool lauscht.' },
  control_method: { title: 'Steuerungsmethode', desc: 'Wie das Tool mit deiner Streaming-Software kommuniziert.' },
  auto_update_config: { title: 'Auto-Konfigurations-Update', desc: 'Fügt beim Tool-Update automatisch neue Optionen hinzu, ohne deine Werte zu überschreiben.' },
  show_sudo_warning: { title: 'Sudo-Warnung', desc: 'Nur Linux. Warnt, wenn du ohne sudo läufst, was Berechtigungsprobleme verursachen kann.' },
  port_policy: { title: 'Port-Richtlinie', desc: 'Steuert, was passiert, wenn ein benötigter Port bereits belegt ist. Kann automatisch zum nächsten freien Port wechseln.' },
  api_key: { title: 'API-Schlüssel', desc: 'Optionaler API-Schlüssel für die Authentifizierung, wenn der Server über localhost hinaus erreichbar ist.' },
  plugin_sandbox: { title: 'Plugin-Sandbox', desc: 'Beschränkt Ressourcen von Plugin-Subprozessen, um die Auswirkungen fehlerhafter oder kompromittierter Plugins zu begrenzen.' },
  outbound: { title: 'Outbound-Webhooks', desc: 'Sendet Live-Events in Echtzeit an externe Dienste — z. B. automatisch jedes Geschenk, jeden Follow oder Subscriber in deinem Discord-Server ankündigen. Channel hinzufügen, Webhook-URL einfügen, Events wählen und einschalten.' },
};

const CATEGORY_LABELS_DE = {
  'Connection': 'Verbindung',
  'Minecraft': 'Minecraft',
  'System': 'System',
  'Integration': 'Integration',
  'Chat & Commands': 'Chat & Befehle',
};

const HELP_TEXT = {
  'auto_update_config': 'When enabled (recommended), new configuration options introduced by updates are automatically merged into your existing config.yaml. Your existing values are preserved.',
  'show_sudo_warning': 'On Linux, running without sudo can cause update and permission issues. Set to false only if you have configured your system to handle permissions properly without sudo.',
  'server_host': 'Controls which network interfaces the servers listen on. "127.0.0.1" means local access only (default, safe). "0.0.0.0" allows access from other devices on your network. The central API always runs on port 29185.',
  'control_method': 'How the tool communicates with your streaming software. DCS (Direct Control System) is recommended for OBS Studio, vMix, and Streamlabs Desktop. ICS (Interface Control System) is required for TikTok Live Studio and Twitch Studio.',
  'shutdown.enabled': 'When enabled, the tool shuts down automatically after your live stream ends.',
  'shutdown.delay_seconds': 'Seconds to wait before shutting down. A countdown gives you time to cancel by typing "stop" in the console.',
  'java.xms': "Initial RAM allocation for the Minecraft server. 'G' = Gigabytes. Using the same value for xms and xmx is recommended. Default is 4G. Reduce to 2G or 1G if your system has less than 8 GB RAM. Low RAM may cause lag or crashes.",
  'java.xmx': "Maximum RAM allocation. Should match xms for stable performance. 'G' = Gigabytes.",
  'java.port': 'Minecraft server port. Default: 25565. Only change if you changed it in server.properties.',
  'rcon.enabled': 'RCON allows the tool to send commands to your Minecraft server. IMPORTANT: Keep this enabled — disabling it breaks most functionality.',
  'rcon.password': 'Set a secure password. The tool will ask you to set one on first start if this is left empty.',
  'rcon.port': 'RCON port. Default: 25575. Only change if you changed it in server.properties.',
  'rcon.http_command_api': 'Direct command endpoint (POST /api/v1/rcon/command) used by the dashboard Console tab. Disabled by default for security and stability — direct commands bypass the bridge\'s RCON queue and throttling. Enable only if you use the console or extensions need it; trigger actions keep working via the queue either way.',
  'tiktok.user': 'Your TikTok username — without the @ symbol. This is required for the tool to connect to your live stream.',
  'tiktok.reconnect_delay_seconds': 'Seconds to wait before attempting to reconnect after a connection loss.',
  'tiktok.autosave_interval_seconds': 'How often (in seconds) the gift revenue log file is saved to disk. The log is stored at data/gift_revenue_log.jsonl.',
  'tiktok.follow_tracking.mode': 'all_time tracks follows across ALL streams. Once a user is recorded, their future follows are ignored even after restarting. per_stream resets the list every time the tool starts.',
  'tiktok.follow_tracking.file': 'Path to the file storing tracked follower names. Default: data/followed_users.txt.',
  'random_triggers.mode': 'deny-all means ONLY triggers in the list are eligible for $random. allow-all means ALL triggers are eligible EXCEPT those in the list.',
  'random_triggers.triggers': 'List of trigger names. Which ones are used depends on the mode. Triggers containing "$random" are automatically excluded to prevent infinite recursion.',
  'like_triggers': 'Like triggers let you automatically run a command every time your stream reaches a certain number of likes. For example: set one to fire every 100 likes so viewers see a reward as the like count grows. Each trigger connects to a command you write in the Actions Editor (data/actions.mca).',
  'like_triggers[].id': 'A short name just for you — so you can tell triggers apart in logs. Example: "likes_100" or "big_milestone".',
  'like_triggers[].every': 'How many likes between each activation. Example: 100 means the trigger fires when likes hit 100, then 200, then 300, and so on.',
  'like_triggers[].function': 'The trigger name from your Actions Editor. Write a command for this name there — it will run every time this trigger fires. Example: if you set this to "likes", create a "likes" trigger in actions.mca.',
  'like_triggers[].payload': 'This text replaces {user} in your actions.mca command. For example: setting it to "Community" means {user} becomes "Community". Leave as "Community" if unsure.',
  'like_triggers[].enabled': 'Turn off to pause this trigger without deleting it.',
  'console.log_level': 'Visibility level: 0 = Hide everything, 1 = Silent (hide console, keep GUI), 2 = Standard (recommended), 3 = Advanced, 4 = Debug, 5 = Override (debugging only).',
  'console.visible': 'Show or hide the main console window when the tool starts.',
  'console.allow_close': 'If true, typing "exit" in the console shuts everything down cleanly. If false, the launcher exits immediately after starting programs.',
  'minecraft_server_api.api_port': 'Port for the internal Minecraft API bridge. Default: 29187.',
  'minecraft_server_api.web_server_port': 'Port for the webhook server that receives Minecraft events. Default: 29188.',
  'gui.enabled': 'Launch the graphical dashboard on startup. If disabled, you can still open it manually.',
  'update.enabled': 'Checks for new versions on startup and installs them automatically. It is strongly recommended to keep this enabled.',
  'update.auto_install': 'When enabled, updates are installed automatically on startup. When disabled, you will be notified in the GUI when an update is available and can install it manually from the Updates tab.',
  'update.max_update_logs': 'Maximum number of update log files to keep in logs/update_logs/. 0 = delete all after each update. -1 = keep forever.',
  'overlay.enabled': 'Enable the built-in text overlay subsystem. When disabled, overlay windows will not open and overlay actions in actions.mca will be skipped.',
  'overlay.display_mode': 'overwrite replaces the current message immediately. queue lines up messages and shows them one after another.',
  'overlay.fade_in': 'Fade-in duration in milliseconds. Set to 0 for instant appearance.',
  'overlay.fade_out': 'Fade-out duration in milliseconds. Set to 0 for instant disappearance.',
  'overlay.max_fails': 'Consecutive failed dispatches before the circuit breaker activates and blocks further messages.',
  'overlay.cooldown': 'Seconds to wait after max_fails before allowing new messages again.',
  'overlay.overlays': 'Named overlay slots. Each slot can have its own OBS Browser Source URL. "default" is required and used when no specific overlay is requested.',
  'overlay.theme.background': 'Background colour of the overlay window. Also used as the chroma key colour.',
  'overlay.theme.text': 'Text colour shown in the overlay.',
  'port_policy.auto_resolve': 'When enabled, automatically find the next free port if the default port is already in use. When disabled, logs an error and exits.',
  'port_policy.session_only': 'When enabled, resolved ports are used only for the current session. When disabled, resolved ports are saved permanently to the config.',
  'port_policy.max_offset': 'How many ports to try before giving up. -1 means unlimited.',
  'api_key': 'Optional API key for authentication. When set, all non-localhost requests must include the X-API-Key header. Leave empty to disable authentication.',
  'plugin_sandbox.enabled': 'Enable sandboxing to restrict plugin subprocess resources.',
  'plugin_sandbox.profile': 'Built-in preset: "light" (1 GB RAM, no CPU cap), "moderate" (512 MB, 1 h CPU) or "strict" (256 MB, 15 min CPU). When set, it overrides the raw values below. Individual plugins can override it via "sandbox_profile" in their plugin.json.',
  'plugin_sandbox.max_memory_mb': 'Maximum RAM per plugin process in megabytes.',
  'plugin_sandbox.max_cpu_time': 'Maximum CPU seconds per plugin (Linux only).',
  'plugin_sandbox.max_files': 'Maximum open file descriptors per plugin (Linux only).',
  'plugin_sandbox.max_processes': 'Maximum child processes per plugin (Linux only).',
  'plugin_sandbox.priority_class': 'Windows process priority for plugin subprocesses. below_normal reduces impact on the main tool.',
  'outbound.enabled': 'Master switch for all outbound channels. When disabled, no events are forwarded.',
  'outbound.max_fails': 'Consecutive failed deliveries before a channel\'s circuit breaker activates. Same mechanism as the overlay circuit breaker.',
  'outbound.cooldown': 'Seconds a channel pauses after max_fails failed deliveries. Events arriving during the cooldown are dropped.',
  'outbound.retries': 'Extra delivery attempts per message after the first failure (1 second apart). 0 = send exactly once.',
  'outbound.timeout': 'HTTP timeout in seconds per delivery attempt.',
  'outbound.channels': 'Webhook channels. Each channel POSTs matching events to its URL. Patterns use exact names (tiktok.gift) or wildcards (tiktok.*); * matches everything.'
};

const HELP_TEXT_DE = {
  'auto_update_config': 'Wenn aktiviert (empfohlen), werden neue Konfigurationsoptionen, die durch Updates eingeführt werden, automatisch in deine bestehende config.yaml eingefügt. Deine vorhandenen Werte bleiben erhalten.',
  'show_sudo_warning': 'Unter Linux kann das Ausführen ohne sudo Update- und Berechtigungsprobleme verursachen. Setze dies nur auf false, wenn dein System die Berechtigungen auch ohne sudo korrekt handhabt.',
  'server_host': 'Steuert, an welchen Netzwerkschnittstellen die Server lauschen. „127.0.0.1" bedeutet nur lokaler Zugriff (Standard, sicher). „0.0.0.0" erlaubt Zugriff von anderen Geräten in deinem Netzwerk. Der zentrale API-Server läuft immer auf Port 29185.',
  'control_method': 'Wie das Tool mit deiner Streaming-Software kommuniziert. DCS (Direct Control System) wird für OBS Studio, vMix und Streamlabs Desktop empfohlen. ICS (Interface Control System) ist für TikTok Live Studio und Twitch Studio erforderlich.',
  'shutdown.enabled': 'Wenn aktiviert, fährt sich das Tool automatisch herunter, nachdem dein Live-Stream endet.',
  'shutdown.delay_seconds': 'Sekunden bis zum Herunterfahren. Ein Countdown gibt dir Zeit zum Abbrechen, indem du „stop" in die Konsole tippst.',
  'java.xms': 'Anfängliche RAM-Zuweisung für den Minecraft-Server. „G" = Gigabyte. Es wird empfohlen, für xms und xmx den gleichen Wert zu verwenden. Standard ist 4G. Reduziere auf 2G oder 1G, wenn dein System weniger als 8 GB RAM hat. Zu wenig RAM kann zu Verzögerungen oder Abstürzen führen.',
  'java.xmx': 'Maximale RAM-Zuweisung. Sollte für stabile Leistung xms entsprechen. „G" = Gigabyte.',
  'java.port': 'Minecraft-Server-Port. Standard: 25565. Nur ändern, wenn du ihn in server.properties geändert hast.',
  'rcon.enabled': 'RCON erlaubt dem Tool, Befehle an deinen Minecraft-Server zu senden. WICHTIG: Lasse dies aktiviert — Deaktivieren bricht die meisten Funktionen.',
  'rcon.password': 'Lege ein sicheres Passwort fest. Das Tool fragt dich beim ersten Start danach, wenn dieses Feld leer bleibt.',
  'rcon.port': 'RCON-Port. Standard: 25575. Nur ändern, wenn du ihn in server.properties geändert hast.',
  'rcon.http_command_api': 'Direkter Befehls-Endpunkt (POST /api/v1/rcon/command), den der Konsole-Tab im Dashboard nutzt. Aus Sicherheits- und Stabilitätsgründen standardmäßig deaktiviert — direkte Befehle umgehen die RCON-Queue und das Throttling der Bridge. Aktiviere ihn nur, wenn du die Konsole nutzt oder Erweiterungen ihn brauchen; Trigger-Aktionen funktionieren über die Queue weiterhin.',
  'tiktok.user': 'Dein TikTok-Benutzername — ohne das @-Zeichen. Dies ist erforderlich, damit sich das Tool mit deinem Live-Stream verbinden kann.',
  'tiktok.reconnect_delay_seconds': 'Sekunden, die vor dem erneuten Verbindungsversuch nach einem Verbindungsverlust gewartet werden.',
  'tiktok.autosave_interval_seconds': 'Wie oft (in Sekunden) die Geschenk-Umsatzlog-Datei auf der Festplatte gespeichert wird. Die Log-Datei liegt unter data/gift_revenue_log.jsonl.',
  'tiktok.follow_tracking.mode': 'all_time verfolgt Follower über ALLE Streams hinweg. Sobald ein Nutzer erfasst wurde, werden zukünftige Follows auch nach einem Neustart ignoriert. per_stream setzt die Liste bei jedem Start des Tools zurück.',
  'tiktok.follow_tracking.file': 'Pfad zur Datei, die die verfolgten Followernamen speichert. Standard: data/followed_users.txt.',
  'random_triggers.mode': 'deny-all bedeutet, dass NUR Trigger in der Liste für $random infrage kommen. allow-all bedeutet, dass ALLE Trigger infrage kommen AUSSER den aufgelisteten.',
  'random_triggers.triggers': 'Liste der Triggernamen. Welche verwendet werden, hängt vom Modus ab. Trigger, die „$random" enthalten, werden automatisch ausgeschlossen, um Endlosrekursion zu verhindern.',
  'like_triggers': 'Like-Trigger lassen dich automatisch einen Befehl ausführen, sobald dein Stream eine bestimmte Like-Zahl erreicht. Zum Beispiel: Setze einen Trigger auf 100 Likes, damit Zuschauer eine Belohnung sehen, während die Like-Zahl steigt. Jeder Trigger verbindet sich mit einem Befehl, den du im Aktions-Editor (data/actions.mca) schreibst.',
  'like_triggers[].id': 'Ein kurzer Name nur für dich — damit du in Logs siehst, welcher Trigger ausgelöst wurde. Beispiel: "likes_100" oder "großer_meilenstein".',
  'like_triggers[].every': 'Wie viele Likes zwischen den Auslösungen. Beispiel: 100 löst bei 100, 200, 300 usw. aus.',
  'like_triggers[].function': 'Der Trigger-Name aus deinem Aktions-Editor. Schreibe dort einen Befehl für diesen Namen — er wird bei jeder Auslösung ausgeführt. Beispiel: Wenn du „likes" eingibst, erstelle einen „likes"-Trigger in actions.mca.',
  'like_triggers[].payload': 'Dieser Text ersetzt {user} in deinem actions.mca-Befehl. Beispiel: „Community" bedeutet, {user} wird zu „Community". Lass „Community" stehen, wenn unsicher.',
  'like_triggers[].enabled': 'Deaktiviere, um diesen Trigger zu pausieren, ohne ihn zu löschen.',
  'console.log_level': 'Sichtbarkeitsstufe: 0 = Alles ausblenden, 1 = Still (Konsole ausblenden, GUI behalten), 2 = Standard (empfohlen), 3 = Erweitert, 4 = Debug, 5 = Override (nur zum Debuggen).',
  'console.visible': 'Konsolen-Hauptfenster beim Start des Tools anzeigen oder ausblenden.',
  'console.allow_close': 'Wenn true, fährt die Eingabe von „exit" in der Konsole alles sauber herunter. Wenn false, beendet sich der Launcher sofort nach dem Start der Programme.',
  'minecraft_server_api.api_port': 'Port für die interne Minecraft-API-Brücke. Standard: 29187.',
  'minecraft_server_api.web_server_port': 'Port für den Webhook-Server, der Minecraft-Ereignisse empfängt. Standard: 29188.',
  'gui.enabled': 'Startet das grafische Dashboard beim Programmstart. Wenn deaktiviert, kannst du es trotzdem manuell öffnen.',
  'update.enabled': 'Überprüft beim Start auf neue Versionen und installiert sie automatisch. Es wird dringend empfohlen, dies aktiviert zu lassen.',
  'update.max_update_logs': 'Maximale Anzahl der Update-Logdateien, die in logs/update_logs/ aufbewahrt werden. 0 = nach jedem Update alle löschen. -1 = für immer behalten.',
  'overlay.enabled': 'Aktiviere das eingebaute Text-Overlay-Subsystem. Wenn deaktiviert, werden Overlay-Fenster nicht geöffnet und Overlay-Aktionen in actions.mca übersprungen.',
  'overlay.display_mode': 'overwrite ersetzt die aktuelle Nachricht sofort. queue reiht Nachrichten auf und zeigt sie nacheinander an.',
  'overlay.fade_in': 'Einblenddauer in Millisekunden. 0 für sofortiges Erscheinen.',
  'overlay.fade_out': 'Ausblenddauer in Millisekunden. 0 für sofortiges Verschwinden.',
  'overlay.max_fails': 'Aufeinanderfolgende fehlgeschlagene Zustellungen, bevor der Schutzschalter auslöst und weitere Nachrichten blockiert.',
  'overlay.cooldown': 'Sekunden nach max_fails, bevor neue Nachrichten wieder zugelassen werden.',
  'overlay.overlays': 'Benannte Overlay-Slots. Jeder Slot kann eine eigene OBS-Browser-Source-URL haben. „default" ist erforderlich und wird verwendet, wenn kein bestimmtes Overlay angefordert wird.',
  'overlay.theme.background': 'Hintergrundfarbe des Overlay-Fensters. Wird auch als Chroma-Key-Farbe verwendet.',
  'overlay.theme.text': 'Textfarbe, die im Overlay angezeigt wird.',
  'port_policy.auto_resolve': 'Wenn aktiviert, wird automatisch der nächste freie Port gefunden, falls der Standardport bereits belegt ist. Wenn deaktiviert, wird ein Fehler protokolliert und beendet.',
  'port_policy.session_only': 'Wenn aktiviert, werden aufgelöste Ports nur für die aktuelle Sitzung verwendet. Wenn deaktiviert, werden aufgelöste Ports dauerhaft in der Konfiguration gespeichert.',
  'port_policy.max_offset': 'Wie viele Ports versucht werden, bevor aufgegeben wird. -1 bedeutet unbegrenzt.',
  'api_key': 'Optionaler API-Schlüssel für die Authentifizierung. Wenn gesetzt, müssen alle Nicht-Localhost-Anfragen den X-API-Key-Header enthalten. Lasse leer, um die Authentifizierung zu deaktivieren.',
  'plugin_sandbox.enabled': 'Sandboxing aktivieren, um Ressourcen von Plugin-Subprozessen einzuschränken.',
  'plugin_sandbox.profile': 'Built-in-Profil: "light" (1 GB RAM, kein CPU-Limit), "moderate" (512 MB, 1 h CPU) oder "strict" (256 MB, 15 min CPU). Wenn gesetzt, überschreibt es die Rohwerte unten. Einzelne Plugins können es via "sandbox_profile" in ihrer plugin.json überschreiben.',
  'plugin_sandbox.max_memory_mb': 'Maximaler RAM pro Plugin-Prozess in Megabyte.',
  'plugin_sandbox.max_cpu_time': 'Maximale CPU-Sekunden pro Plugin (nur Linux).',
  'plugin_sandbox.max_files': 'Maximale offene Dateideskriptoren pro Plugin (nur Linux).',
  'plugin_sandbox.max_processes': 'Maximale Kindprozesse pro Plugin (nur Linux).',
  'plugin_sandbox.priority_class': 'Windows-Prozesspriorität für Plugin-Subprozesse. below_normal reduziert die Auswirkungen auf das Haupt-Tool.',
  'outbound.enabled': 'Hauptschalter für alle Outbound-Channels. Wenn deaktiviert, werden keine Events weitergeleitet.',
  'outbound.max_fails': 'Aufeinanderfolgende fehlgeschlagene Zustellungen, bevor der Schutzschalter eines Channels auslöst. Gleicher Mechanismus wie beim Overlay-Schutzschalter.',
  'outbound.cooldown': 'Sekunden, die ein Channel nach max_fails Fehlzustellungen pausiert. Events während der Pause werden verworfen.',
  'outbound.retries': 'Zusätzliche Zustellversuche pro Nachricht nach dem ersten Fehlversuch (jeweils 1 Sekunde Abstand). 0 = genau einmal senden.',
  'outbound.timeout': 'HTTP-Timeout in Sekunden pro Zustellversuch.',
  'outbound.channels': 'Webhook-Channels. Jeder Channel POSTet passende Events an seine URL. Patterns sind exakte Namen (tiktok.gift) oder Wildcards (tiktok.*); * passt auf alles.'
};

const FIELD_META = {
  'config_version': { basic: false, readonly: true, type: 'text' },
  'auto_update_config': { basic: true, type: 'bool' },
  'show_sudo_warning': { basic: false, type: 'bool' },
  'server_host': { basic: false, type: 'text', required: true },
  'control_method': { basic: true, type: 'select', options: ['DCS','ICS'] },
  'shutdown.enabled': { basic: true, type: 'bool' },
  'shutdown.delay_seconds': { basic: true, type: 'number', min: 0, max: 3600 },
  'java.xms': { basic: true, type: 'text', pattern: /^\d+[GgMm]$/ },
  'java.xmx': { basic: true, type: 'text', pattern: /^\d+[GgMm]$/ },
  'java.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'rcon.enabled': { basic: true, type: 'bool' },
  'rcon.password': { basic: true, type: 'password', required: true },
  'rcon.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'rcon.http_command_api': { basic: true, type: 'bool' },
  'tiktok.user': { basic: true, type: 'text', required: true },
  'tiktok.reconnect_delay_seconds': { basic: true, type: 'number', min: 0 },
  'tiktok.autosave_interval_seconds': { basic: true, type: 'number', min: 1 },
  'tiktok.follow_tracking': { basic: true },
  'tiktok.follow_tracking.mode': { basic: true, type: 'select', options: ['all_time','per_stream'] },

  'random_triggers': { basic: true },
  'random_triggers.mode': { basic: true, type: 'select', options: ['deny-all','allow-all'] },
  'console.log_level': { basic: false, type: 'number', min: 0, max: 5 },
  'console.visible': { basic: false, type: 'bool' },
  'console.allow_close': { basic: false, type: 'bool' },
  'minecraft_server_api.api_port': { basic: false, type: 'number', min: 1, max: 65535 },
  'minecraft_server_api.web_server_port': { basic: false, type: 'number', min: 1, max: 65535 },
  'gui.enabled': { basic: true, type: 'bool' },
  'update.enabled': { basic: true, type: 'bool' },
  'update.auto_install': { basic: true, type: 'bool' },
  'update.max_update_logs': { basic: true, type: 'number' },
  'overlay.enabled': { basic: true, type: 'bool' },
  'overlay.display_mode': { basic: true, type: 'select', options: ['overwrite','queue'] },
  'overlay.fade_in': { basic: true, type: 'number', min: 0 },
  'overlay.fade_out': { basic: true, type: 'number', min: 0 },
  'overlay.max_fails': { basic: true, type: 'number', min: 1 },
  'overlay.cooldown': { basic: true, type: 'number', min: 0 },
  'overlay.overlays': { basic: true, type: 'json' },
  'overlay.theme.background': { basic: true, type: 'color' },
  'overlay.theme.text': { basic: true, type: 'color' },
  'theme': { basic: true },
  'api_key': { basic: false, type: 'password' },
  'port_policy.auto_resolve': { basic: false, type: 'bool' },
  'port_policy.session_only': { basic: false, type: 'bool' },
  'port_policy.max_offset': { basic: false, type: 'number', min: -1 },
  'plugin_sandbox.enabled': { basic: false, type: 'bool' },
  'plugin_sandbox.profile': { basic: false, type: 'select', options: ['', 'light', 'moderate', 'strict'] },
  'plugin_sandbox.max_memory_mb': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.max_cpu_time': { basic: false, type: 'number', min: 0 },
  'plugin_sandbox.max_files': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.max_processes': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.priority_class': { basic: false, type: 'select', options: ['below_normal', 'idle'] },

  'like_triggers': { basic: true },
  'like_triggers[].id': { basic: true, type: 'text' },
  'like_triggers[].every': { basic: true, type: 'number', min: 1 },
  'like_triggers[].function': { basic: true, type: 'text' },
  'like_triggers[].payload': { basic: true, type: 'text' },
  'like_triggers[].enabled': { basic: true, type: 'bool' },

  'outbound': { basic: true },
  'outbound.enabled': { basic: true, type: 'bool' },
  'outbound.max_fails': { basic: true, type: 'number', min: 1 },
  'outbound.cooldown': { basic: true, type: 'number', min: 0 },
  'outbound.retries': { basic: true, type: 'number', min: 0 },
  'outbound.timeout': { basic: true, type: 'number', min: 1 },
  'outbound.channels': { basic: true, type: 'list' },
};

function getMeta(path) {
  if (FIELD_META[path]) return FIELD_META[path];
  const p = path.replace(/\.groups\[\d+\]/, '.groups[]').replace(/\.triggers\[\d+\]/, '.triggers[]').replace(/\.overlays\[\d+\]/, '.overlays[]').replace(/\.commands_config\.\w+/, '.commands_config[]').replace(/\.like_triggers\[\d+\]/, '.like_triggers[]');
  return FIELD_META[p] || { basic: false, type: 'text' };
}

function _normalizeEditorPath(path) {
  return path
    .replace(/\.groups\[\d+\]/, '.groups[]')
    .replace(/\.triggers\[\d+\]/, '.triggers[]')
    .replace(/\.overlays\[\d+\]/, '.overlays[]')
    .replace(/\.commands_config\.\w+/, '.commands_config[]')
    .replace(/\.like_triggers\[\d+\]/, '.like_triggers[]');
}

function _editorLangIsDe() {
  return window.I18N && I18N.lang && I18N.lang() === 'de';
}

function getHelp(path) {
  const p = HELP_TEXT[path] ? path : _normalizeEditorPath(path);
  const en = HELP_TEXT[p];
  if (!en) return '';
  if (_editorLangIsDe() && HELP_TEXT_DE[p]) return HELP_TEXT_DE[p];
  return en;
}

function sectionMeta(key) {
  const en = SECTION_META[key] || null;
  if (!_editorLangIsDe() || !en) return en;
  return SECTION_META_DE[key] || en;
}

function categoryLabel(cat) {
  if (_editorLangIsDe() && CATEGORY_LABELS_DE[cat]) return CATEGORY_LABELS_DE[cat];
  return cat;
}

/* ─── Editor Class ─── */
class ConfigEditor {
  constructor() {
    this.data = {};
    this.original = {};
    this.unknownKeys = {};
    this.originalUnknownKeys = {};
    this.searchQuery = '';
    this.errors = new Map();
    this.sidebar = document.getElementById('editor-sidebar');
    this.content = document.getElementById('editor-content');
    this.knownTop = new Set(Object.keys(SECTION_META));
    this.activeSection = null;
    this.originalTypes = {}; // track original types for commands_config etc.
    this._advancedMode = localStorage.getItem('config_advanced_mode') === 'true';
  }

  open(config) {
    this.original = JSON.parse(JSON.stringify(config));
    this.data = JSON.parse(JSON.stringify(config));
    this.unknownKeys = {};
    this.originalUnknownKeys = {};
    this.errors.clear();
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

  isDirty() {
    return JSON.stringify(this.data) !== JSON.stringify(this.original);
  }

  _updateSaveButton() {
    const btn = document.getElementById('config-editor-save');
    if (!btn) return;
    const dirty = this.isDirty();
    btn.disabled = !dirty;
    btn.style.opacity = dirty ? '1' : '0.5';
    btn.style.cursor = dirty ? 'pointer' : 'not-allowed';
  }

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

  _detachInputListeners() {
    if (!this._inputHandler) return;
    this.content.removeEventListener('input', this._inputHandler);
    this.content.removeEventListener('change', this._inputHandler);
    this._inputHandler = null;
    if (this._inputTimer) { clearTimeout(this._inputTimer); this._inputTimer = null; }
  }

  _isFieldAdvanced(path) {
    const meta = getMeta(path);
    return meta.basic === false;
  }

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

  _resetData() {
    this.data = JSON.parse(JSON.stringify(this.original));
    this.unknownKeys = JSON.parse(JSON.stringify(this.originalUnknownKeys));
  }

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

  mergeUnknownKeys() {
    Object.assign(this.data, this.unknownKeys);
  }

  render() {
    this.renderSidebar();
    this.renderContent();
    // Re-attach observer to new section cards after any re-render
    this.setupScrollSpy();
  }

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

  sectionHasError(key) {
    const prefix = key === '_unknown' ? '_unknown' : key;
    for (const [path, err] of this.errors) {
      if (path.startsWith(prefix)) return true;
    }
    return false;
  }

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

  fieldMatchesSearch(path, key) {
    if (!this.searchQuery) return true;
    const q = this.searchQuery.toLowerCase();
    if (path.toLowerCase().includes(q)) return true;
    if (key.toLowerCase().includes(q)) return true;
    if ((getHelp(path) || '').toLowerCase().includes(q)) return true;
    return false;
  }

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

  removeTagByIndex(path, idx) {
    const arr = this.getValue(path) || [];
    if (idx >= 0 && idx < arr.length) { arr.splice(idx, 1); this.setValue(path, arr); this.render(); }
  }

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

  onRoleChange(path, cb) {
    const role = cb.getAttribute('data-role');
    const arr = this.getValue(path) || [];
    if (cb.checked) { if (!arr.includes(role)) arr.push(role); }
    else { const idx = arr.indexOf(role); if (idx > -1) arr.splice(idx, 1); }
    this.setValue(path, arr);
  }

  removeArrayItem(path, index) {
    const arr = this.getValue(path) || [];
    arr.splice(index, 1);
    this.setValue(path, arr);
    this.render();
  }

  onFieldInput() {
    this.collect();
    this._updateSaveButton();
  }

  buildOverlaySlotsEditor(path, slots) {
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const help = getHelp(path);
    const rows = (slots || []).map((slot, i) => {
      const nameId = id + '_name_' + i;
      const urlId = id + '_url_' + i;
      return `<div class="overlay-slot-row">
        <input type="text" id="${nameId}" value="${escapeHtml(slot.name || '')}" placeholder="Slot name" data-path="${path}[${i}].name" data-type="string" oninput="editor.onFieldInput()" style="width:140px;padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.85rem;">
        <input type="text" id="${urlId}" value="${escapeHtml(slot.url || '')}" placeholder="OBS Browser Source URL" data-path="${path}[${i}].url" data-type="string" oninput="editor.onFieldInput()" style="flex:1;padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.85rem;">
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

  addOverlaySlot(path) {
    const arr = this.getValue(path) || [];
    arr.push({ name: '', url: '' });
    this.setValue(path, arr);
    this.render();
  }

  removeOverlaySlot(path, index) {
    const arr = this.getValue(path) || [];
    arr.splice(index, 1);
    this.setValue(path, arr);
    this.render();
  }

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

  buildOverlayEditor(path, overlay) {
    const fields = this.buildObjectFields(path, overlay);
    return fields;
  }

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

  addLikeTrigger(path) {
    const arr = this.getValue(path) || [];
    arr.push({ id: '', every: 100, function: '', payload: 'Community', enabled: true });
    this.setValue(path, arr);
    this.render();
  }

  removeLikeTrigger(path, index) {
    const arr = this.getValue(path) || [];
    if (index >= 0 && index < arr.length) { arr.splice(index, 1); this.setValue(path, arr); this.render(); }
  }

  collectLikeTriggers() {
    const path = 'like_triggers';
    const current = this.getValue(path);
    if (!Array.isArray(current)) return;
    const triggers = [];
    for (let i = 0; i < current.length; i++) {
      const enEl = document.querySelector(`[data-li-enabled="${i}"]`);
      const idEl = document.querySelector(`[data-li-id="${i}"]`);
      const evEl = document.querySelector(`[data-li-every="${i}"]`);
      const fnEl = document.querySelector(`[data-li-function="${i}"]`);
      const plEl = document.querySelector(`[data-li-payload="${i}"]`);
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

  addOutboundChannel(path) {
    const arr = this.getValue(path) || [];
    arr.push({ name: '', url: '', events: ['tiktok.*'], format: 'raw', template: '', enabled: false });
    this.setValue(path, arr);
    this.render();
  }

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

  unknownKeysToYaml() {
    // Very simplified YAML-like serialization for display
    let out = '';
    for (const [k, v] of Object.entries(this.unknownKeys)) {
      out += k + ':\n' + JSON.stringify(v, null, 2).split('\n').map(l => '  ' + l).join('\n') + '\n';
    }
    return out;
  }

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

  onSearch(q) {
    this.searchQuery = q.trim().toLowerCase();
    this.render();
  }

  /* ─── Value helpers ─── */
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
  collect() {
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
        try { this.setValue(path, JSON.parse(el.value)); } catch (e) {}
      } else {
        this.setValue(path, el.value);
      }
    });
    this.collectLikeTriggers();
    this.collectOutboundChannels();
  }

  /* ─── Validation ─── */
  validate() {
    this.errors.clear();
    let ok = true;
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

  hideReview() {
    document.getElementById('review-modal').classList.add('hidden');
  }

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

/* ─── Utilities ─── */
function escapeHtml(text) {
  // Escapes quotes as well — the output is interpolated into quoted HTML
  // attributes and inline onclick JS strings throughout the dashboard.
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
// Sanitizes rendered markdown (e.g. third-party plugin READMEs) before it is
// assigned via innerHTML. The dashboard runs inside a pywebview window with a
// privileged JS bridge, so active content must never survive this path.
function sanitizeMarkdownHtml(html) {
  const doc = new DOMParser().parseFromString(String(html), 'text/html');
  doc.querySelectorAll('script,style,iframe,frame,object,embed,link,meta,form,base')
    .forEach(el => el.remove());
  doc.querySelectorAll('*').forEach(el => {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      const value = attr.value;
      if (name.startsWith('on')) {
        el.removeAttribute(attr.name);
      } else if ((name === 'href' || name === 'src' || name === 'xlink:href' || name === 'action') &&
                 /^\s*(javascript|vbscript|data:text\/html)/i.test(value)) {
        el.removeAttribute(attr.name);
      }
    }
  });
  return doc.body.innerHTML;
}
function toTitle(str) {
  return str.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/* ─── Plugin Config Editor ─── */

class PluginConfigEditor {
  constructor() {
    this.pluginName = null;
    this.displayName = null;
    this.config = {};
    this.schema = null;
    this.original = {};
    this.errors = new Map();
    this.searchQuery = '';
    this.sidebar = document.getElementById('plugin-editor-sidebar');
    this.content = document.getElementById('plugin-editor-content');
    this.searchInput = document.getElementById('plugin-editor-search');
    this.saveBtn = document.getElementById('plugin-editor-save');
    this.activeCategory = null;
    this.hasSchema = false;
    this._inlineMode = false;
    this._advancedMode = localStorage.getItem('plugin_config_advanced_mode') === 'true';
  }

  _swapElements(inline) {
    this._inlineMode = inline;
    if (inline) {
      this._origSidebar = this.sidebar;
      this._origContent = this.content;
      this._origSearchInput = this.searchInput;
      this._origSaveBtn = this.saveBtn;
      this.sidebar = document.getElementById('plugins-config-sidebar');
      this.content = document.getElementById('plugins-config-content');
      this.searchInput = document.getElementById('plugins-config-search');
      this.saveBtn = document.getElementById('plugins-config-save');
    } else {
      this.sidebar = this._origSidebar || document.getElementById('plugin-editor-sidebar');
      this.content = this._origContent || document.getElementById('plugin-editor-content');
      this.searchInput = this._origSearchInput || document.getElementById('plugin-editor-search');
      this.saveBtn = this._origSaveBtn || document.getElementById('plugin-editor-save');
      this._origSidebar = this._origContent = this._origSearchInput = this._origSaveBtn = null;
    }
  }

  async _loadConfig(pluginName) {
    try {
      const [cfgRes, schemaRes] = await Promise.all([
        fetchJSON(`/plugins/${encodeURIComponent(pluginName)}/config`),
        fetchJSON(`/plugins/${encodeURIComponent(pluginName)}/config/schema`)
      ]);
      this.config = JSON.parse(JSON.stringify(cfgRes.config || {}));
      this.original = JSON.parse(JSON.stringify(cfgRes.config || {}));
      this.schema = schemaRes.schema;
      this.hasSchema = !!(this.schema && this.schema.fields && this.schema.fields.length);
    } catch (e) {
      log('Failed to load plugin config: ' + e.message, 'err');
      this.showToast(I18N.t('editor.loadFailed', { msg: e.message }), 'error');
      throw e;
    }
  }

  async open(pluginName, displayName) {
    this._swapElements(false);
    this.pluginName = pluginName;
    this.displayName = displayName || pluginName;
    this.searchQuery = '';
    this.searchInput.value = '';
    this.errors.clear();

    try {
      await this._loadConfig(pluginName);
    } catch (e) {
      return;
    }

    document.getElementById('plugin-editor-title').textContent = escapeHtml(this.displayName) + ' Configuration';
    this.render();
    document.getElementById('plugin-config-editor').classList.remove('hidden');
    this.setupScrollSpy();
    this._updateSaveButton();
    this._updateAdvancedUI();
    this._attachInputListeners();
  }

  async openInline(pluginName, displayName) {
    this._swapElements(true);
    this.pluginName = pluginName;
    this.displayName = displayName || pluginName;
    this.searchQuery = '';
    this.searchInput.value = '';
    this.errors.clear();

    try {
      await this._loadConfig(pluginName);
    } catch (e) {
      return;
    }

    document.getElementById('plugins-config-title').textContent = escapeHtml(this.displayName) + ' Configuration';
    // Hide plugin list, show config section
    document.getElementById('plugin-list-section').classList.add('hidden');
    document.getElementById('plugins-config-section').classList.remove('hidden');
    this.render();
    this.setupScrollSpy();
    this._updateSaveButton();
    this._updateAdvancedUI();
    this._attachInputListeners();
  }

  onInlineSearch(query) {
    this.searchQuery = query.toLowerCase();
    this.renderContent();
  }

  isDirty() {
    return JSON.stringify(this.config) !== JSON.stringify(this.original);
  }

  _updateSaveButton() {
    const btn = this._inlineMode
      ? document.getElementById('plugins-config-save')
      : document.getElementById('plugin-editor-save');
    if (!btn) return;
    const dirty = this.isDirty();
    btn.disabled = !dirty;
    btn.style.opacity = dirty ? '1' : '0.5';
    btn.style.cursor = dirty ? 'pointer' : 'not-allowed';
  }

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

  _detachInputListeners() {
    if (!this._inputHandler) return;
    this.content.removeEventListener('input', this._inputHandler);
    this.content.removeEventListener('change', this._inputHandler);
    this._inputHandler = null;
    if (this._inputTimer) { clearTimeout(this._inputTimer); this._inputTimer = null; }
  }

  close() {
    if (this._inlineMode) {
      this.closeInline();
      return;
    }
    if (this.isDirty()) {
      showConfirmDialog(I18N.t('dialog.unsavedTitle'), I18N.t('dialog.unsavedClose'), I18N.t('common.close'), 'btn-danger').then(confirmed => {
        if (!confirmed) return;
        this._detachInputListeners();
        this.config = JSON.parse(JSON.stringify(this.original));
        this._updateSaveButton();
        document.getElementById('plugin-config-editor').classList.add('hidden');
        document.getElementById('plugin-review-modal').classList.add('hidden');
      });
      return;
    }
    this._detachInputListeners();
    document.getElementById('plugin-config-editor').classList.add('hidden');
    document.getElementById('plugin-review-modal').classList.add('hidden');
  }

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

  _hideInline() {
    document.getElementById('plugins-config-section').classList.add('hidden');
    document.getElementById('plugin-list-section').classList.remove('hidden');
    document.getElementById('plugin-review-modal').classList.add('hidden');
    document.querySelector('.nav-item[data-view="plugins"]')?.classList.add('active');
  }

  _toggleAdvanced() {
    if (this._advancedMode) {
      this._advancedMode = false;
      localStorage.setItem('plugin_config_advanced_mode', 'false');
      this._updateAdvancedUI();
      this.render();
    } else {
      this._unlockAdvanced();
    }
  }

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
      localStorage.setItem('plugin_config_advanced_mode', 'true');
      this._updateAdvancedUI();
      this.render();
    };
    const handleCancel = () => { cleanup(); };

    if (okBtn) { okBtn.addEventListener('click', handleOk); }
    if (cancelBtn) { cancelBtn.addEventListener('click', handleCancel); }
  }

  _updateAdvancedUI() {
    const inlineBtn = document.getElementById('plugins-config-advanced-btn');
    const overlayBtn = document.getElementById('plugin-editor-advanced-btn');
    [inlineBtn, overlayBtn].forEach(btn => {
      if (!btn) return;
      if (this._advancedMode) {
        btn.textContent = I18N.t('common.advanced') + ' ✓';
        btn.classList.add('active');
      } else {
        btn.textContent = I18N.t('common.advanced');
        btn.classList.remove('active');
      }
    });
  }

  /* ─── Rendering ─── */

  render() {
    this.renderSidebar();
    this.renderContent();
    this.setupScrollSpy();
  }

  renderSidebar() {
    let html = '<div class="sidebar-header">Categories</div>';
    if (!this.hasSchema) {
      html += '<div class="sidebar-group"><a class="sidebar-item active" onclick="pluginEditor.scrollTo(\'section_raw\')">Raw JSON</a></div>';
      this.sidebar.innerHTML = html;
      return;
    }

    const categories = this.groupByCategory();
    for (const [cat, fields] of Object.entries(categories)) {
      const catId = 'cat_' + cat.replace(/[^a-zA-Z0-9]/g, '_');
      const hasErr = fields.some(f => this.fieldHasError(f.key));
      const isActive = this.activeCategory === cat;
      html += '<div class="sidebar-group">';
      html += `<a class="sidebar-item ${hasErr ? 'has-error' : ''} ${isActive ? 'active' : ''}" onclick="pluginEditor.scrollTo('${catId}')">${escapeHtml(cat)}${hasErr ? '<span class="badge">!</span>' : ''}</a>`;
      html += '</div>';
    }
    this.sidebar.innerHTML = html;
  }

  renderContent() {
    if (!this.hasSchema) {
      this.content.innerHTML = this.buildRawEditor();
      return;
    }

    const categories = this.groupByCategory();
    let html = '';
    for (const [cat, fields] of Object.entries(categories)) {
      const catId = 'cat_' + cat.replace(/[^a-zA-Z0-9]/g, '_');
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
      html = `<div class="search-empty"><h3>No results</h3><p>No settings match your search.</p></div>`;
    }
    this.content.innerHTML = html;
  }

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

  /* ─── Schema Field Builders ─── */

  buildSchemaField(field, value) {
    if (field.advanced && !this._advancedMode) {
      const label = field.label || toTitle(field.key.split('.').pop());
      const help = field.help || '';
      return `<div class="editor-field editor-field--locked" onclick="pluginEditor._unlockAdvanced()">
        <div class="field-label">
          <span class="lock-icon">🔒</span> ${escapeHtml(label)}
        </div>
        <div class="field-widget">
          <div class="locked-overlay">
            <span class="locked-text">Advanced setting — <a href="#" onclick="event.preventDefault();pluginEditor._unlockAdvanced()">unlock advanced features</a> to edit</span>
          </div>
          ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
        </div>
      </div>`;
    }
    const path = field.key;
    const id = 'pf_' + path.replace(/[^a-zA-Z0-9]/g, '_');
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
      // Default string
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

  buildArrayField(field, value, path, id) {
    const arr = Array.isArray(value) ? value : [];
    const itemSchema = field.item_schema || {};
    const itemType = itemSchema.type || 'string';

    if (itemType === 'object' && itemSchema.fields) {
      // Table of objects
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
        html += `<td class="row-actions"><button class="btn-icon" onclick="pluginEditor.removeArrayItem('${path}', ${i})">Remove</button></td></tr>`;
      }
      html += '</tbody></table>';
      html += `<button class="btn btn-secondary" style="margin-top:0.5rem;" onclick="pluginEditor.addArrayObjectItem('${path}')">+ Add Row</button>`;
      return html;
    } else if (itemType === 'string') {
      // Tag editor for string arrays
      const chips = arr.map((v, idx) => `<span class="tag-chip">${escapeHtml(v)}<span class="remove" onclick="pluginEditor.removeTagByIndex('${path}', ${idx})">&times;</span></span>`).join('');
      return `<div class="tag-box" id="${id}_box">${chips}<input type="text" id="${id}_inp" placeholder="Add..." onkeydown="pluginEditor.tagKey(event, '${path}')"></div>`;
    } else {
      // Generic JSON array fallback
      return `<textarea id="${id}" data-path="${escapeHtml(path)}" data-type="json" rows="4" style="font-family:monospace;">${escapeHtml(JSON.stringify(arr, null, 2))}</textarea>`;
    }
  }

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

  buildRawEditor() {
    return `<div class="section-card" id="section_raw">
      <div class="section-header"><h3>Raw Configuration</h3></div>
      <div class="section-body">
        <p class="field-desc">This plugin does not provide a configuration schema. You can edit the raw JSON below. Invalid JSON will be rejected on save.</p>
        <textarea id="plugin-raw-json" rows="20" style="font-family:monospace;width:100%;" onchange="pluginEditor.parseRawJson()">${escapeHtml(JSON.stringify(this.config, null, 2))}</textarea>
        <p class="field-desc">Be careful — malformed JSON may break the plugin.</p>
      </div>
    </div>`;
  }

  /* ─── Search ─── */

  categoryMatchesSearch(cat, fields) {
    const q = this.searchQuery;
    if (cat.toLowerCase().includes(q)) return true;
    return fields.some(f => this.fieldMatchesSearch(f));
  }

  fieldMatchesSearch(field) {
    const q = this.searchQuery;
    const label = (field.label || field.key || '').toLowerCase();
    const help = (field.help || '').toLowerCase();
    return label.includes(q) || help.includes(q);
  }

  onSearch(q) {
    this.searchQuery = q.trim().toLowerCase();
    this.render();
  }

  /* ─── Data Helpers ─── */

  getConfigValue(path) {
    const keys = path.split('.');
    let target = this.config;
    for (let i = 0; i < keys.length - 1; i++) {
      if (target === undefined || target === null) return undefined;
      target = target[keys[i]];
    }
    return target !== undefined && target !== null ? target[keys[keys.length - 1]] : undefined;
  }

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

  /* ─── Array / Tag Helpers ─── */

  removeArrayItem(path, index) {
    const arr = this.getConfigValue(path) || [];
    arr.splice(index, 1);
    this.setConfigValue(path, arr);
    this.render();
  }

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

  removeTagByIndex(path, idx) {
    const arr = this.getConfigValue(path) || [];
    if (idx >= 0 && idx < arr.length) { arr.splice(idx, 1); this.setConfigValue(path, arr); this.render(); }
  }

  tagKey(e, path) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const val = e.target.value.trim();
    if (!val) return;
    const arr = this.getConfigValue(path) || [];
    if (!arr.includes(val)) { arr.push(val); this.setConfigValue(path, arr); }
    this.render();
    const id = 'pf_' + path.replace(/[^a-zA-Z0-9]/g, '_') + '_inp';
    setTimeout(() => { const el = document.getElementById(id); if (el) el.focus(); }, 0);
  }

  parseRawJson() {
    const raw = document.getElementById('plugin-raw-json').value;
    try {
      this.config = JSON.parse(raw);
      this.errors.clear();
      this.showToast(I18N.t('editor.jsonValid'), 'info');
    } catch (e) {
      this.showToast(I18N.t('editor.jsonInvalid', { msg: e.message }), 'error');
    }
  }

  findFieldByPath(path) {
    if (!this.schema || !this.schema.fields) return null;
    return this.schema.fields.find(f => f.key === path) || null;
  }

  /* ─── Collection ─── */

  collect() {
    if (!this.hasSchema) {
      // Raw JSON mode already updates this.config on change
      return;
    }
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
        try { this.setConfigValue(path, JSON.parse(el.value)); } catch (e) {}
      } else {
        this.setConfigValue(path, el.value);
      }
    });
  }

  /* ─── Validation ─── */

  validate() {
    this.errors.clear();
    if (!this.hasSchema) {
      try { JSON.stringify(this.config); return true; }
      catch (e) { this.showToast(I18N.t('editor.invalidConfig', { msg: e.message }), 'error'); return false; }
    }

    let ok = true;
    for (const field of (this.schema.fields || [])) {
      const path = field.key;
      const value = this.getConfigValue(path);
      const err = this.validateField(field, value);
      if (err) {
        this.errors.set(path, err);
        ok = false;
      }
      // Validate array items
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
      // Validate object subfields
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

  validateField(field, value) {
    const ftype = field.type || 'string';
    if (field.required) {
      if (value === undefined || value === null || value === '') {
        return 'This field is required.';
      }
      if (ftype === 'array' && Array.isArray(value) && value.length === 0) {
        return 'This field is required.';
      }
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
      if (opts.length && !opts.includes(value)) return `Must be one of: ${opts.join(', ')}.`;
    }

    if ((ftype === 'integer' || ftype === 'number') && field.min !== undefined && field.min !== null) {
      if (Number(value) < field.min) return `Must be at least ${field.min}.`;
    }
    if ((ftype === 'integer' || ftype === 'number') && field.max !== undefined && field.max !== null) {
      if (Number(value) > field.max) return `Must be at most ${field.max}.`;
    }
    return null;
  }

  fieldHasError(path) {
    for (const [epath, _] of this.errors) {
      if (epath === path || epath.startsWith(path + '.')) return true;
    }
    return false;
  }

  /* ─── Save Flow ─── */

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
    const body = document.getElementById('plugin-review-body');
    body.innerHTML = diff.map(d => `<div class="review-item"><div class="review-path">${escapeHtml(d.path)}</div><div class="review-change"><span class="review-old">${escapeHtml(String(d.old))}</span> <span style="color:var(--text-secondary);">-></span> <span class="review-new">${escapeHtml(String(d.new))}</span></div></div>`).join('');
    document.getElementById('plugin-review-modal').classList.remove('hidden');
  }

  hideReview() {
    document.getElementById('plugin-review-modal').classList.add('hidden');
  }

  async confirmSave() {
    this.hideReview();
    try {
      const payload = JSON.parse(JSON.stringify(this.config));
      payload._backup = true;
      await putJSON(`/plugins/${encodeURIComponent(this.pluginName)}/config`, payload);
      this.original = JSON.parse(JSON.stringify(this.config));
      this._updateSaveButton();
      this.close();
      await loadPlugins();
      this.showToast(I18N.t('editor.savedSuccess'), 'success');
      // Only prompt to restart if the plugin is currently enabled
      // Disabled plugins should not trigger restart/reload prompts
      const plugin = currentPlugins.find(p => p.name === this.pluginName);
      if (plugin && plugin.enabled) {
        const display = this.displayName || this.pluginName;
        setTimeout(async () => {
          const confirmed = await showConfirmDialog(
            I18N.t('plugins.restartTitle', { instance: display }),
            I18N.t('plugins.restartConfirm'),
            I18N.t('servers.restart'),
            'btn-danger'
          );
          if (confirmed) {
            restartPlugin(this.pluginName, display);
          }
        }, 300);
      }
    } catch (e) {
      this.showToast(I18N.t('editor.saveFailed', { msg: e.message }), 'error');
    }
  }

  async confirmSaveNoPrompt() {
    this.hideReview();
    try {
      const payload = JSON.parse(JSON.stringify(this.config));
      payload._backup = true;
      await putJSON(`/plugins/${encodeURIComponent(this.pluginName)}/config`, payload);
      this.original = JSON.parse(JSON.stringify(this.config));
      this._updateSaveButton();
      this.close();
      await loadPlugins();
      this.showToast(I18N.t('plugins.configSaved'), 'success');
    } catch (e) {
      this.showToast(I18N.t('editor.saveFailed', { msg: e.message }), 'error');
    }
  }

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

  /* ─── Scroll Spy ─── */

  scrollTo(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (id.startsWith('cat_')) {
      this.activeCategory = id.substring(4).replace(/_/g, ' ');
      this.renderSidebar();
    }
  }

  setupScrollSpy() {
    const main = document.querySelector('#plugin-config-editor .editor-main');
    if (!main) return;
    if (this._observer) this._observer.disconnect();

    const visibleRatios = new Map();
    this._observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const id = entry.target.id;
        if (id && id.startsWith('cat_')) {
          visibleRatios.set(id, entry.intersectionRatio);
        }
      }
      let bestId = null, bestRatio = -1;
      for (const [id, ratio] of visibleRatios) {
        if (ratio > bestRatio) { bestRatio = ratio; bestId = id; }
      }
      if (bestId) {
        const key = bestId.substring(4).replace(/_/g, ' ');
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

  updateSidebarActive() {
    this.sidebar.querySelectorAll('.sidebar-item').forEach(item => item.classList.remove('active'));
    const items = this.sidebar.querySelectorAll('.sidebar-item');
    for (const item of items) {
      const onClick = item.getAttribute('onclick');
      if (onClick && onClick.includes(`cat_${this.activeCategory.replace(/[^a-zA-Z0-9]/g, '_')}`)) {
        item.classList.add('active');
        item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        break;
      }
    }
  }

  showToast(msg, type) {
    const c = document.getElementById('toast-container');
    const t = document.createElement('div');
    t.className = 'toast ' + type;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.remove(), 4000);
  }
}

class ReactionEditor {
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

  _bindEvents() {
    document.getElementById('reaction-add')?.addEventListener('click', () => this.startCreate());
    document.getElementById('reaction-wizard-back')?.addEventListener('click', () => this.wizardBack());
    document.getElementById('reaction-wizard-next')?.addEventListener('click', () => this.wizardNext());
    document.getElementById('reaction-wizard-cancel')?.addEventListener('click', () => this._closeWizard());
    document.getElementById('reaction-delete-cancel')?.addEventListener('click', () => this._hideDeleteModal());
  }

  /* ─── Public API ─── */

  async open() {
    this.el.classList.remove('hidden');
    await loadPlugins();
    await this.load();
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

  isDirty() {
    return this._dirty;
  }

  onSearch(q) {
    this.searchQuery = q.trim().toLowerCase();
    this.renderList();
  }

  /* ─── Dashboard summary ─── */

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

  _updateSaveButton() {
    const btn = document.getElementById('reaction-save');
    if (!btn) return;
    btn.disabled = !this._dirty;
    btn.style.opacity = this._dirty ? '1' : '0.5';
    btn.style.cursor = this._dirty ? 'pointer' : 'not-allowed';
  }

  /* ─── Sidebar / Filters ─── */

  _localized(obj, field) {
    const i18nKey = field + '_i18n';
    if (obj[i18nKey]) {
      const lang = I18N.lang();
      if (obj[i18nKey][lang]) return obj[i18nKey][lang];
    }
    return obj[field] || '';
  }

  _humanizeCategory(cat) {
    return cat
      .split(/[-_]/)
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

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

  setCategory(cat) {
    this.activeCategory = cat;
    this.renderSidebar();
    this.renderList();
  }

  /* ─── List Rendering ─── */

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

  startCreate() {
    this.wizardEditing = null;
    this.wizardStep = 0;
    this.wizardDraft = { event: '', plugin: '', command: '', args: {} };
    this._openWizard();
    this._renderWizard();
  }

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
      const knownTiktokEvents = ['follow', 'like', 'join', 'share', 'comment', 'gift'];
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

  _hideDeleteModal() {
    document.getElementById('reaction-delete-modal').classList.add('hidden');
  }

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

  _openWizard() {
    this.wizardEl.classList.remove('hidden');
    requestAnimationFrame(() => {
      const body = this.wizardEl.querySelector('.reaction-wizard-body');
      if (body) body.scrollTop = 0;
    });
  }

  _closeWizard() {
    this.wizardEl.classList.add('hidden');
  }

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

  selectEvent(key, isCustom = false) {
    this.wizardDraft.event = key;
    this._renderWizard();
  }

  onCustomEventInput(value) {
    // Update draft without re-rendering so the input keeps focus
    this.wizardDraft.event = value;
  }

  selectPlugin(key) {
    this.wizardDraft.plugin = key;
    this.wizardDraft.command = '';
    this.wizardDraft.args = {};
    this._renderWizard();
  }

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

  wizardBack() {
    if (this.wizardStep > 0) {
      this.wizardStep--;
      this._renderWizard();
    }
  }

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

/* ════════════════════════════════════════════════════════════════════
   Comment Commands Editor
   ════════════════════════════════════════════════════════════════════ */

class CommentCommandsEditor {
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

  _bindEvents() {
    document.getElementById('cc-add')?.addEventListener('click', () => this.startCreate());
    document.getElementById('cc-group-cancel')?.addEventListener('click', () => this._closeWizard());
    document.getElementById('cc-group-next')?.addEventListener('click', () => this._wizardNext());
    document.getElementById('cc-group-back')?.addEventListener('click', () => this._wizardBack());
    document.getElementById('cc-delete-cancel')?.addEventListener('click', () => this._hideDeleteModal());
  }

  async open() {
    this.el.classList.remove('hidden');
    await this.load();
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

  async _loadPluginCatalog() {
    try {
      const res = await fetchJSON('/reactions/catalog');
      this._pluginCatalog = res.commands || {};
    } catch (e) {
      this._pluginCatalog = {};
    }
  }

  isDirty() { return this._dirty; }

  onSearch(q) { this.searchQuery = q.trim().toLowerCase(); this.renderList(); }

  _updateSaveButton() {
    const btn = document.getElementById('cc-save');
    if (!btn) return;
    const dirty = this._dirty;
    btn.disabled = !dirty;
    btn.style.opacity = dirty ? '1' : '0.5';
    btn.style.cursor = dirty ? 'pointer' : 'not-allowed';
  }

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

  setCategory(cat) { this.activeCategory = cat; this.renderSidebar(); this.renderList(); }

  /* ─── List ─── */
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

  _toggleInlinePluginRef(groupIdx) {
    if (this._openPluginRefPanels.has(groupIdx)) {
      this._openPluginRefPanels.delete(groupIdx);
    } else {
      this._openPluginRefPanels.add(groupIdx);
    }
    this.renderList();
  }

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

  toggleGlobal(enabled) { this.data.enabled = enabled; this._dirty = true; this._updateSaveButton(); }
  setGlobalCooldown(v) { this.data.cooldown = v; this._dirty = true; this._updateSaveButton(); }
  setGlobalUserCooldown(v) { this.data.user_cooldown = v; this._dirty = true; this._updateSaveButton(); }

  /* ─── Wizard (create / edit group — 3 steps, no overrides) ─── */
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

  _openWizard() {
    this._renderWizardStep();
    document.getElementById('cc-group-editor').classList.remove('hidden');
  }

  _closeWizard() { document.getElementById('cc-group-editor').classList.add('hidden'); }

  _nextAvailablePrefix() {
    const seq = ['#','!','$','@','*','?','+','~','&','%','/','^'];
    const used = new Set((this.data.groups || []).map(g => g.prefix));
    return seq.find(c => !used.has(c)) || '?';
  }

  _wizardBack() {
    if (this._wizardStep > 0) { this._wizardStep--; this._renderWizardStep(); }
  }

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

  _showStepError(msg) {
    const el = document.getElementById('cc-wiz-error');
    if (el) { el.textContent = msg; el.style.display = 'flex'; }
    else showToast(msg, 'error');
  }

  /* ─── Collect data ─── */
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

  _updateSecurityWarning(d) {
    const warnEl = document.getElementById('cc-security-warning');
    if (!warnEl) return;
    const show = d.handler === 'rcon' && d.mode === 'allow-all' && (d.allowed_roles || []).includes('all');
    warnEl.style.display = show ? 'block' : 'none';
  }

  /* ─── Step 2: Commands ─── */
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

  _hideDeleteModal() { document.getElementById('cc-delete-modal').classList.add('hidden'); }

  /* ─── Save ─── */
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

const reactionEditor = new ReactionEditor();
const commentCommandsEditor = new CommentCommandsEditor();
const pluginEditor = new PluginConfigEditor();
const actionsEditor = new ActionsEditor();

/* ─── Unsaved changes warning on window close ─── */
let _closeInProgress = false;
let _pendingNavigation = null;

// Fallback for browser testing (no pywebview API)
if (typeof pywebview === 'undefined' || !pywebview.api) {
  window.addEventListener('beforeunload', function (e) {
    if (isAnyEditorDirty()) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
}

function isAnyEditorDirty() {
  return editor.isDirty() || pluginEditor.isDirty() || actionsEditor.isDirty || reactionEditor.isDirty() || commentCommandsEditor.isDirty() || chatbotEditor.isDirty();
}

/* Detect close requests from pywebview's on_closing (deadlock-free polling) */
async function _pollCloseRequest() {
  if (_closeInProgress) return;
  try {
    const requested = await pywebview.api.close_requested();
    if (!requested) return;
    await pywebview.api.reset_close_request();
    await _handleCloseRequest();
  } catch (_) {}
}

async function _handleCloseRequest() {
  if (_closeInProgress) return;
  if (!isAnyEditorDirty()) {
    _closeInProgress = true;
    await pywebview.api.approve_close();
    window.close();
    return;
  }
  _closeInProgress = true;
  document.getElementById('btn-unsaved-save-exit').textContent = I18N.t('dialog.saveExit');
  document.getElementById('btn-unsaved-exit-no-save').textContent = I18N.t('dialog.exitNoSave');
  document.getElementById('unsaved-changes-modal').classList.remove('hidden');
}

async function _saveAllEditors() {
  let pluginChanged = false;
  let rconPasswordSet = false;
  if (actionsEditor.isDirty) {
    await actionsEditor.save();
    if (actionsEditor.isDirty) {
      throw new Error('Actions editor could not be saved — check for errors.');
    }
  }
  if (reactionEditor.isDirty()) {
    await reactionEditor.save();
    if (reactionEditor.isDirty()) {
      throw new Error('Reaction editor could not be saved — check for errors.');
    }
  }
  if (commentCommandsEditor.isDirty()) {
    await commentCommandsEditor.save();
    if (commentCommandsEditor.isDirty()) {
      throw new Error('Comment commands editor could not be saved — check for errors.');
    }
  }
  if (chatbotEditor.isDirty()) {
    await chatbotEditor.save();
    if (chatbotEditor.isDirty()) {
      throw new Error('Chatbot editor could not be saved — check for errors.');
    }
  }
  if (editor.isDirty()) {
    const oldRcon = (editor.original || {}).rcon || {};
    editor.collect();
    editor.mergeUnknownKeys();
    const newRcon = (editor.data || {}).rcon || {};
    rconPasswordSet = !oldRcon.password && newRcon.password;
    await putJSON('/config', { config: editor.data, backup: true });
    editor.original = JSON.parse(JSON.stringify(editor.data));
    currentConfig = JSON.parse(JSON.stringify(editor.data));
    editor._updateSaveButton();
  }
  if (pluginEditor.isDirty()) {
    pluginEditor.collect();
    const payload = JSON.parse(JSON.stringify(pluginEditor.config));
    payload._backup = true;
    await putJSON(`/plugins/${encodeURIComponent(pluginEditor.pluginName)}/config`, payload);
    pluginEditor.original = JSON.parse(JSON.stringify(pluginEditor.config));
    pluginEditor._updateSaveButton();
    pluginChanged = true;
  }

  await postJSON('/reload', {});
  if (rconPasswordSet) {
    await postJSON('/server/restart', {});
  }
  if (pluginChanged) {
    await postJSON(`/plugins/${encodeURIComponent(pluginEditor.pluginName)}/restart`, {});
    showToast(I18N.t('plugins.changesAppliedRestart'), 'success');
  }
}

function _discardAllEditors() {
  if (actionsEditor.isDirty) {
    actionsEditor.isDirty = false;
    actionsEditor._updateSaveButton();
  }
  if (reactionEditor.isDirty()) {
    reactionEditor._dirty = false;
    reactionEditor._updateSaveButton();
  }
  if (commentCommandsEditor.isDirty()) {
    commentCommandsEditor._dirty = false;
    commentCommandsEditor._updateSaveButton();
  }
  if (editor.isDirty()) {
    editor.data = JSON.parse(JSON.stringify(editor.original));
    currentConfig = JSON.parse(JSON.stringify(editor.original));
    editor._updateSaveButton();
  }
  if (pluginEditor.isDirty()) {
    pluginEditor.config = JSON.parse(JSON.stringify(pluginEditor.original));
    pluginEditor._updateSaveButton();
  }
}

document.getElementById('btn-unsaved-save-exit').addEventListener('click', async () => {
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  const navigate = _pendingNavigation;
  _pendingNavigation = null;
  try {
    await _saveAllEditors();
    if (navigate) {
      navigate();
    } else {
      _closeInProgress = true;
      await pywebview.api.approve_close();
      window.close();
    }
  } catch (e) {
    showToast(I18N.t('plugins.saveFailedExit', { msg: e.message }), 'error');
    _closeInProgress = false;
  }
});

document.getElementById('btn-unsaved-exit-no-save').addEventListener('click', async () => {
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  const navigate = _pendingNavigation;
  _pendingNavigation = null;
  if (navigate) {
    _discardAllEditors();
    navigate();
  } else {
    _closeInProgress = true;
    await pywebview.api.approve_close();
    window.close();
  }
});

document.getElementById('btn-unsaved-cancel').addEventListener('click', () => {
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  _pendingNavigation = null;
  _closeInProgress = false;
});

/* ─── Update Checker ─── */
let _updateData = null;
let _lastResultToastCode = null;
let _autoInstallEnabled = true;
let _updateNotificationShown = false;

async function checkAllUpdates() {
  const summary = document.getElementById('updates-summary');
  const detail = document.getElementById('updates-detail');
  if (summary) summary.innerHTML = '<span class="text-muted">' + I18N.t('updates.checking') + '</span>';
  if (detail) detail.classList.add('hidden');

  try {
    const [toolData, pluginData, hookData, lastResult, autoInstallData] = await Promise.all([
      fetchJSON('/updates/check').catch(() => null),
      fetchJSON('/plugins/updates').catch(() => null),
      fetchJSON('/hooks/updates').catch(() => null),
      fetchJSON('/updates/result').catch(() => null),
      fetchJSON('/updates/auto_install').catch(() => null),
    ]);

    if (autoInstallData && typeof autoInstallData.auto_install === 'boolean') {
      _autoInstallEnabled = autoInstallData.auto_install;
    }

    _updateData = { tool: toolData, plugins: pluginData, hooks: hookData, lastResult };
    if (lastResult && lastResult.exit_code !== null && lastResult.ok === false) {
      if (_lastResultToastCode !== lastResult.exit_code) {
        _lastResultToastCode = lastResult.exit_code;
        showToast(I18N.t('updates.lastFailedMsg', { msg: lastResult.message || I18N.t('updates.exitCode', { code: lastResult.exit_code }) }), 'error');
      }
    }
    _renderUpdateResults();

    if (!_autoInstallEnabled && !_updateNotificationShown && toolData && toolData.update_available) {
      _updateNotificationShown = true;
      showUpdateNotification(toolData.latest_version);
    }
  } catch (e) {
    if (summary) summary.innerHTML = '<span class="log-err">' + I18N.t('updates.checkFailed') + '</span>';
    log('Update check failed: ' + e.message, 'err');
  }
}

function _renderUpdateResults() {
  const summary = document.getElementById('updates-summary');
  const detail = document.getElementById('updates-detail');
  if (!summary) return;

  const tool = _updateData?.tool;
  const plugins = _updateData?.plugins;
  const hooks = _updateData?.hooks;
  const toolAvail = tool && tool.update_available;
  const pluginAvail = plugins && plugins.updates_available > 0;
  const hookAvail = hooks && hooks.updates_available > 0;
  const total =
    (toolAvail ? 1 : 0) +
    (pluginAvail ? plugins.updates_available : 0) +
    (hookAvail ? hooks.updates_available : 0);

  let html = '<div class="update-actions">' +
    '<button class="btn btn--primary" onclick="checkAllUpdates()">' + I18N.t('updates.check') + '</button>' +
    '</div>';

  const lastResult = _updateData?.lastResult;
  if (lastResult && lastResult.exit_code !== null && lastResult.ok === false) {
    html +=
      '<div class="update-status update-status--err">' +
      '<span class="update-status__icon">✕</span>' +
      '<div><span class="update-status__text">' + I18N.t('updates.lastFailed') + '</span>' +
      '<span class="update-status__version">' + escapeHtml(lastResult.message || I18N.t('updates.exitCode', { code: lastResult.exit_code })) + '</span>' +
      '</div></div>';
  }

  if (!toolAvail && !pluginAvail && !hookAvail) {
    html +=
      '<div class="update-status update-status--ok">' +
      '<span class="update-status__icon">✓</span>' +
      '<div><span class="update-status__text">' + I18N.t('updates.allUpToDate') + '</span>' +
      (tool ? '<span class="update-status__version">v' + tool.current_version + '</span>' : '') +
      '</div></div>';
    summary.innerHTML = html;
    detail.classList.add('hidden');
    return;
  }

  html +=
    '<div class="update-status update-status--avail">' +
    '<span class="update-status__icon">!</span>' +
    '<div><span class="update-status__text">' + I18N.t('updates.available', { count: total }) + '</span>' +
    (tool ? '<span class="update-status__version">v' + tool.current_version + '</span>' : '') +
    '</div></div>';

  if (!_autoInstallEnabled && toolAvail) {
    html +=
      '<button class="btn btn--primary" style="width:100%;margin-bottom:0.5rem;" onclick="triggerToolUpdate()">' + I18N.t('updates.updateNow') + '</button>';
  }

  html +=
    '<button class="btn btn--primary" style="width:100%;" onclick="applyUpdates()">' + I18N.t('updates.applyRestart') + '</button>';

  summary.innerHTML = html;

  let detailHtml = '';
  if (toolAvail) {
    detailHtml +=
      '<div class="update-item">' +
      '<div class="update-item__info">' +
      '<strong>TikTok2Mc</strong>' +
      '<span class="update-item__version">' + tool.current_version + ' → <strong>' + tool.latest_version + '</strong></span>' +
      '</div>' +
      (tool.release_url ? '<a href="' + escapeHtml(tool.release_url) + '" target="_blank" class="btn btn--secondary btn--sm">' + I18N.t('updates.viewRelease') + '</a>' : '') +
      '</div>';
  }
  if (pluginAvail && plugins.plugins) {
    for (const p of plugins.plugins) {
      if (!p.update_available) continue;
      detailHtml +=
        '<div class="update-item">' +
        '<div class="update-item__info">' +
        '<strong>' + escapeHtml(p.display_name || p.name) + '</strong>' +
        '<span class="update-item__version">' + p.current_version + ' → <strong>' + p.latest_version + '</strong></span>' +
        '</div>' +
        (p.error ? '<span class="log-err">' + escapeHtml(p.error) + '</span>' : '') +
        '</div>';
    }
  }
  if (hookAvail && hooks.hooks) {
    for (const h of hooks.hooks) {
      if (!h.update_available) continue;
      detailHtml +=
        '<div class="update-item">' +
        '<div class="update-item__info">' +
        '<strong>' + escapeHtml(h.display_name || h.name) + '</strong>' +
        '<span class="update-item__version">' + h.current_version + ' → <strong>' + h.latest_version + '</strong></span>' +
        '</div>' +
        (h.error ? '<span class="log-err">' + escapeHtml(h.error) + '</span>' : '') +
        '</div>';
    }
  }
  detail.innerHTML = detailHtml;
  detail.classList.remove('hidden');
}

async function applyUpdates() {
  log(I18N.t('updates.installing'), 'info');
  let installed = 0;
  const failures = [];
  try {
    const result = await postJSON('/plugins/updates/install', {});
    if (result.installed > 0) {
      installed += result.installed;
      log(I18N.t('updates.installedOk', { count: result.installed }), 'info');
    }
    if (result.failed > 0) {
      log(I18N.t('updates.installedFailed', { count: result.failed }), 'err');
      for (const r of result.results) {
        if (!r.success) failures.push(r);
      }
    }
  } catch (e) {
    log('Plugin update install failed: ' + e.message, 'err');
    showToast(I18N.t('updates.installFailedGeneric', { msg: e.message }), 'error');
  }
  try {
    // Hooks may not have pending updates or the endpoint may be absent
    // in older installs — both are non-fatal.
    const hookResult = await postJSON('/hooks/updates/install', {});
    if (hookResult.installed > 0) {
      installed += hookResult.installed;
      log(I18N.t('updates.installedOk', { count: hookResult.installed }), 'info');
    }
    if (hookResult.failed > 0) {
      log(I18N.t('updates.installedFailed', { count: hookResult.failed }), 'err');
      for (const r of hookResult.results || []) {
        if (!r.success) failures.push(r);
      }
    }
  } catch (e) {
    log('Hook update install failed: ' + e.message, 'err');
  }
  for (const r of failures) {
    showToast(I18N.t('updates.installFailed', { name: r.display_name || r.name, msg: r.error || I18N.t('common.unknownError') }), 'error');
  }
  showRestartDialog(
    I18N.t('updates.applyTitle'),
    installed > 0
      ? I18N.t('updates.installedRestart', { count: installed })
      : I18N.t('updates.restartToApply')
  );
}

function showUpdateNotification(version) {
  const desc = document.getElementById('update-notification-desc');
  if (desc) {
    desc.textContent = I18N.t('updates.popupDesc', { version: version });
  }
  document.getElementById('update-notification-dialog').classList.remove('hidden');
}

function hideUpdateNotification() {
  document.getElementById('update-notification-dialog').classList.add('hidden');
}

async function triggerToolUpdate() {
  const btn = event?.target;
  if (btn) btn.disabled = true;
  showToast(I18N.t('updates.updating'), 'info');
  try {
    const result = await postJSON('/updates/apply', {});
    if (result.status === 'started') {
      showToast(I18N.t('updates.updating'), 'info');
    } else {
      showToast(I18N.t('updates.applyFailed', { msg: result.message || I18N.t('common.unknownError') }), 'error');
    }
  } catch (e) {
    showToast(I18N.t('updates.applyFailed', { msg: e.message }), 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ─── SSE Log Streaming ─── */
let _sseSource = null;
let _sseReconnectTimer = null;
let _sseReconnectDelay = 2000;

function connectLogStream() {
  if (_sseSource) {
    _sseSource.close();
  }
  if (_sseReconnectTimer) {
    clearTimeout(_sseReconnectTimer);
    _sseReconnectTimer = null;
  }
  const ep = '/api/v1/events/stream' + (_apiKey ? '?key=' + encodeURIComponent(_apiKey) : '');
  _sseSource = new EventSource(ep);
  _sseSource.onopen = () => {
    // Reset backoff on successful connection.
    _sseReconnectDelay = 2000;
    liveLog.setConnected(true);
  };
  _sseSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const type = data.type || '';
      const payload = data.data || {};
      if (type === 'log') {
        liveLog.add(payload.msg || payload.message || '', payload.level || 'info', payload.source || '');
      } else if (type === 'server.console') {
        if (payload.line && (!_consoleInstanceId || payload.instance_id === _consoleInstanceId)) {
          consoleTerminal._print(payload.line, 'server');
        }
      } else if (type === 'server.restarting') {
        liveLog.add('Backend restart started', 'warning', 'server');
        _showRestartOverlay();
      } else if (type === 'server.started') {
        liveLog.add('API server started (v' + (payload.version || '?') + ')', 'info', 'server');
        if (_restartPending) {
          window.location.reload();
        }
      } else if (type === 'server.stopping') {
        liveLog.add('API server stopping', 'warning', 'server');
      } else if (type.startsWith('plugin.')) {
        liveLog.add(payload.msg || type, payload.level || 'info', payload.plugin || 'plugin');
      } else if (type === 'tiktok.live_status') {
        _tiktokLiveState = payload.connected === true;
        if (typeof payload.disabled === 'boolean') {
          _tiktokConnectDisabled = payload.disabled;
        }
        _updateTiktokStatusDisplay();
      } else if (type.startsWith('tiktok.')) {
        // Test triggers (trigger tester / external simulations) must never
        // count as proof of an active live connection.
        const isTestEvent = payload.test === true || payload.source === 'trigger_tester';
        if (!isTestEvent) {
          _lastTiktokEventTime = Date.now();
          _updateTiktokStatusDisplay();
        }
      } else if (type === 'dashboard.ecm_diagnostics') {
        updateEcmDiagnostics(payload);
      } else if (type === 'chatbot.status') {
        chatbotEditor._renderStatus(payload);
      } else if (type === 'update.available') {
        // Auto-install disabled: show notification if not already shown
        if (!_autoInstallEnabled && !_updateNotificationShown) {
          _updateNotificationShown = true;
          showUpdateNotification(payload.latest_version || 'unknown');
        }
      }
    } catch (_) {}
  };
  _sseSource.onerror = () => {
    liveLog.add('Log stream disconnected — retrying...', 'warning', 'sse');
    liveLog.setConnected(false);
    // EventSource auto-reconnects, but if the server is gone for long
    // it gives up.  We manually reconnect with backoff.
    if (_sseSource) {
      _sseSource.close();
      _sseSource = null;
    }
    if (_sseReconnectTimer) clearTimeout(_sseReconnectTimer);
    _sseReconnectTimer = setTimeout(() => {
      // Don't reconnect if we're shutting down or restarting.
      if (_shutdownCountdownInterval || _restartPending) return;
      connectLogStream();
    }, _sseReconnectDelay);
    // Exponential backoff up to 10s.
    _sseReconnectDelay = Math.min(_sseReconnectDelay * 1.5, 10000);
  };
}

/* ─── Live Dashboard Widgets ─── */

function updateEcmDiagnostics(payload) {
  // Update the reactions summary on the dashboard card if it shows 0
  const summary = document.getElementById('reactions-summary');
  if (summary && payload.total_reactions !== undefined) {
    const count = payload.total_reactions;
    if (count === 0) {
      summary.innerHTML = '<span style="color:var(--text-secondary);">' + I18N.t('reactions.noReactionsSet') + '</span>';
    } else {
      summary.innerHTML = `<span style="color:var(--success);">${count === 1 ? I18N.t('reactions.reactionCount', { count }) : I18N.t('reactions.reactionsCount', { count })}</span> <span style="color:var(--text-secondary);">${I18N.t('reactions.configured')}</span>`;
    }
  }
}

/* ─── Minecraft Console Terminal ─── */

function parseMinecraftColors(text) {
  const colors = {
    '0': '#000000', '1': '#0000AA', '2': '#00AA00', '3': '#00AAAA',
    '4': '#AA0000', '5': '#AA00AA', '6': '#FFAA00', '7': '#AAAAAA',
    '8': '#555555', '9': '#5555FF', 'a': '#55FF55', 'b': '#55FFFF',
    'c': '#FF5555', 'd': '#FF55FF', 'e': '#FFFF55', 'f': '#FFFFFF',
  };
  const formats = {
    'l': 'font-weight:bold;',
    'm': 'text-decoration:line-through;',
    'n': 'text-decoration:underline;',
    'o': 'font-style:italic;',
  };

  let html = '';
  let open = false;
  let styleParts = [];

  for (let i = 0; i < text.length; i++) {
    if (text[i] === '§' && i + 1 < text.length) {
      const code = text[i + 1].toLowerCase();
      if (colors[code] !== undefined || formats[code] !== undefined || code === 'r') {
        if (open) {
          html += '</span>';
          open = false;
        }
        if (code === 'r') {
          styleParts = [];
        } else {
          if (colors[code]) {
            styleParts = styleParts.filter(s => !s.startsWith('color:'));
            styleParts.push('color:' + colors[code] + ';');
          }
          if (formats[code]) {
            styleParts.push(formats[code]);
          }
          html += '<span style="' + styleParts.join('') + '">';
          open = true;
        }
        i++;
        continue;
      }
    }
    html += text[i]
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
  if (open) html += '</span>';
  return html;
}

let _consoleInstanceId = '';
let _consoleLastRefresh = 0;

function refreshConsoleInstanceSelector() {
  const sel = document.getElementById('console-instance-selector');
  if (!sel) return;
  const now = Date.now();
  if (now - _consoleLastRefresh < 2000) return;
  _consoleLastRefresh = now;
  const instances = _serverManagerCache?.instances || [];
  const current = sel.value;
  sel.innerHTML = '<option value="">' + I18N.t('reactions.selectServer') + '</option>' +
    instances.map(inst =>
      `<option value="${escapeHtml(inst.id)}" ${inst.id === current ? 'selected' : ''}>${escapeHtml(inst.name)} (${inst.hasJar ? escapeHtml(inst.version) : I18N.t('servers.notInstalled')})</option>`
    ).join('');
  if (!current && instances.length === 1) {
    sel.value = instances[0].id;
    _consoleInstanceId = instances[0].id;
  }
}

const CONSOLE_HISTORY_KEY = 'tiktok2mc_console_history';
const CONSOLE_HISTORY_MAX = 50;

const consoleTerminal = {
  _history: (() => {
    try {
      const saved = JSON.parse(localStorage.getItem(CONSOLE_HISTORY_KEY) || '[]');
      return Array.isArray(saved) ? saved.slice(0, CONSOLE_HISTORY_MAX) : [];
    } catch (_) { return []; }
  })(),
  _historyIdx: -1,
  _connected: false,
  _tabIdx: -1,
  _tabBase: '',
  _tabMatches: [],

  _commandCompletions: [
    'advancement', 'attribute', 'ban', 'ban-ip', 'banlist', 'bossbar', 'clear', 'clone',
    'connect', 'datapack', 'debug', 'defaultgamemode', 'deop', 'difficulty', 'effect',
    'enchant', 'execute', 'experience', 'fill', 'fillbiome', 'forceload', 'function',
    'gamemode', 'gamerule', 'give', 'help', 'item', 'jfr', 'kick', 'kill', 'list',
    'locate', 'loot', 'me', 'msg', 'op', 'pardon', 'particle', 'playsound', 'publish',
    'recipe', 'reload', 'remove', 'replaceitem', 'return', 'save-all', 'save-off',
    'save-on', 'say', 'schedule', 'scoreboard', 'seed', 'setblock', 'setidletimeout',
    'setworldspawn', 'spawnpoint', 'spectate', 'spreadplayers', 'stopsound', 'summon',
    'tag', 'team', 'teammsg', 'teleport', 'tell', 'tellraw', 'testfor', 'testforblock',
    'testforblocks', 'tick', 'time', 'title', 'titleraw', 'toggledownfall', 'tp',
    'trigger', 'weather', 'whitelist', 'worldborder', 'xp'
  ],

  _saveHistory() {
    try {
      localStorage.setItem(CONSOLE_HISTORY_KEY, JSON.stringify(this._history.slice(-CONSOLE_HISTORY_MAX)));
    } catch (_) {}
  },

  _resetTabState() {
    this._tabIdx = -1;
    this._tabBase = '';
    this._tabMatches = [];
  },

  _completeCurrentToken(input, word) {
    if (!word) { this._resetTabState(); return false; }
    const lower = word.toLowerCase();
    const isCycle = this._tabBase && this._tabMatches.length > 0 &&
      lower.startsWith(this._tabBase) &&
      this._tabMatches.some(c => c.toLowerCase() === lower);
    if (isCycle) {
      this._tabIdx = (this._tabIdx + 1) % this._tabMatches.length;
      this._replaceLastToken(input, word, this._tabMatches[this._tabIdx]);
      return true;
    }
    const candidates = this._commandCompletions.filter(c => c.toLowerCase().startsWith(lower));
    if (candidates.length === 0) { this._resetTabState(); return false; }
    if (candidates.length === 1) {
      this._resetTabState();
      this._replaceLastToken(input, word, candidates[0]);
      return true;
    }
    this._tabBase = lower;
    this._tabMatches = candidates;
    this._tabIdx = 0;
    this._replaceLastToken(input, word, candidates[0]);
    return true;
  },

  _replaceLastToken(input, word, replacement) {
    const start = input.selectionStart ?? input.value.length;
    const val = input.value;
    const from = Math.max(val.lastIndexOf(' ', start - 1) + 1, 0);
    input.value = val.slice(0, from) + replacement + val.slice(start);
    const cursor = from + replacement.length;
    input.setSelectionRange(cursor, cursor);
  },

  _complete(input) {
    const start = input.selectionStart ?? input.value.length;
    const before = input.value.slice(0, start);
    const word = (before.match(/\S+$/) || [''])[0];
    this._completeCurrentToken(input, word);
  },

  switchInstance(instanceId) {
    _consoleInstanceId = instanceId || '';
    if (this._connected) {
      this.disconnect();
    }
    const output = document.getElementById('console-output');
    output.innerHTML = '';
    this._print(I18N.t('console.switched', { target: instanceId ? I18N.t('console.serverPrefix', { id: instanceId }) : I18N.t('console.allServers') }), 'system');
  },

  async toggleConnection() {
    if (this._connected) {
      await this.disconnect();
    } else {
      await this.connect();
    }
  },

  async connect() {
    const btn = document.getElementById('btn-console-connect');
    const input = document.getElementById('console-input');
    const status = document.getElementById('console-status');
    btn.disabled = true;
    btn.textContent = I18N.t('console.connecting');
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    try {
      const res = await fetch(API + '/rcon/connect', { method: 'POST', signal: controller.signal, headers: _withApiKey({}) });
      if (!res.ok) throw new Error((await res.json()).detail || I18N.t('console.commandFailed'));
      this._connected = true;
      status.textContent = I18N.t('console.connected');
      status.className = 'console-status connected';
      btn.textContent = I18N.t('console.disconnect');
      input.disabled = false;
      input.focus();
      this._print(I18N.t('console.connectedMsg'), 'system');
    } catch (e) {
      if (e.name === 'AbortError') {
        this._print(I18N.t('console.timeout'), 'error');
      } else {
        this._print(I18N.t('console.failed', { msg: e.message }), 'error');
      }
      btn.textContent = I18N.t('console.connect');
      status.textContent = I18N.t('console.disconnected');
      status.className = 'console-status offline';
    } finally {
      clearTimeout(timeoutId);
      btn.disabled = false;
    }
  },

  async disconnect() {
    const btn = document.getElementById('btn-console-connect');
    const input = document.getElementById('console-input');
    const status = document.getElementById('console-status');
    btn.disabled = true;
    try {
      await fetch(API + '/rcon/disconnect', { method: 'POST', headers: _withApiKey({}) });
    } catch (_) {}
    this._connected = false;
    status.textContent = I18N.t('console.disconnected');
    status.className = 'console-status offline';
    btn.textContent = I18N.t('console.connect');
    input.disabled = true;
    this._print(I18N.t('console.disconnectedMsg'), 'system');
    btn.disabled = false;
  },

  async sendCommand(cmd) {
    if (!cmd.trim()) return;
    this._print('> ' + cmd, 'input');
    try {
      const res = await fetch(API + '/rcon/command', {
        method: 'POST',
        headers: _withApiKey({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ command: cmd })
      });
      if (!res.ok) throw new Error((await res.json()).detail || I18N.t('console.commandFailed'));
      const data = await res.json();
      if (data.response) {
        this._print(data.response, 'output');
      }
    } catch (e) {
      if (e.message.includes('MC-0012')) {
        this._print(I18N.t('console.commandApiDisabled'), 'error');
      } else {
        this._print(I18N.t('console.error', { msg: e.message }), 'error');
      }
      if (e.message.includes('Not connected') || e.message.includes('RCON not connected')) {
        this._connected = false;
        const status = document.getElementById('console-status');
        const btn = document.getElementById('btn-console-connect');
        const input = document.getElementById('console-input');
        status.textContent = I18N.t('console.disconnected');
        status.className = 'console-status offline';
        btn.textContent = I18N.t('console.connect');
        input.disabled = true;
      }
    }
  },

  _print(text, cls = 'output') {
    const output = document.getElementById('console-output');
    const line = document.createElement('div');
    line.className = 'console-line console-line--' + cls;
    if (text.includes('§')) {
      line.innerHTML = parseMinecraftColors(text);
    } else {
      line.textContent = text;
    }
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
  },

  clear() {
    const output = document.getElementById('console-output');
    output.innerHTML = '';
    this._print(I18N.t('console.cleared'), 'system');
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('console-input');
  if (!input) return;
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const cmd = input.value;
      if (cmd.trim()) {
        consoleTerminal._history.push(cmd);
        consoleTerminal._historyIdx = consoleTerminal._history.length;
        consoleTerminal._saveHistory();
      }
      input.value = '';
      consoleTerminal.sendCommand(cmd);
    } else if (e.key === 'Tab') {
      e.preventDefault();
      consoleTerminal._complete(input);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (consoleTerminal._historyIdx > 0) {
        consoleTerminal._historyIdx--;
        input.value = consoleTerminal._history[consoleTerminal._historyIdx];
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (consoleTerminal._historyIdx < consoleTerminal._history.length - 1) {
        consoleTerminal._historyIdx++;
        input.value = consoleTerminal._history[consoleTerminal._historyIdx];
      } else {
        consoleTerminal._historyIdx = consoleTerminal._history.length;
        input.value = '';
      }
    }
  });
  input.addEventListener('input', () => consoleTerminal._resetTabState());
});

/* ─── Sidebar ─── */
let _sidebarMode = 0;
const SIDEBAR_MODES = ['full', 'icons', 'hide'];
function _setSidebarMode(mode) {
  _sidebarMode = mode;
  const sidebar = document.querySelector('.sidebar');
  sidebar.classList.remove('full', 'icons', 'hide');
  sidebar.classList.add(SIDEBAR_MODES[_sidebarMode]);
  document.querySelector('.app-layout').classList.toggle('sidebar-hidden', _sidebarMode === 2);
}
function cycleSidebar() {
  // Toggle between full (0) and icons (1)
  _setSidebarMode(_sidebarMode === 0 ? 1 : 0);
}
function hideSidebar() {
  _setSidebarMode(2);
}
function _initSidebarReveal() {
  const reveal = document.querySelector('.sidebar-reveal');
  reveal?.addEventListener('click', () => {
    if (_sidebarMode === 2) _setSidebarMode(0);
  });
  document.querySelector('.app-layout')?.addEventListener('click', (e) => {
    if (_sidebarMode === 2 && e.clientX < 18) {
      _setSidebarMode(0);
    }
  });
}

/* ─── Mobile sidebar (off-canvas drawer) ─── */
function _isMobileWidth() {
  return window.innerWidth <= 768;
}

function toggleMobileSidebar() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  const open = sidebar.classList.toggle('mobile-open');
  document.getElementById('sidebar-backdrop')?.classList.toggle('open', open);
  document.querySelector('.mobile-menu-btn')?.setAttribute('aria-expanded', String(open));
  if (open) {
    const first = sidebar.querySelector('a[href], button, input, select, textarea, [tabindex]');
    if (first) first.focus();
  }
}

function closeMobileSidebar() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar || !sidebar.classList.contains('mobile-open')) return;
  sidebar.classList.remove('mobile-open');
  document.getElementById('sidebar-backdrop')?.classList.remove('open');
  document.querySelector('.mobile-menu-btn')?.setAttribute('aria-expanded', 'false');
}

function _initMobileSidebar() {
  document.getElementById('sidebar-backdrop')?.addEventListener('click', closeMobileSidebar);
  window.addEventListener('resize', () => {
    if (!_isMobileWidth()) closeMobileSidebar();
  });
}

/* ─── Editor helpers (show/hide editors within app-layout) ─── */
function _hideAllEditors() {
  document.querySelectorAll('.editor-overlay').forEach(el => el.classList.add('hidden'));
}

function _syncDashboardVisibility() {
  const anyOpen = document.querySelector('.editor-overlay:not(.hidden)');
  document.getElementById('dashboard').classList.toggle('dashboard-hidden', !!anyOpen);
  // Deactivate editor nav items when no editor is open
  if (!anyOpen) {
    document.querySelectorAll('.nav-item[data-view="actions"], .nav-item[data-view="reactions"], .nav-item[data-view="settings"], .nav-item[data-view="commands"], .nav-item[data-view="chatbot"]').forEach(el => el.classList.remove('active'));
  }
}

function _initEditorVisibilityObserver() {
  const observer = new MutationObserver(_syncDashboardVisibility);
  document.querySelectorAll('.editor-overlay').forEach(el => {
    observer.observe(el, { attributes: true, attributeFilter: ['class'] });
  });
  _syncDashboardVisibility();
}

/* ─── Sidebar Navigation ─── */
function _switchWithUnsavedGuard(action) {
  if (isAnyEditorDirty()) {
    _pendingNavigation = action;
    document.getElementById('btn-unsaved-save-exit').textContent = I18N.t('dialog.saveChanges');
    document.getElementById('btn-unsaved-exit-no-save').textContent = I18N.t('dialog.discardChanges');
    document.getElementById('unsaved-changes-modal').classList.remove('hidden');
  } else {
    action();
  }
}

function switchView(viewId) {
  _switchWithUnsavedGuard(() => switchViewNow(viewId));
}

function switchViewNow(viewId) {
  _hideAllEditors();
  closeMobileSidebar();
  // Close inline plugin config if open
  const pluginInline = document.getElementById('plugins-config-section');
  if (pluginInline && !pluginInline.classList.contains('hidden')) {
    pluginInline.classList.add('hidden');
    document.getElementById('plugin-list-section')?.classList.remove('hidden');
    pluginEditor._detachInputListeners();
    document.getElementById('plugin-review-modal')?.classList.add('hidden');
  }
  // Close inline hook config if open
  const hookInline = document.getElementById('hooks-config-section');
  if (hookInline && !hookInline.classList.contains('hidden')) {
    hookInline.classList.add('hidden');
    document.getElementById('hook-list-section')?.classList.remove('hidden');
    hookEditor._detachInputListeners();
    document.getElementById('hook-review-modal')?.classList.add('hidden');
  }
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
  document.querySelector(`.nav-item[data-view="${viewId}"]`)?.classList.add('active');
  document.getElementById('view-' + viewId)?.classList.add('active');
  if (viewId === 'plugins') {
    renderPluginManager();
  }
  if (viewId === 'hooks') {
    renderHookManager();
  }
  if (viewId === 'overlays') {
    renderOverlayUrls();
  }
  if (viewId === 'servers') {
    loadServerManager();
    startServerLifecyclePolling();
  } else {
    stopServerLifecyclePolling();
  }
  if (viewId === 'log') {
    crashReports.load();
    requestAnimationFrame(() => liveLog._scrollToBottom());
  }
  if (viewId === 'revenue') {
    loadRevenueView();
  }
  if (viewId === 'sessions') {
    loadSessions();
  }
  if (viewId === 'backups') {
    loadBackups();
  }
}

/* For nav items that open an editor (Actions/Reactions/Settings) */
function switchToEditor(viewId, openFn) {
  _switchWithUnsavedGuard(() => switchToEditorNow(viewId, openFn));
}

function switchToEditorNow(viewId, openFn) {
  const prevNav = document.querySelector('.nav-item.active');
  const prevOverlay = document.querySelector('.editor-overlay:not(.hidden)');
  _hideAllEditors();
  closeMobileSidebar();
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const navItem = document.querySelector(`.nav-item[data-view="${viewId}"]`);
  navItem?.classList.add('active');
  let aborted = false;
  // An editor's open() may abort by resolving `false` (e.g. the chatbot beta
  // consent gate). Restore the previous nav item / editor instead of leaving
  // the target nav highlighted above the old dashboard view.
  Promise.resolve(openFn()).then(result => {
    if (result !== false) return;
    aborted = true;
    navItem?.classList.remove('active');
    if (prevNav && prevNav.isConnected) prevNav.classList.add('active');
    if (prevOverlay && prevOverlay.isConnected) prevOverlay.classList.remove('hidden');
  });
  // Re-assert active class after editor opens to handle race condition
  // where MutationObserver might clear it before editor overlay is visible
  setTimeout(() => {
    if (!aborted) navItem?.classList.add('active');
  }, 0);
}

/* ─── Theme Toggle ─── */
function _initTheme() {
  const saved = localStorage.getItem('theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'dark'); // default to dark for this app
  document.documentElement.setAttribute('data-theme', theme);
  _updateThemeLabel(theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  _updateThemeLabel(next);
  _retargetPluginFrames(next);
}

function _updateThemeLabel(theme) {
  const label = document.getElementById('theme-label');
  if (!label) return;
  label.textContent = I18N.t(theme === 'dark' ? 'nav.themeLight' : 'nav.themeDark');
}

/* ─── Language Switcher ─── */
function _syncLangButtons() {
  const lang = I18N.lang();
  document.querySelectorAll('.lang-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });
}

document.addEventListener('i18n:changed', () => {
  _syncLangButtons();
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  _updateThemeLabel(theme);
  const cfgEditor = document.getElementById('config-editor');
  if (cfgEditor && !cfgEditor.classList.contains('hidden') && typeof editor !== 'undefined') {
    editor.render();
  }
  loadStatus();
  if (typeof reactionEditor !== 'undefined') {
    reactionEditor.renderSidebar();
    reactionEditor.renderList();
  }
});

/* ─── Event Tester ─── */
class EventTester {
  constructor() {
    this._cooldown = false;
    this._history = [];
    this._statusEl = document.getElementById('trigger-tester-status');
    this._errorEl = document.getElementById('trigger-error');
    this._historyEl = document.getElementById('trigger-history');
    this._gifts = [];
    this._selectedGift = null;
    this._giftSelectLoaded = false;
  }

  onTypeChange() {
    const type = document.getElementById('trigger-type').value;
    const customGroup = document.getElementById('custom-trigger-group');
    const giftGroup = document.getElementById('gift-trigger-group');
    const commentFields = document.getElementById('comment-fields');
    if (customGroup) customGroup.style.display = type === 'custom' ? 'block' : 'none';
    if (giftGroup) giftGroup.style.display = type === 'gift' ? 'block' : 'none';
    if (commentFields) commentFields.style.display = type === 'comment' ? 'flex' : 'none';

    if (type === 'gift' && !this._giftSelectLoaded) {
      this._loadGifts();
    }
  }

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

  onGiftSearch(query) {
    const q = (query || '').toLowerCase().trim();
    const filtered = q
      ? this._gifts.filter(g => (g.name || '').toLowerCase().includes(q) || String(g.id).includes(q))
      : this._gifts;
    this._renderGiftSelect(filtered);
  }

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

  _setStatus(state, text) {
    if (!this._statusEl) return;
    this._statusEl.textContent = text;
    this._statusEl.className = 'console-status ' + state;
  }

  _showError(msg) {
    if (!this._errorEl) return;
    this._errorEl.textContent = msg;
    this._errorEl.classList.remove('hidden');
    setTimeout(() => this._errorEl.classList.add('hidden'), 5000);
  }

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

  clearHistory() {
    this._history = [];
    this._renderHistory();
  }
}

const eventTester = new EventTester();

/* ─── Init ─── */
async function init() {
  _initTheme();
  _syncLangButtons();
  _initEditorVisibilityObserver();
  _initSidebarReveal();
  _initMobileSidebar();
  await loadHealth();
  await loadStatus();
  await loadConfig();
  await loadPlugins();
  // One-time hook discovery at startup, then periodic refresh is just the list
  await postJSON('/hooks/discover', {}).catch(() => {});
  await loadHooks();
  await loadServerManager();
  await reactionEditor.load();
  updateRestartBanner();
  connectLogStream();
  checkAllUpdates();
  if (isFirstRun(currentConfig)) showWizard();
  else hideWizard();
  if (!window.__TEST__) {
    _healthIntervalId = setInterval(loadHealth, 10000);
    _statusIntervalId = setInterval(loadStatus, 10000);
    _pluginsIntervalId = setInterval(loadPlugins, 5000);
    _hooksIntervalId = setInterval(loadHooks, 10000);
    _uptimeIntervalId = setInterval(() => {
      const activeView = document.querySelector('.view.active');
      if (activeView && activeView.id === 'view-status') {
        _updateUptimeDisplay();
      }
      if (activeView && (activeView.id === 'view-status' || activeView.id === 'view-servers')) {
        _updateServerUptimeDisplay();
      }
      _updateTiktokStatusDisplay();
    }, 1000);
    if (typeof pywebview !== 'undefined' && pywebview.api) {
      _closePollIntervalId = setInterval(_pollCloseRequest, 200);
    }
  }
}
function hideAppLoading() {
  document.getElementById('app-loading')?.classList.add('app-loading--hidden');
}
init().finally(hideAppLoading);
