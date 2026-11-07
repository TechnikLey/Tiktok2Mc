/**
 * @file Live log buffer, toast notifications and crash-report handling.
 *
 * Provides the shared logging surface used by the rest of the dashboard.
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Live Log ─── */
const LOG_FILTER_KEY = 'tiktok2mc_log_filter';
const LOG_AUTOSCROLL_KEY = 'tiktok2mc_log_autoscroll';
const LOG_LEVELS = ['all', 'info', 'warning', 'error', 'debug', 'critical'];

/**
 * Filterable live-log view with its own SSE subscription and persisted display preferences.
 *
 * Keeps at most 500 entries in the DOM and supports level/search filters, pause, export and connection statistics.
 */
class LiveLog {
  /** Create the log view, cache its DOM elements and restore persisted display preferences. */
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

  /** Restore level, search and autoscroll preferences from localStorage. */
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

  /** Highlight the level filter buttons for the active filter. */
  _applyFilterButtons() {
    const buttons = document.getElementById('log-filter-buttons');
    if (!buttons) return;
    buttons.querySelectorAll('.log-filter-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-level') === this.filter);
    });
  }

  /** Persist autoscroll changes when the user toggles the checkbox. */
  _bindAutoscroll() {
    const autoScroll = document.getElementById('log-autoscroll');
    if (!autoScroll) return;
    autoScroll.addEventListener('change', () => {
      try { localStorage.setItem(LOG_AUTOSCROLL_KEY, String(autoScroll.checked)); } catch (_) {}
    });
  }

  /** Normalize a raw log level to one of the filter categories. */
  _normalizeLevel(level) {
    const l = String(level || 'info').toLowerCase();
    if (l === 'warn') return 'warning';
    if (l === 'err') return 'error';
    if (l === 'crit') return 'critical';
    if (['info','warning','error','debug','critical'].includes(l)) return l;
    return 'info';
  }

  /** Wire level filters, search, pause and export controls. */
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

  /** Open the log SSE stream and reconnect with backoff. */
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

  /** Handle one SSE log payload, skipping entries suppressed by pause or filters. */
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

  /** Select a level filter and re-render the visible entries. */
  setFilter(level) {
    this.filter = level || 'all';
    try { localStorage.setItem(LOG_FILTER_KEY, this.filter); } catch (_) {}
    this._applyFilterButtons();
    this.render();
  }

  /** Apply a search query and re-render the visible entries. */
  onSearch(query) {
    this.searchQuery = (query || '').toLowerCase().trim();
    this.render();
  }

  /** Pause or resume live log updates. */
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

  /** Update the SSE connection indicator. */
  setConnected(connected) {
    if (this.status) {
      this.status.textContent = this.paused
        ? I18N.t('log.paused')
        : (connected ? I18N.t('log.connected') : I18N.t('log.streamDisconnected'));
    }
  }

  /** Remove all entries from the view. */
  clear() {
    this.entries = [];
    this.levelCounts = { all: 0, info: 0, warning: 0, error: 0, debug: 0, critical: 0 };
    this.render();
  }

  /** Export the currently visible log entries as a text file. */
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

  /** Add a log entry, enforce the buffer limit and render it when it matches the filters. */
  add(message, level = 'info', source = '') {
    this._addFromSSE(message, level, source);
  }

  /** Return whether an entry passes the active level and search filters. */
  _matches(entry) {
    if (this.filter !== 'all' && entry.level !== this.filter) return false;
    if (this.searchQuery) {
      const text = (entry.message + ' ' + entry.source + ' ' + entry.level).toLowerCase();
      return text.includes(this.searchQuery);
    }
    return true;
  }

  /** Build the DOM row for one log entry. */
  _renderEntry(entry) {
    const line = document.createElement('div');
    line.className = 'log-line log-' + entry.level;
    line.setAttribute('data-id', entry.id);
    line.setAttribute('data-level', entry.level);
    line.innerHTML = `<span class="log-time">${escapeHtml(entry.time)}</span><span class="log-badge log-badge-${entry.level}">${entry.level.toUpperCase()}</span>${entry.source ? '<span class="log-source">' + escapeHtml(entry.source) + '</span>' : ''}<span class="log-message">${escapeHtml(entry.message)}</span>`;
    return line;
  }

  /** Remove rendered rows beyond the 500-entry limit. */
  _trimVisible() {
    while (this.view.children.length > this.maxEntries) {
      this.view.removeChild(this.view.firstChild);
    }
  }

  /** Scroll the log container to the newest entry. */
  _scrollToBottom() {
    const autoScroll = document.getElementById('log-autoscroll');
    if (!autoScroll || autoScroll.checked) {
      this.view.scrollTop = this.view.scrollHeight;
    }
  }

  /** Update entry counts and the pause button label. */
  _updateStats() {
    for (const level of Object.keys(this.levelCounts)) {
      const el = document.getElementById('stat-' + level);
      if (el) el.textContent = this.levelCounts[level];
    }
  }

  /** Update the number of visible entries. */
  _updateVisibleCount() {
    if (this.visibleCount) {
      const visible = Array.from(this.view.children).filter(c => !c.classList.contains('hidden')).length;
      this.visibleCount.textContent = visible + ' / ' + this.entries.length + ' shown';
    }
  }

  /** Re-render all entries matching the current filters. */
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

/** Append a message to the live-log widget, creating the widget on first use. */
function log(msg, level = 'info') {
  liveLog.add(msg, level);
}

const liveLog = new LiveLog();

/* ─── Crash Reports ─── */
/**
 * Crash-report browser backed by `/logs/crash-reports`.
 *
 * Renders the report list and a detail pane with the selected traceback.
 */
class CrashReports {
  /** Create the crash-report browser and cache its DOM elements. */
  constructor() {
    this.container = document.getElementById('crash-reports-list');
    this.detailView = document.getElementById('crash-report-detail');
    this.detailContent = document.getElementById('crash-report-detail-content');
    this.emptyState = document.getElementById('crash-reports-empty');
    this.reports = [];
  }

  /** Fetch the crash-report list and render it. */
  async load() {
    try {
      const data = await fetchJSON('/logs/crash-reports');
      this.reports = data.reports || [];
      this.renderList();
    } catch (e) {
      if (this.container) this.container.innerHTML = '<p class="muted">' + I18N.t('log.crashLoadFailed') + '</p>';
    }
  }

  /** Render the list of available crash reports. */
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

  /** Load and display one crash report. */
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

  /** Close the detail view and return to the report list. */
  close() {
    if (this.detailView) this.detailView.classList.add('hidden');
  }

  /** Render the traceback and metadata of the selected report. */
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

/** Show a transient toast notification; errors and warnings are announced to assistive technology. */
function showToast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  t.setAttribute('role', type === 'error' || type === 'warning' ? 'alert' : 'status');
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

