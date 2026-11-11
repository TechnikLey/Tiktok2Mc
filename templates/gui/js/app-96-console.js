/**
 * @file SSE log stream, console diagnostics and terminal input.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── SSE Log Streaming ─── */
let _sseSource = null;
let _sseReconnectTimer = null;
let _sseReconnectDelay = 2000;

/** Open the dashboard SSE stream and reconnect with exponential backoff. */
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
    // Reconcile degraded component state from the health endpoint: events
    // fired before the GUI connected would otherwise be missed.
    initDegradedFromHealth();
  };
  _sseSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const type = data.type || '';
      const payload = data.data || {};
      if (type === 'log') {
        liveLog.add(payload.msg || payload.message || '', payload.level || 'info', payload.source || '');
      } else if (type === 'server.console') {
        // Only surface server output when an RCON session is active —
        // otherwise the console would show log lines even when the user
        // has not connected.
        if (consoleTerminal._connected && payload.line && (!_consoleInstanceId || payload.instance_id === _consoleInstanceId)) {
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
      } else if (type === 'tiktok.connect_failed') {
        // Repeated connection failures: pause + let the user choose whether
        // to re-enable or keep the TikTok connection disabled.
        showTiktokFailedDialog(payload.max_fails || 1);
        liveLog.add(
          (payload.reason || '') + ' — ' + I18N.t('dialog.tiktokFailed.title'),
          'warning',
          'tiktok'
        );
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
      } else if (type === 'config.degraded') {
        registerDegraded(payload);
      } else if (type === 'datapack.changed') {
        if (payload.changed === true) handleDatapackFunctionChange(payload);
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

/* ─── Datapack Function Change ─── */

/**
 * Ask the user whether to restart the Minecraft servers after the bridge
 * reports that datapack function content changed (from datapack.changed SSE).
 *
 * Minecraft loads .mcfunction files only at server start, so regenerated
 * functions take effect only after a restart. The bridge sends the list of
 * instances whose world received the datapack; one confirmation covers all
 * of them. On confirm every instance is restarted through the API.
 * @param {object} payload - {changed: boolean, instances: string[]} from the bridge.
 */
function handleDatapackFunctionChange(payload) {
  const instances = Array.isArray(payload.instances) && payload.instances.length
    ? payload.instances
    : ['default'];
  showConfirmDialog(
    I18N.t('datapack.changedTitle'),
    I18N.t('datapack.changedMessage'),
    I18N.t('datapack.restartNow'),
    'btn-primary'
  )
    .then((ok) => {
      if (!ok) {
        liveLog.add(I18N.t('datapack.restartSkipped'), 'warning', 'datapack');
        return null;
      }
      return Promise.allSettled(
        instances.map((id) => postJSON('/server/' + encodeURIComponent(id) + '/restart'))
      ).then((results) => {
        const failed = results.filter((r) => r.status === 'rejected');
        if (failed.length) {
          showToast(
            I18N.t('datapack.restartFailed').replace('{n}', String(failed.length)),
            'error'
          );
        } else {
          liveLog.add(I18N.t('datapack.restartRequested'), 'info', 'datapack');
        }
      });
    })
    .catch((e) => showToast(e.message || I18N.t('common.unknown'), 'error'));
}

/* ─── Degraded Component Banner ─── */

/** Known degraded component states: component name -> payload from report_degraded. */
const _degradedComponents = new Map();

/**
 * Register/render one degraded fallback report (from config.degraded SSE).
 * @param {object} payload - {code, component, message, detail, path} from core.degraded.
 */
function registerDegraded(payload) {
  const component = payload.component || payload.code || 'unknown';
  _degradedComponents.set(component, payload);
  renderDegradedBanner();
  const loc = payload.path ? ' (' + payload.path + ')' : '';
  liveLog.add(
    (payload.code || 'DEGRADED') + ': ' + (payload.detail || payload.message || component) + loc,
    'error',
    'config'
  );
}

/**
 * Initial synchronisation from /health/extended — catches degraded states
 * that were reported before the SSE stream was connected.
 */
async function initDegradedFromHealth() {
  try {
    const data = await fetchJSON('/health/extended');
    const names = (data.subsystems && data.subsystems.degraded_components) || [];
    for (const name of names) {
      if (!_degradedComponents.has(name)) {
        _degradedComponents.set(name, { component: name, code: 'DEGRADED', detail: '' });
      }
    }
    renderDegradedBanner();
  } catch (_) {
    // Health endpoint unavailable — banner stays empty; SSE events cover new cases.
  }
}

/** Show or hide the degraded banner and set its summary text. */
function renderDegradedBanner() {
  const banner = document.getElementById('degraded-banner');
  if (!banner) return;
  const text = document.getElementById('degraded-banner-text');
  if (_degradedComponents.size === 0) {
    banner.classList.add('hidden');
    return;
  }
  const names = Array.from(_degradedComponents.keys()).slice(0, 5).join(', ');
  const more = _degradedComponents.size > 5 ? ' …' : '';
  text.textContent =
    I18N.t('degraded.banner') + ' ' + names + more;
  banner.classList.remove('hidden');
}

/** User dismissed the banner; new degraded reports will show it again. */
function dismissDegradedBanner() {
  document.getElementById('degraded-banner').classList.add('hidden');
}

/* ─── Live Dashboard Widgets ─── */

/** Update the dashboard reactions summary from a diagnostics payload. */
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

/** Convert Minecraft section-sign color codes to escaped HTML with inline styles. */
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

/** Refresh the console instance selector from the cached server list, throttled to once every two seconds. */
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

  /** Persist the console command history to localStorage. */
  _saveHistory() {
    try {
      localStorage.setItem(CONSOLE_HISTORY_KEY, JSON.stringify(this._history.slice(-CONSOLE_HISTORY_MAX)));
    } catch (_) {}
  },

  /** Reset the tab-completion cycling state. */
  _resetTabState() {
    this._tabIdx = -1;
    this._tabBase = '';
    this._tabMatches = [];
  },

  /** Complete the token at the cursor from the available commands. */
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

  /** Replace the token around the cursor with a completion. */
  _replaceLastToken(input, word, replacement) {
    const start = input.selectionStart ?? input.value.length;
    const val = input.value;
    const from = Math.max(val.lastIndexOf(' ', start - 1) + 1, 0);
    input.value = val.slice(0, from) + replacement + val.slice(start);
    const cursor = from + replacement.length;
    input.setSelectionRange(cursor, cursor);
  },

  /** Handle Tab completion for the console input. */
  _complete(input) {
    const start = input.selectionStart ?? input.value.length;
    const before = input.value.slice(0, start);
    const word = (before.match(/\S+$/) || [''])[0];
    this._completeCurrentToken(input, word);
  },

  /** Switch the console to another server instance and reset its connection state. */
  switchInstance(instanceId) {
    _consoleInstanceId = instanceId || '';
    if (this._connected) {
      this.disconnect();
    }
    const output = document.getElementById('console-output');
    output.innerHTML = '';
    this._print(I18N.t('console.switched', { target: instanceId ? I18N.t('console.serverPrefix', { id: instanceId }) : I18N.t('console.allServers') }), 'system');
  },

  /** Connect or disconnect the console depending on its current state. */
  async toggleConnection() {
    if (this._connected) {
      await this.disconnect();
    } else {
      await this.connect();
    }
  },

  /** Connect the console to the selected server instance. */
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
      if (!res.ok) throw new Error((await _parseErrorDetail(res)) || I18N.t('console.commandFailed'));
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

  /** Disconnect the console stream. */
  async disconnect() {
    const btn = document.getElementById('btn-console-connect');
    const input = document.getElementById('console-input');
    const status = document.getElementById('console-status');
    const output = document.getElementById('console-output');
    btn.disabled = true;
    try {
      await fetch(API + '/rcon/disconnect', { method: 'POST', headers: _withApiKey({}) });
    } catch (_) {}
    this._connected = false;
    status.textContent = I18N.t('console.disconnected');
    status.className = 'console-status offline';
    btn.textContent = I18N.t('console.connect');
    input.disabled = true;
    output.innerHTML = '';
    this._print(I18N.t('console.disconnectedMsg'), 'system');
    btn.disabled = false;
  },

  /** Send a command to the connected server. */
  async sendCommand(cmd) {
    if (!cmd.trim()) return;
    this._print('> ' + cmd, 'input');
    try {
      const res = await fetch(API + '/rcon/command', {
        method: 'POST',
        headers: _withApiKey({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ command: cmd })
      });
      if (!res.ok) throw new Error((await _parseErrorDetail(res)) || I18N.t('console.commandFailed'));
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

  /** Append text to the console output, translating Minecraft color codes. */
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

  /** Clear the console output. */
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

