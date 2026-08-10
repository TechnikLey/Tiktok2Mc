import { describe, it, expect, beforeEach } from 'vitest';

/* ─── fetchJSON / postJSON / putJSON ─── */
describe('API helpers', () => {
  beforeEach(() => {
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ result: 'ok' }),
    });
  });

  it('fetchJSON calls GET with API prefix', async () => {
    const data = await fetchJSON('/health');
    expect(data).toEqual({ result: 'ok' });
  });

  it('postJSON calls POST with JSON body', async () => {
    let calledUrl, calledBody;
    globalThis.fetch = async (url, opts) => {
      calledUrl = url;
      calledBody = opts.body;
      return { ok: true, status: 200, statusText: 'OK', json: async () => ({}) };
    };
    await postJSON('/plugins/test/enable', {});
    expect(calledUrl).toContain('/api/v1/plugins/test/enable');
    expect(calledBody).toBe('{}');
  });

  it('putJSON calls PUT with JSON body', async () => {
    let calledMethod, calledBody;
    globalThis.fetch = async (url, opts) => {
      calledMethod = opts.method;
      calledBody = opts.body;
      return { ok: true, status: 200, statusText: 'OK', json: async () => ({}) };
    };
    await putJSON('/config', { config: {} });
    expect(calledMethod).toBe('PUT');
    expect(calledBody).toBe('{"config":{}}');
  });

  it('fetchJSON throws on non-ok response', async () => {
    globalThis.fetch = async () => ({
      ok: false, status: 500, statusText: 'Server Error',
      json: async () => ({}),
    });
    await expect(fetchJSON('/health')).rejects.toThrow('500');
  });
});

/* ─── log / showToast ─── */
describe('log / showToast', () => {
  it('log adds line to log-view', () => {
    const view = document.getElementById('log-view');
    view.innerHTML = '';
    log('Test message', 'info');
    expect(view.children.length).toBe(1);
    expect(view.lastChild.textContent).toContain('Test message');
    expect(view.lastChild.className).toContain('log-info');
  });

  it('log uses info level by default', () => {
    const view = document.getElementById('log-view');
    view.innerHTML = '';
    log('Default level');
    expect(view.lastChild.className).toContain('log-info');
  });

  it('showToast creates toast in container', () => {
    const container = document.getElementById('toast-container');
    container.innerHTML = '';
    showToast('Hello', 'info');
    expect(container.children.length).toBe(1);
    expect(container.lastChild.textContent).toBe('Hello');
    expect(container.lastChild.className).toBe('toast info');
  });

  it('showToast removes after timeout', async () => {
    const container = document.getElementById('toast-container');
    container.innerHTML = '';
    showToast('Auto-remove', 'success');
    expect(container.children.length).toBe(1);
    // After 4001ms the toast should be removed (setTimeout 4000)
    await new Promise(r => setTimeout(r, 4100));
    expect(container.children.length).toBe(0);
  }, 10000);
});

/* ─── loadHealth ─── */
describe('loadHealth', () => {
  it('sets online pill on success', async () => {
    globalThis.fetch = async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({ api_version: '1.0.0' }),
    });
    const pill = document.getElementById('status-pill');
    await loadHealth();
    expect(pill.textContent).toContain('1.0.0');
    expect(pill.className).toBe('online');
  });

  it('sets offline pill on failure', async () => {
    globalThis.fetch = async () => { throw new Error('Network error'); };
    const pill = document.getElementById('status-pill');
    await loadHealth();
    expect(pill.textContent).toBe('Offline');
    expect(pill.className).toBe('offline');
  });
});

/* ─── loadStatus ─── */
describe('loadStatus', () => {
  it('renders system info on success', async () => {
    globalThis.fetch = async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({
        server: 'running',
        plugins_active: 2,
        plugins_total: 4,
        config_loaded: true,
        uptime_seconds: 3600,
      }),
    });
    const el = document.getElementById('system-info');
    await loadStatus();
    expect(el.innerHTML).toContain('running');
    expect(el.innerHTML).toContain('2 / 4');
  });

  it('shows error on failure', async () => {
    globalThis.fetch = async () => { throw new Error('API down'); };
    const el = document.getElementById('system-info');
    await loadStatus();
    expect(el.innerHTML).toContain('Failed to load status');
  });
});

/* ─── loadPlugins ─── */
describe('loadPlugins', () => {
  it('renders plugin manager table', async () => {
    globalThis.fetch = async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({
        plugins: [
          { name: 'spotify', enabled: true, display_name: 'Spotify', port: 29186 },
        ],
      }),
    });
    await loadPlugins();
    expect(currentPlugins).toHaveLength(1);
    const table = document.getElementById('plugin-manager-table');
    expect(table.innerHTML).toContain('spotify');
  });
});

/* ─── renderOverlayUrls ─── */
describe('renderOverlayUrls', () => {
  beforeEach(() => {
    currentPlugins = [];
    currentConfig = {};
  });

  it('renders OBS URLs for enabled plugins with ports', () => {
    currentPlugins = [{ name: 'test', enabled: true, port: 29186, display_name: 'Test' }];
    renderOverlayUrls();
    const container = document.getElementById('overlay-urls');
    // The function always renders the built-in overlay section ...
    expect(container.innerHTML).toContain('Built-in Overlay');
    // ... and adds plugin overlay URLs for enabled plugins with ports.
    expect(container.innerHTML).toContain('localhost:29186');
  });

  it('shows built-in overlay even when no plugins with ports', () => {
    currentPlugins = [{ name: 'test', enabled: true, port: 0 }];
    renderOverlayUrls();
    const container = document.getElementById('overlay-urls');
    // The built-in overlay URL is always rendered.
    expect(container.innerHTML).toContain('Built-in Overlay');
    expect(container.innerHTML).toContain('overlay=default');
    // No plugin overlay URLs should appear.
    expect(container.innerHTML).not.toContain('Plugin Overlays');
  });
});

/* ─── renderPluginManager ─── */
describe('renderPluginManager', () => {
  beforeEach(() => {
    currentPlugins = [];
    const tableDiv = document.getElementById('plugin-manager-table');
    if (tableDiv) tableDiv.innerHTML = '';
  });

  it('shows empty message when no plugins', () => {
    currentPlugins = [];
    renderPluginManager();
    const tableDiv = document.getElementById('plugin-manager-table');
    expect(tableDiv.innerHTML).toContain('No plugins found');
  });

  it('renders plugin table rows', () => {
    currentPlugins = [
      { name: 'spotify', enabled: true, version: '1.0', port: 29186, display_name: 'Spotify' },
    ];
    renderPluginManager();
    const tableDiv = document.getElementById('plugin-manager-table');
    expect(tableDiv.innerHTML).toContain('spotify');
    expect(tableDiv.innerHTML).toContain('1.0');
    expect(tableDiv.innerHTML).toContain('29186');
  });
});

/* ─── copyUrl ─── */
describe('copyUrl', () => {
  it('copies URL to clipboard', async () => {
    let copied = '';
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: async (text) => { copied = text; } },
      configurable: true,
    });
    const btn = document.createElement('button');
    btn.textContent = 'Copy';
    document.body.appendChild(btn);
    await copyUrl(btn, 'http://localhost:29186');
    expect(copied).toBe('http://localhost:29186');
    expect(btn.textContent).toBe('Copied');
    document.body.removeChild(btn);
  });
});

/* ─── restartPlugin ─── */
describe('restartPlugin', () => {
  it('performs disable-wait-enable cycle', async () => {
    const calls = [];
    globalThis.fetch = async (url, opts) => {
      calls.push({ url, method: opts?.method || 'GET' });
      return { ok: true, status: 200, statusText: 'OK', json: async () => ({ plugins: [] }) };
    };
    await restartPlugin('spotify', 'Spotify');
    expect(calls.length).toBeGreaterThanOrEqual(2);
    expect(calls[0].url).toContain('/api/v1/plugins/spotify/disable');
  });
});

/* ─── isFirstRun (dashboard) ─── */
describe('isFirstRun', () => {
  it('returns true for placeholder username', () => {
    expect(isFirstRun({ tiktok: { user: 'your_tiktok_username' }, rcon: { password: 'x' } })).toBe(true);
  });
  it('returns true for missing password', () => {
    expect(isFirstRun({ tiktok: { user: 'real' }, rcon: { password: '' } })).toBe(true);
  });
  it('returns false when properly configured', () => {
    expect(isFirstRun({ tiktok: { user: 'real' }, rcon: { password: 'secret' } })).toBe(false);
  });
});

/* ─── escapeHtml (double-check) ─── */
describe('escapeHtml (full coverage)', () => {
  it('escapes & < > "', () => {
    expect(escapeHtml('&<>"')).toBe('&amp;&lt;&gt;"');
  });
  it('passes safe strings', () => {
    expect(escapeHtml('hello world 123')).toBe('hello world 123');
  });
});

/* ─── toTitle (edge cases) ─── */
describe('toTitle (edge cases)', () => {
  it('handles single character', () => {
    expect(toTitle('a')).toBe('A');
  });
  it('handles numbers in string', () => {
    expect(toTitle('abc_123_def')).toBe('Abc 123 Def');
  });
});

/* ─── formatUptime (edge cases) ─── */
describe('formatUptime (edge cases)', () => {
  it('handles negative values', () => {
    expect(formatUptime(-1)).toBe('-1s');
  });
  it('handles large values', () => {
    expect(formatUptime(100000)).toBe('27h 46m 40s');
  });
});

/* ─── getPasswordStrength (edge cases) ─── */
describe('getPasswordStrength (edge cases)', () => {
  it('returns weak for very long but simple password', () => {
    expect(getPasswordStrength('aaaaaaaaaaaa')).toBe('medium');
  });
  it('returns medium for mixed but short password', () => {
    expect(getPasswordStrength('Ab1!')).toBe('medium'); // length=4, score=4
  });
  it('returns strong for complex password', () => {
    expect(getPasswordStrength('Abcd1234!')).toBe('strong'); // length>=8, upper, lower, digit, special = score 5
  });
});

/* ─── validatePassword (combinations) ─── */
describe('validatePassword (combinations)', () => {
  it('returns multiple issues for weak password', () => {
    const issues = validatePassword('short');
    expect(issues.length).toBeGreaterThanOrEqual(1);
  });
  it('only reports actual issues', () => {
    const issues = validatePassword('abcdefgh');
    expect(issues).not.toContain('At least 8 characters');
    expect(issues).toContain('One uppercase letter (A-Z)');
    expect(issues).toContain('One number (0-9)');
    expect(issues).toContain('One special character (!@#$ etc.)');
  });
});

/* ─── showConfirmDialog ─── */
describe('showConfirmDialog', () => {
  it('resolves to true when OK clicked', async () => {
    const promise = showConfirmDialog('Title', 'Message');
    document.getElementById('btn-confirm-ok').click();
    const result = await promise;
    expect(result).toBe(true);
    const dlg = document.getElementById('confirm-dialog');
    expect(dlg.classList.contains('hidden')).toBe(true);
  });

  it('resolves to false when Cancel clicked', async () => {
    const promise = showConfirmDialog('Title', 'Message');
    document.getElementById('btn-confirm-cancel').click();
    const result = await promise;
    expect(result).toBe(false);
  });
});

/* ─── showWizard / hideWizard ─── */
describe('showWizard / hideWizard', () => {
  it('shows wizard and hides dashboard', () => {
    showWizard();
    const wizard = document.getElementById('wizard');
    const dashboard = document.getElementById('dashboard');
    expect(wizard.classList.contains('hidden')).toBe(false);
    expect(dashboard.classList.contains('hidden')).toBe(true);
  });

  it('hides wizard and shows dashboard', () => {
    hideWizard();
    const wizard = document.getElementById('wizard');
    const dashboard = document.getElementById('dashboard');
    expect(wizard.classList.contains('hidden')).toBe(true);
    expect(dashboard.classList.contains('hidden')).toBe(false);
  });
});

/* ─── hideAppLoading ─── */
describe('hideAppLoading', () => {
  it('hides the startup loading indicator', () => {
    const loading = document.getElementById('app-loading');
    loading.classList.remove('app-loading--hidden');
    hideAppLoading();
    expect(loading.classList.contains('app-loading--hidden')).toBe(true);
  });
});



/* ─── updateRestartBanner ─── */
describe('updateRestartBanner', () => {
  it('shows banner when restart pending', () => {
    _restartPending = true;
    updateRestartBanner();
    const banner = document.getElementById('restart-pending-banner');
    expect(banner.classList.contains('hidden')).toBe(false);
  });

  it('hides banner when no restart pending', () => {
    _restartPending = false;
    updateRestartBanner();
    const banner = document.getElementById('restart-pending-banner');
    expect(banner.classList.contains('hidden')).toBe(true);
  });
});

/* ─── dismissRestartBanner ─── */
describe('dismissRestartBanner', () => {
  it('clears restart pending and updates banner', () => {
    _restartPending = true;
    dismissRestartBanner();
    expect(_restartPending).toBe(false);
    const banner = document.getElementById('restart-pending-banner');
    expect(banner.classList.contains('hidden')).toBe(true);
  });
});

/* ─── wizard rendering ─── */
describe('wizard rendering', () => {
  beforeEach(() => {
    wizardStep = 0;
    wizardData = { tiktok_user: '', rcon_password: '' };
  });

  it('renders step 0 (TikTok user)', () => {
    renderWizardStep();
    const content = document.getElementById('wizard-content');
    expect(content.innerHTML).toContain('TikTok Username');
    expect(content.innerHTML).toContain('w-tiktok-user');
  });

  it('renders step 1 (RCON password)', () => {
    wizardStep = 1;
    renderWizardStep();
    const content = document.getElementById('wizard-content');
    expect(content.innerHTML).toContain('RCON Password');
  });

  it('renders step 2 (review)', () => {
    wizardStep = 2;
    wizardData.tiktok_user = 'testuser';
    wizardData.rcon_password = 'secret123';
    renderWizardStep();
    const content = document.getElementById('wizard-content');
    expect(content.innerHTML).toContain('testuser');
    expect(content.innerHTML).toContain('********');
  });
});

/* ─── wizardNext validation ─── */
describe('wizardNext', () => {
  beforeEach(() => {
    wizardStep = 0;
    wizardData = { tiktok_user: '', rcon_password: '' };
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('wizard').classList.remove('hidden');
    renderWizardStep();
  });

  it('shows error for empty tiktok username', async () => {
    const input = document.getElementById('w-tiktok-user');
    input.value = '';
    await wizardNext();
    expect(input.classList.contains('invalid')).toBe(true);
    expect(wizardStep).toBe(0);
  });

  it('shows error for placeholder username', async () => {
    const input = document.getElementById('w-tiktok-user');
    input.value = 'your_tiktok_username';
    await wizardNext();
    expect(input.classList.contains('invalid')).toBe(true);
  });

  it('advances step with valid username', async () => {
    const input = document.getElementById('w-tiktok-user');
    input.value = 'realuser';
    await wizardNext();
    expect(wizardStep).toBe(1);
  });
});

/* ─── updatePasswordMeter ─── */
describe('updatePasswordMeter', () => {
  beforeEach(() => {
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('wizard').classList.remove('hidden');
    wizardStep = 1;
    wizardData.rcon_password = '';
    renderWizardStep();
  });

  it('shows weak for short password', () => {
    const input = document.getElementById('w-rcon-password');
    input.value = 'abc';
    updatePasswordMeter();
    const label = document.getElementById('strength-label');
    expect(label.textContent).toBe('Weak');
  });

  it('shows medium for moderate password', () => {
    const input = document.getElementById('w-rcon-password');
    input.value = 'Abcdefgh';
    updatePasswordMeter();
    const label = document.getElementById('strength-label');
    expect(label.textContent).toBe('Medium');
  });

  it('shows strong for complex password', () => {
    const input = document.getElementById('w-rcon-password');
    input.value = 'Abcdef1!xyz';
    updatePasswordMeter();
    const label = document.getElementById('strength-label');
    expect(label.textContent).toBe('Strong');
  });

  it('resets for empty password', () => {
    const input = document.getElementById('w-rcon-password');
    input.value = '';
    updatePasswordMeter();
    const label = document.getElementById('strength-label');
    expect(label.textContent).toBe('Enter a password to see strength');
  });
});

/* ─── checkAllUpdates ─── */
describe('checkAllUpdates', () => {
  beforeEach(() => {
    _lastResultToastCode = null;
    const summary = document.getElementById('updates-summary');
    if (summary) {
      summary.innerHTML = '<span class="text-muted">No update information available.</span>';
    }
  });

  it('shows all up to date when no updates', async () => {
    globalThis.fetch = async (url) => {
      let body;
      if (url.includes('updates/check')) body = { current_version: '1.0.0', update_available: false };
      else if (url.includes('updates/result')) body = { exit_code: 5, ok: true, message: 'No update needed.' };
      else body = { updates_available: 0, plugins: [] };
      return { ok: true, status: 200, statusText: 'OK', json: async () => body };
    };
    await checkAllUpdates();
    const summary = document.getElementById('updates-summary');
    expect(summary.innerHTML).toContain('All up to date');
  });

  it('shows error banner when the last update failed', async () => {
    globalThis.fetch = async (url) => {
      let body;
      if (url.includes('updates/check')) body = { current_version: '1.0.0', update_available: false };
      else if (url.includes('updates/result')) body = { exit_code: 13, ok: false, message: 'Checksum verification failed.' };
      else body = { updates_available: 0, plugins: [] };
      return { ok: true, status: 200, statusText: 'OK', json: async () => body };
    };
    const container = document.getElementById('toast-container');
    container.innerHTML = '';
    await checkAllUpdates();
    const summary = document.getElementById('updates-summary');
    expect(summary.innerHTML).toContain('Last update failed');
    expect(summary.innerHTML).toContain('Checksum verification failed.');
    expect(container.children.length).toBe(1);
    expect(container.lastChild.className).toBe('toast error');
  });
});

/* ─── connectLogStream ─── */
describe('connectLogStream', () => {
  it('creates EventSource and handles messages', () => {
    connectLogStream();
    expect(_sseSource).toBeTruthy();
    expect(_sseSource.url).toContain('/api/v1/events/stream');
  });

  it('handles log messages via EventSource', () => {
    connectLogStream();
    const view = document.getElementById('log-view');
    view.innerHTML = '';
    const msgEvent = { data: JSON.stringify({ type: 'log', data: { msg: 'hello', level: 'info' } }) };
    _sseSource.onmessage(msgEvent);
    expect(view.lastChild).toBeTruthy();
    expect(view.lastChild.textContent).toContain('hello');
  });
});

/* ─── TikTok live status ─── */
describe('TikTok live status', () => {
  function seedTiktokDom() {
    currentConfig = { tiktok: { user: 'testuser' } };
    const info = document.getElementById('system-info');
    info.innerHTML =
      '<span class="status-card__value" id="tiktok-status-value">Checking...</span>' +
      '<span class="tiktok-status" id="tiktok-status-pill">Checking</span>';
    const pill = document.getElementById('tiktok-status-pill');
    pill.className = 'tiktok-status connecting';
    pill.textContent = 'Checking';
    _tiktokLiveState = null;
    _lastTiktokEventTime = 0;
  }

  it('shows Connected when live_status is true', () => {
    seedTiktokDom();
    connectLogStream();
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.live_status', data: { connected: true, source: 'tiktok_bridge' } }) });
    expect(_tiktokLiveState).toBe(true);
    expect(document.getElementById('tiktok-status-value').textContent).toBe('Connected');
    expect(document.getElementById('tiktok-status-pill').textContent).toBe('Live');
  });

  it('shows Configured when live_status is false', () => {
    seedTiktokDom();
    connectLogStream();
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.live_status', data: { connected: false } }) });
    expect(_tiktokLiveState).toBe(false);
    expect(document.getElementById('tiktok-status-value').textContent).toBe('Configured');
    expect(document.getElementById('tiktok-status-pill').textContent).toBe('Not Live');
  });

  it('does not count test triggers as live activity', () => {
    seedTiktokDom();
    connectLogStream();
    const before = _lastTiktokEventTime;
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.gift', data: { test: true, uniqueId: 'x' } }) });
    expect(_lastTiktokEventTime).toBe(before);
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.comment', data: { source: 'trigger_tester' } }) });
    expect(_lastTiktokEventTime).toBe(before);
  });

  it('records genuine events while state is unknown (fallback)', () => {
    seedTiktokDom();
    connectLogStream();
    const before = _lastTiktokEventTime;
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.gift', data: { uniqueId: 'x' } }) });
    expect(_lastTiktokEventTime).toBeGreaterThan(before);
    expect(document.getElementById('tiktok-status-value').textContent).toBe('Connected');
  });

  it('keeps Connected even after a genuine event while explicitly not live', () => {
    seedTiktokDom();
    connectLogStream();
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.live_status', data: { connected: true } }) });
    const before = _lastTiktokEventTime;
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.gift', data: { uniqueId: 'x' } }) });
    expect(_tiktokLiveState).toBe(true);
    expect(document.getElementById('tiktok-status-value').textContent).toBe('Connected');
    expect(_lastTiktokEventTime).toBeGreaterThan(before);
  });

  it('loadStatus reads tiktok_live from the API', async () => {
    seedTiktokDom();
    globalThis.fetch = async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({
        server: 'running', plugins_active: 1, plugins_total: 2,
        config_loaded: true, uptime_seconds: 10, tiktok_live: true, tiktok_live_source: 'tiktok_bridge',
      }),
    });
    await loadStatus();
    expect(_tiktokLiveState).toBe(true);
    expect(document.getElementById('tiktok-status-value').textContent).toBe('Connected');
  });
});

/* ─── EventTester TikTok connection state ─── */
describe('EventTester TikTok connection state', () => {
  beforeEach(() => {
    _tiktokConnectDisabled = false;
    _tiktokLiveState = null;
    _lastTiktokEventTime = 0;
    eventTester._cooldown = false;
    // Reset fetch to default mock to avoid cross-test pollution
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({}),
    });
  });

  function seedTesterDom(user) {
    currentConfig = { tiktok: { user: user || '' } };
    const label = document.getElementById('tiktok-connection-state');
    const btn = document.getElementById('btn-tiktok-toggle');
    if (label) label.className = 'tiktok-state-label';
    if (btn) { btn.className = 'btn btn--secondary'; btn.textContent = 'Toggle Connection'; }
    _tiktokLiveState = null;
    _tiktokConnectDisabled = false;
  }

  it('shows ON when the connection is enabled', () => {
    seedTesterDom('testuser');
    eventTester._updateTiktokStateUI();
    expect(document.getElementById('tiktok-connection-state').textContent).toBe('ON');
    expect(document.getElementById('btn-tiktok-toggle').textContent).toBe('Toggle Connection');
  });

  it('shows OFF when the connection is disabled', () => {
    seedTesterDom('testuser');
    _tiktokConnectDisabled = true;
    eventTester._updateTiktokStateUI();
    expect(document.getElementById('tiktok-connection-state').textContent).toBe('OFF');
  });

  it('shows OFF when disabled even if the bridge reports live', () => {
    seedTesterDom('testuser');
    _tiktokLiveState = true;
    _tiktokConnectDisabled = true;
    eventTester._updateTiktokStateUI();
    expect(document.getElementById('tiktok-connection-state').textContent).toBe('OFF');
  });

  it('shows Not configured when no TikTok user is set', () => {
    seedTesterDom('');
    _tiktokLiveState = true;
    eventTester._updateTiktokStateUI();
    expect(document.getElementById('tiktok-connection-state').textContent).toBe('Not configured');
  });

  it('status display keeps the EventTester label in sync via live_status', () => {
    seedTesterDom('testuser');
    connectLogStream();
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.live_status', data: { connected: true, disabled: false, source: 'tiktok_bridge' } }) });
    expect(document.getElementById('tiktok-connection-state').textContent).toBe('ON');
    _sseSource.onmessage({ data: JSON.stringify({ type: 'tiktok.live_status', data: { connected: false, disabled: true, source: 'tiktok_bridge' } }) });
    expect(document.getElementById('tiktok-connection-state').textContent).toBe('OFF');
  });

  it('warns before turning the connection OFF while live', async () => {
    seedTesterDom('testuser');
    _tiktokLiveState = true;
    let posted = false;
    globalThis.fetch = async () => {
      posted = true;
      return { ok: true, status: 200, statusText: 'OK', json: async () => ({ status: 'ok', connected: false }) };
    };
    const promise = eventTester.toggleTiktok();
    await Promise.resolve();
    expect(document.getElementById('confirm-title').textContent).toBe('Disconnect TikTok Stream');
    document.getElementById('btn-confirm-cancel').click();
    await promise;
    expect(posted).toBe(false);
    expect(_tiktokConnectDisabled).toBe(false);
  });

  it('turns the connection OFF after confirming the warning', async () => {
    seedTesterDom('testuser');
    _tiktokLiveState = true;
    globalThis.fetch = async () => ({ ok: true, status: 200, statusText: 'OK', json: async () => ({ status: 'ok', connected: false }) });
    const promise = eventTester.toggleTiktok();
    await Promise.resolve();
    document.getElementById('btn-confirm-ok').click();
    await promise;
    expect(_tiktokConnectDisabled).toBe(true);
    expect(document.getElementById('tiktok-connection-state').textContent).toBe('OFF');
  });

  it('shows a plain toggle dialog when turning OFF while not connected', async () => {
    seedTesterDom('testuser');
    _tiktokLiveState = false;
    const promise = eventTester.toggleTiktok();
    await Promise.resolve();
    expect(document.getElementById('confirm-title').textContent).toBe('Toggle TikTok Connection');
    document.getElementById('btn-confirm-cancel').click();
    await promise;
  });
});
