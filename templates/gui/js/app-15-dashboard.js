/**
 * @file Health/status polling, live statistics, plugin status and hook widgets.
 *
 * Renders the dashboard overview; data loading is triggered by init() in app.js.
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Dashboard ─── */
/** Fetch the health endpoint and update the health summary cards. */
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

/** Format an uptime in seconds as hours, minutes and seconds. */
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

/** Refresh the displayed uptime by extrapolating from the last API sample. */
function _updateUptimeDisplay() {
  const el = document.getElementById('uptime-value');
  if (!el) return;
  const now = Date.now();
  const elapsed = (now - _uptimeData.lastFetch) / 1000;
  const total = _uptimeData.baseSeconds + elapsed;
  el.textContent = formatUptime(total);
}

/** Update uptime values on server cards, clearing stale values for stopped instances. */
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


/** Fetch the dashboard status payload and update system, live and TikTok state. */
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

/** Render live-stream counters such as queue sizes, events per minute and gift value. */
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

/** Update the TikTok status indicator, falling back to a recent event while the live state is unknown. */
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

/** Classify a plugin record as `error`, `disabled` or `enabled` for status badges. */
function getPluginStatus(p) {
  if (p.error) return { label: I18N.t('common.error'), cls: 'status-error' };
  if (!p.enabled) return { label: I18N.t('plugins.disabled'), cls: 'status-disabled' };
  return { label: I18N.t('plugins.enabled'), cls: 'status-enabled' };
}

/** Fetch the plugin registry and re-render the plugin manager and dashboard navigation. */
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

/** Rebuild hook-provided dashboard widgets from `/hooks/widgets`, removing stale widgets and lazy-loading iframes. */
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

/** Activate a hook widget view and hydrate its deferred iframe sources. */
function openHookWidgets() {
  const view = document.getElementById('view-' + HOOK_WIDGET_VIEW);
  if (!view) return;
  // Load iframes on first open
  view.querySelectorAll('iframe[data-src]').forEach(f => {
    if (!f.src && f.dataset.src) f.src = f.dataset.src;
  });
  switchView(HOOK_WIDGET_VIEW);
}

