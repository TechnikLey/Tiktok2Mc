const API = '/api/v1';
let currentConfig = {};
let currentPlugins = [];
let wizardStep = 0;
let wizardData = {};

/* ─── API helpers ─── */
async function fetchJSON(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
  return res.json();
}
async function postJSON(path, body) {
  const res = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
  return res.json();
}
async function putJSON(path, body) {
  const res = await fetch(API + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
  return res.json();
}

/* ─── Shutdown Countdown ─── */
let _shutdownPollInterval = null;
let _shutdownTriggered = false;
let _shutdownNowClicked = false;
let _shutdownApiFailCount = 0;
let _healthIntervalId = null;
let _statusIntervalId = null;
let _pluginsIntervalId = null;
let _closePollIntervalId = null;

function _stopDashboardPolling() {
  if (_healthIntervalId) { clearInterval(_healthIntervalId); _healthIntervalId = null; }
  if (_statusIntervalId) { clearInterval(_statusIntervalId); _statusIntervalId = null; }
  if (_pluginsIntervalId) { clearInterval(_pluginsIntervalId); _pluginsIntervalId = null; }
}

function _closeWindowForShutdown() {
  _stopDashboardPolling();
  if (_sseSource) { _sseSource.close(); _sseSource = null; }
  try { window.close(); } catch (_) {}
  if (typeof pywebview !== 'undefined' && pywebview.api) {
    try { pywebview.api.approve_close(); } catch (_) {}
  }
}

async function pollShutdownStatus() {
  try {
    const data = await fetchJSON('/shutdown/status');
    _shutdownApiFailCount = 0;
    const overlay = document.getElementById('shutdown-overlay');
    const display = document.getElementById('shutdown-countdown-display');
    const shutdownNowBtn = document.getElementById('btn-shutdown-now');
    const cancelBtn = document.getElementById('btn-shutdown-cancel');

    // Once "Shutdown Now" is clicked, ignore all stale API responses
    if (_shutdownNowClicked) {
      overlay.classList.remove('hidden');
      display.textContent = 'Shutting down...';
      return;
    }

    const state = data.state || 'idle';

    overlay.classList.remove('hidden');

    if (state === 'countdown') {
      display.textContent = data.remaining_seconds + ' seconds';
      shutdownNowBtn.disabled = false;
      cancelBtn.disabled = false;
    } else if (state === 'shutting_down') {
      display.textContent = 'Shutting down...';
      shutdownNowBtn.disabled = true;
      cancelBtn.disabled = true;
      _stopDashboardPolling();
      if (_shutdownPollInterval) {
        clearInterval(_shutdownPollInterval);
        _shutdownPollInterval = null;
      }
    } else if (state === 'complete') {
      display.textContent = 'Shutdown complete. Closing...';
      _shutdownTriggered = false;
      if (_shutdownPollInterval) {
        clearInterval(_shutdownPollInterval);
        _shutdownPollInterval = null;
      }
      _closeWindowForShutdown();
    } else if (_shutdownTriggered) {
      // Backend hasn't processed our request yet (file watcher has 5s delay)
      display.textContent = 'Preparing shutdown...';
      shutdownNowBtn.disabled = true;
      cancelBtn.disabled = false;
    } else {
      // idle and not triggered
      overlay.classList.add('hidden');
      if (_shutdownPollInterval) {
        clearInterval(_shutdownPollInterval);
        _shutdownPollInterval = null;
      }
    }
  } catch (e) {
    // If API fails during shutdown, the backend is likely gone.
    // After 3 consecutive failures, close the window.
    if (_shutdownTriggered || _shutdownNowClicked) {
      _shutdownApiFailCount++;
      const overlay = document.getElementById('shutdown-overlay');
      const display = document.getElementById('shutdown-countdown-display');
      overlay.classList.remove('hidden');
      display.textContent = _shutdownNowClicked ? 'Shutting down...' : 'Preparing shutdown...';
      if (_shutdownApiFailCount >= 3) {
        display.textContent = 'Backend stopped. Closing window...';
        _closeWindowForShutdown();
      }
    }
  }
}

function startShutdownPolling() {
  _shutdownTriggered = true;
  _shutdownNowClicked = false;
  if (_shutdownPollInterval) clearInterval(_shutdownPollInterval);
  pollShutdownStatus();
  _shutdownPollInterval = setInterval(pollShutdownStatus, 1000);
}

document.getElementById('btn-shutdown-now').addEventListener('click', async () => {
  try {
    const overlay = document.getElementById('shutdown-overlay');
    const display = document.getElementById('shutdown-countdown-display');
    overlay.classList.remove('hidden');
    display.textContent = 'Shutting down...';
    document.getElementById('btn-shutdown-now').disabled = true;
    document.getElementById('btn-shutdown-cancel').disabled = true;
    const res = await fetch('/api/v1/shutdown/now', { method: 'POST' });
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    _shutdownNowClicked = true;
  } catch (e) {
    document.getElementById('btn-shutdown-now').disabled = false;
    document.getElementById('btn-shutdown-cancel').disabled = false;
    document.getElementById('shutdown-overlay').classList.add('hidden');
    showToast('Shutdown Now failed: ' + e.message, 'error');
  }
});

document.getElementById('btn-shutdown-cancel').addEventListener('click', async () => {
  _shutdownNowClicked = false;
  _shutdownTriggered = false;
  if (_shutdownPollInterval) {
    clearInterval(_shutdownPollInterval);
    _shutdownPollInterval = null;
  }
  document.getElementById('shutdown-overlay').classList.add('hidden');
  try {
    await fetch('/api/v1/shutdown/cancel', { method: 'POST' });
  } catch (e) {
    showToast('Cancel failed: ' + e.message, 'error');
  }
});

/* ─── Dialogs ─── */
function showConfirmDialog(title, message, okText = 'Confirm', okClass = 'btn-primary') {
  return new Promise((resolve) => {
    const dlg = document.getElementById('confirm-dialog');
    const titleEl = document.getElementById('confirm-title');
    const msgEl = document.getElementById('confirm-message');
    const okBtn = document.getElementById('btn-confirm-ok');
    const cancelBtn = document.getElementById('btn-confirm-cancel');

    titleEl.textContent = title;
    msgEl.textContent = message;
    okBtn.textContent = okText;
    okBtn.className = 'btn ' + okClass;

    const cleanup = () => {
      dlg.classList.add('hidden');
      okBtn.replaceWith(okBtn.cloneNode(true));
      cancelBtn.replaceWith(cancelBtn.cloneNode(true));
    };

    const newOk = okBtn.cloneNode(true);
    const newCancel = cancelBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOk, okBtn);
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);

    newOk.addEventListener('click', () => { cleanup(); resolve(true); });
    newCancel.addEventListener('click', () => { cleanup(); resolve(false); });

    dlg.classList.remove('hidden');
  });
}

/* ─── Logging ─── */
function log(msg, level = 'info') {
  const view = document.getElementById('log-view');
  const line = document.createElement('div');
  line.className = 'log-line log-' + level;
  line.textContent = new Date().toLocaleTimeString() + '  ' + msg;
  view.appendChild(line);
  view.scrollTop = view.scrollHeight;
}

function showToast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

/* ─── Dashboard ─── */
async function loadHealth() {
  try {
    const data = await fetchJSON('/health');
    const pill = document.getElementById('status-pill');
    pill.textContent = 'API v' + data.api_version;
    pill.className = 'online';
  } catch (e) {
    const pill = document.getElementById('status-pill');
    pill.textContent = 'Offline';
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

async function loadStatus() {
  try {
    const data = await fetchJSON('/status');
    const el = document.getElementById('system-info');
    if (!el) return;
    el.innerHTML =
      '<div class="field-row"><span>Server</span><span class="status-enabled">' + escapeHtml(data.server) + '</span></div>' +
      '<div class="field-row"><span>Plugins</span><span>' + data.plugins_active + ' / ' + data.plugins_total + ' active</span></div>' +
      '<div class="field-row"><span>Config</span><span>' + (data.config_loaded ? 'Loaded' : 'Not loaded') + '</span></div>' +
      '<div class="field-row"><span>Uptime</span><span>' + formatUptime(data.uptime_seconds) + '</span></div>';
  } catch (e) {
    const el = document.getElementById('system-info');
    if (el) el.innerHTML = '<span class="log-err">Failed to load status: ' + escapeHtml(e.message) + '</span>';
  }
}

function getPluginStatus(p) {
  if (!p.enabled) return { label: 'Disabled', cls: 'status-disabled' };
  return { label: 'Enabled', cls: 'status-enabled' };
}

async function loadPlugins() {
  const summary = document.getElementById('plugin-summary');
  try {
    const data = await fetchJSON('/plugins');
    currentPlugins = data.plugins || [];
    const enabled = currentPlugins.filter(p => p.enabled).length;
    if (summary) {
      summary.textContent = currentPlugins.length
        ? `${currentPlugins.length} plugins (${enabled} enabled).`
        : 'No plugins found.';
    }
    renderPluginManager();
    renderOverlayUrls();
  } catch (e) {
    if (summary) summary.textContent = 'Failed to load plugins.';
    log('Plugins load failed: ' + e.message, 'err');
  }
}

function     renderOverlayUrls() {
  const containers = [
    document.getElementById('overlay-urls'),
    document.getElementById('plugin-manager-urls')
  ];
  // Built-in overlay URLs
  let html = '<h3 style="margin:0 0 0.6rem 0;font-size:0.95rem;color:var(--text-secondary);">Built-in Overlay</h3>';
  const base = location.origin + '/api/v1/overlay';
  const overlayNames = ['default'];
  if (currentConfig.overlay && Array.isArray(currentConfig.overlay.overlays)) {
    for (const o of currentConfig.overlay.overlays) {
      if (o.name && !overlayNames.includes(o.name)) overlayNames.push(o.name);
    }
  }
  for (const name of overlayNames) {
    const u = `${base}?overlay=${name}&chroma=1`;
    html += `<div class="url-row"><span style="font-size:0.85rem;min-width:100px;">${escapeHtml(name)}</span><code>${u}</code><button class="btn-copy" onclick="copyUrl(this,'${u}')">Copy</button></div>`;
  }
  // Plugin overlay URLs
  const en = currentPlugins.filter(p => p.enabled && p.port > 0);
  if (en.length) {
    html += '<h3 style="margin:0.8rem 0 0.6rem 0;font-size:0.95rem;color:var(--text-secondary);">Plugin Overlays</h3>';
    html += en.map(p => {
      const u = `http://localhost:${p.port}`;
      return `<div class="url-row"><span style="font-size:0.85rem;min-width:100px;">${escapeHtml(p.display_name || p.name)}</span><code>${u}</code><button class="btn-copy" onclick="copyUrl(this,'${u}')">Copy</button></div>`;
    }).join('');
  }
  for (const c of containers) {
    if (c) c.innerHTML = html;
  }
}

function renderPluginManager() {
  const tableDiv = document.getElementById('plugin-manager-table');
  if (!tableDiv) return;
  if (!currentPlugins.length) {
    tableDiv.innerHTML = '<p class="muted">No plugins found.</p>';
    return;
  }
  let html = '<table class="plugin-table"><thead><tr><th>Name</th><th>Version</th><th>Port</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
  for (const p of currentPlugins) {
    const status = getPluginStatus(p);
    const action = p.enabled
      ? `<button class="btn btn-danger" style="padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="promptDisablePlugin('${p.name}', '${escapeHtml(p.display_name || p.name)}')">Disable</button>`
      : `<button class="btn btn-primary" style="padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="promptEnablePlugin('${p.name}', '${escapeHtml(p.display_name || p.name)}')">Enable</button>`;
    html += `<tr>
      <td data-label="Name">${escapeHtml(p.display_name || p.name)}</td>
      <td data-label="Version">${p.version || '-'}</td>
      <td data-label="Port">${p.port || '-'}</td>
      <td data-label="Status"><span class="plugin-status ${status.cls}">${status.label}</span></td>
      <td data-label="Actions">${action} <button class="btn btn-secondary" style="padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="pluginEditor.open('${p.name}', '${escapeHtml(p.display_name || p.name)}')">Edit Config</button></td>
    </tr>`;
  }
  html += '</tbody></table>';
  tableDiv.innerHTML = html;
}

function openPluginManager() {
  renderPluginManager();
  document.getElementById('plugin-manager').classList.remove('hidden');
}

function closePluginManager() {
  document.getElementById('plugin-manager').classList.add('hidden');
}

function copyUrl(btn, url) {
  navigator.clipboard.writeText(url).then(() => {
    btn.textContent = 'Copied';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1500);
  });
}

async function promptEnablePlugin(name, displayName) {
  const confirmed = await showConfirmDialog(
    'Enable Plugin',
    `Do you want to enable "${displayName || name}"?`,
    'Enable'
  );
  if (!confirmed) return;
  try {
    await postJSON(`/plugins/${name}/enable`, {});
    await loadPlugins();
    showToast(`Plugin "${displayName || name}" enabled.`, 'success');
    log(`Plugin ${name} enabled`);
  } catch (e) {
    const msg = 'Failed to enable "' + (displayName || name) + '": ' + e.message;
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

async function promptDisablePlugin(name, displayName) {
  const confirmed = await showConfirmDialog(
    'Disable Plugin',
    `Do you want to disable "${displayName || name}"?`,
    'Disable',
    'btn-danger'
  );
  if (!confirmed) return;
  try {
    await postJSON(`/plugins/${name}/disable`, {});
    await loadPlugins();
    showToast(`Plugin "${displayName || name}" disabled.`, 'info');
    log(`Plugin ${name} disabled`);
  } catch (e) {
    const msg = 'Failed to disable "' + (displayName || name) + '": ' + e.message;
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
    showToast(`Plugin "${displayName || name}" restarted.`, 'success');
    log(`Plugin ${name} restarted successfully.`);
  } catch (e) {
    const msg = 'Failed to restart "' + (displayName || name) + '": ' + e.message;
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

async function promptShutdown() {
  const confirmed = await showConfirmDialog(
    'Shutdown Application',
    'Are you sure you want to shut down the application?\nAll running programs and plugins will be stopped.',
    'Shutdown',
    'btn-danger'
  );
  if (!confirmed) return;
  const overlay = document.getElementById('shutdown-overlay');
  const display = document.getElementById('shutdown-countdown-display');
  overlay.classList.remove('hidden');
  display.textContent = 'Preparing shutdown...';
  document.getElementById('btn-shutdown-now').disabled = true;
  try {
    const res = await fetch('/api/v1/shutdown', { method: 'POST' });
    if (res.ok) {
      _shutdownTriggered = true;
      startShutdownPolling();
    } else {
      overlay.classList.add('hidden');
      showToast('Shutdown signal failed: ' + res.status + ' ' + res.statusText, 'error');
    }
  } catch (e) {
    overlay.classList.add('hidden');
    showToast('Shutdown signal failed: ' + e.message, 'error');
  }
}

async function loadConfig() {
  const el = document.getElementById('config-summary');
  try {
    const data = await fetchJSON('/config');
    currentConfig = data.config || {};
    const tiktok = currentConfig.tiktok || {};
    const rcon = currentConfig.rcon || {};
    el.innerHTML = `
      <div class="field-row"><span>TikTok User</span><span>${escapeHtml(tiktok.user || '—')}</span></div>
      <div class="field-row"><span>Server Host</span><span>${escapeHtml(currentConfig.server_host || '—')}</span></div>
      <div class="field-row"><span>RCON Enabled</span><span>${rcon.enabled ? 'Yes' : 'No'}</span></div>
      <div class="field-row"><span>Control Method</span><span>${escapeHtml(currentConfig.control_method || '—')}</span></div>`;
  } catch (e) {
    el.textContent = 'Failed to load configuration.';
    log('Config load failed: ' + e.message, 'err');
  }
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
  wizardStep = 0;
  wizardData = {
    tiktok_user: (currentConfig.tiktok || {}).user || '',
    rcon_password: (currentConfig.rcon || {}).password || ''
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
    <h2 style="border:none;padding:0;">${escapeHtml(title || 'Restart Required')}</h2>
    <p class="muted" style="margin-bottom:1.5rem;">${escapeHtml(message || 'Your settings have been saved. The tool must be restarted for changes to take effect.')}</p>
    <div style="display:flex;gap:1rem;justify-content:center;">
      <button class="btn btn-primary" id="btn-restart-now">Restart Now</button>
      <button class="btn btn-secondary" id="btn-restart-later">Later</button>
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
  steps.innerHTML = [0, 1, 2].map(i => `<div class="step-dot ${i === wizardStep ? 'active' : i < wizardStep ? 'done' : ''}"></div>`).join('');
  backBtn.disabled = wizardStep === 0;
  backBtn.style.visibility = wizardStep === 0 ? 'hidden' : 'visible';
  nextBtn.textContent = wizardStep === 2 ? 'Save' : 'Next';
  if (wizardStep === 0) {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">Welcome! Let's get your stream connected. Enter your TikTok username below.</p>
      <div class="form-group"><label>TikTok Username (without @)</label>
      <input type="text" id="w-tiktok-user" value="${escapeHtml(wizardData.tiktok_user)}" placeholder="your_tiktok_username">
      <div class="inline-error" id="err-tiktok-user">Please enter a valid TikTok username.</div>
      <div class="hint">The username you use when going live on TikTok.</div></div>`;
  } else if (wizardStep === 1) {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">Set a password for the Minecraft RCON connection.</p>
      <div class="form-group"><label>RCON Password</label>
      <input type="password" id="w-rcon-password" value="${escapeHtml(wizardData.rcon_password)}" placeholder="Password" oninput="updatePasswordMeter()">
      <div class="strength-meter"><div class="strength-segment"></div><div class="strength-segment"></div><div class="strength-segment"></div></div>
      <div class="strength-label" id="strength-label">Enter a password to see strength</div>
      <div class="hint">Choose any password you prefer. Strength meter is for guidance only.</div></div>`;
    setTimeout(updatePasswordMeter, 0);
  } else {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">Review your settings before saving.</p>
      <div style="background:var(--input-bg);padding:1rem;border-radius:8px;margin-bottom:1rem;">
      <div class="field-row"><span>TikTok User</span><span>${escapeHtml(wizardData.tiktok_user || '—')}</span></div>
      <div class="field-row"><span>RCON Password</span><span>${wizardData.rcon_password ? '********' : 'Not set'}</span></div></div>
      <p class="muted" style="font-size:0.85rem;margin:0;">Plugins are disabled by default. You can enable them later from the dashboard.</p>`;
  }
}
function validatePassword(pass) {
  const issues = [];
  if (pass.length < 8) issues.push('At least 8 characters');
  if (!/[A-Z]/.test(pass)) issues.push('One uppercase letter (A-Z)');
  if (!/[a-z]/.test(pass)) issues.push('One lowercase letter (a-z)');
  if (!/[0-9]/.test(pass)) issues.push('One number (0-9)');
  if (!/[^A-Za-z0-9]/.test(pass)) issues.push('One special character (!@#$ etc.)');
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
    if (strength === 'weak') { segments[0].classList.add('weak'); label.textContent = 'Weak'; label.style.color = 'var(--danger)'; }
    else if (strength === 'medium') { segments[0].classList.add('medium'); segments[1].classList.add('medium'); label.textContent = 'Medium'; label.style.color = 'var(--warning)'; }
    else { segments.forEach(s => s.classList.add('strong')); label.textContent = 'Strong'; label.style.color = 'var(--success)'; }
  } else { label.textContent = 'Enter a password to see strength'; label.style.color = 'var(--text-secondary)'; }
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
    wizardData.rcon_password = passInput.value;
  }
  if (wizardStep === 2) { await wizardSave(); return; }
  wizardStep++;
  renderWizardStep();
}
async function wizardSave() {
  const nextBtn = document.getElementById('wizard-next');
  nextBtn.disabled = true;
  nextBtn.textContent = 'Saving...';
  try {
    const cfgData = await fetchJSON('/config');
    const cfg = cfgData.config || {};
    if (!cfg.tiktok) cfg.tiktok = {};
    cfg.tiktok.user = wizardData.tiktok_user;
    if (!cfg.rcon) cfg.rcon = {};
    cfg.rcon.password = wizardData.rcon_password;
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
    showToast('Setup complete — settings applied.', 'success');
  } catch (e) {
    log('Failed to save setup: ' + e.message, 'err');
    showToast('Failed to save: ' + e.message, 'error');
  } finally { nextBtn.disabled = false; nextBtn.textContent = 'Save'; }
}
function _showRestartOverlay() {
  _stopDashboardPolling();
  if (_sseSource) { _sseSource.close(); _sseSource = null; }
  const card = document.querySelector('#restart-dialog .wizard-card');
  if (card) {
    card.innerHTML = '<h2 style="border:none;padding:0;">Restarting...</h2><p class="muted">Please wait while the backend services restart.</p>';
  }
  document.getElementById('restart-dialog').classList.remove('hidden');
}

async function triggerRestart() {
  _restartPending = true;
  updateRestartBanner();
  try {
    const res = await fetch('/api/v1/restart', { method: 'POST' });
    if (res.ok) {
      _showRestartOverlay();
      // The supervisor keeps the API server alive and publishes
      // server.restarting / server.started events via SSE.  If the
      // browser misses the events, fall back to a timeout.
      _waitForRestartCompletion();
    } else {
      _restartPending = false;
      updateRestartBanner();
      showToast('Restart signal failed. Please restart manually.', 'error');
      document.getElementById('restart-dialog').classList.add('hidden');
    }
  } catch (e) {
    _restartPending = false;
    updateRestartBanner();
    showToast('Restart signal failed. Please restart manually.', 'error');
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
document.getElementById('wizard-back').addEventListener('click', () => { if (wizardStep > 0) { wizardStep--; renderWizardStep(); } });
document.getElementById('wizard-next').addEventListener('click', wizardNext);

/* ─── Config Editor ─── */

const SECTION_ORDER = [
  'tiktok','rcon','server_host','control_method',
  'java','minecraft_server_api',
  'console',
  'overlay',
  'theme',
  'update','shutdown','auto_update_config','show_sudo_warning','gui',
  'plugin_sandbox',
  'port_policy','api_key',
  'comment_commands','random_triggers'
];

const CATEGORIES = {
  'Connection': ['tiktok','rcon','server_host','control_method','api_key'],
  'Minecraft': ['java','minecraft_server_api'],
  'System': ['console','update','shutdown','auto_update_config','show_sudo_warning','gui','plugin_sandbox','port_policy'],
  'Appearance': ['overlay','theme'],
  'Chat & Commands': ['comment_commands','random_triggers']
};

const SECTION_META = {
  tiktok: { title: 'TikTok Live', desc: 'Connect the tool to your TikTok live stream. Set your username and connection behavior.', category: 'Connection' },
  rcon: { title: 'Remote Console (RCON)', desc: 'RCON allows the tool to send commands to your Minecraft server. Keep this enabled.', category: 'Connection' },
  java: { title: 'Minecraft Server', desc: 'Controls how much RAM the Minecraft server uses and which port it runs on.', category: 'Minecraft' },
  comment_commands: { title: 'Chat Commands', desc: 'Let viewers send commands via TikTok chat. You can create multiple groups with different prefixes, roles, and rules.', category: 'Chat & Commands' },
  random_triggers: { title: 'Random Trigger Filter', desc: 'Controls which triggers can be selected by the $random action in data/actions.mca.', category: 'Chat & Commands' },
  console: { title: 'Console Visibility', desc: 'Controls which windows and processes are shown when the tool starts.', category: 'System' },
  minecraft_server_api: { title: 'Minecraft Server API', desc: 'Handles communication between the tool and the Minecraft server. Required for player death/respawn detection.', category: 'Minecraft' },
  gui: { title: 'Dashboard', desc: 'The graphical user interface is served by the central API server and shown in a window.', category: 'System' },
  overlay: { title: 'Overlay Text', desc: 'Built-in overlay subsystem for displaying text messages on stream. Runs as a core component, not a plugin.', category: 'Appearance' },
  theme: { title: 'Overlay Colors', desc: 'Customize colors for overlays. All values are CSS hex codes like #ff0000.', category: 'Appearance' },
  update: { title: 'Auto-Updater', desc: 'Checks for new versions on startup and installs them automatically. Strongly recommended.', category: 'System' },
  shutdown: { title: 'Auto-Shutdown', desc: 'Automatically shuts down the tool after your live stream ends.', category: 'System' },
  server_host: { title: 'Server Address', desc: 'Controls which network interfaces the tool listens on.', category: 'Connection' },
  control_method: { title: 'Control Method', desc: 'How the tool communicates with your streaming software.', category: 'Connection' },
  auto_update_config: { title: 'Auto-Update Config', desc: 'Automatically merge new options when the tool updates.', category: 'System' },
  show_sudo_warning: { title: 'Sudo Warning', desc: 'Linux only. Warns if running without sudo, which can cause permission issues.', category: 'System' },
  port_policy: { title: 'Port Policy', desc: 'Controls what happens when a required port is already in use. Can auto-resolve to the next free port.', category: 'System' },
  api_key: { title: 'API Key', desc: 'Optional API key for authentication when the server is exposed beyond localhost.', category: 'Connection' },
  plugin_sandbox: { title: 'Plugin Sandbox', desc: 'Restricts plugin subprocess resources to limit the impact of misbehaving or compromised plugins.', category: 'System' }
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
  'tiktok.user': 'Your TikTok username — without the @ symbol. This is required for the tool to connect to your live stream.',
  'tiktok.reconnect_delay_seconds': 'Seconds to wait before attempting to reconnect after a connection loss.',
  'tiktok.autosave_interval_seconds': 'How often (in seconds) the gift revenue log file is saved to disk. The log is stored at data/gift_revenue_log.jsonl.',
  'tiktok.follow_tracking.mode': 'all_time tracks follows across ALL streams. Once a user is recorded, their future follows are ignored even after restarting. per_stream resets the list every time the tool starts.',
  'tiktok.follow_tracking.file': 'Path to the file storing tracked follower names. Default: data/followed_users.txt.',
  'comment_commands.enabled': 'Master switch — set to true to let viewers send commands via chat. Each group below processes matching comments independently.',
  'comment_commands.cooldown': 'Global cooldown across ALL groups. If set to 10, a viewer who runs $skip must wait 10 seconds before ANY command works. Set to 0 to disable.',
  'comment_commands.user_cooldown': 'Global user cooldown — like global cooldown, but per user. If set to 30, a viewer must wait 30 seconds before THEIR NEXT command in any group. Set to 0 to disable.',
  'comment_commands.groups': 'Define one or more command groups. Each group has its own prefix, role requirements, allow/deny rules, dispatch target, and cooldowns.',
  'comment_commands.groups[].enabled': 'Turn this command group on or off.',
  'comment_commands.groups[].prefix': 'The character that triggers this group. For example: # for Minecraft commands or $ for Spotify.',
  'comment_commands.groups[].allowed_roles': 'Who can use commands in this group. Options: all, moderator, superfan, fanclub. Be careful with "all" — anyone in chat can use these commands.',
  'comment_commands.groups[].mode': 'deny-all means ONLY the listed commands work. allow-all means ALL commands work EXCEPT the listed ones. deny-all is safer for public access.',
  'comment_commands.groups[].commands': 'List of base command names to allow or block, depending on the mode above.',
  'comment_commands.groups[].commands_config': 'Per-command overrides for points cost, cooldown, roles, URL, and handler. Only needed if you want special settings for specific commands.',
  'comment_commands.groups[].handler': 'rcon sends commands to your Minecraft server. http sends them to a web URL.',
  'comment_commands.groups[].cooldown': 'Seconds to wait between ANY command in this group. Set to 0 to disable.',
  'comment_commands.groups[].user_cooldown': 'Seconds the SAME viewer must wait before their next command in this group. Set to 0 to disable.',
  'comment_commands.groups[].trigger_comment_event': 'Also fire the "comment" trigger in actions.mca when a command is used? Default: true.',
  'comment_commands.groups[].url': 'HTTP endpoint that receives the command. You can use placeholders: {user} = viewer name, {text} = command text.',
  'comment_commands.groups[].commands_config[].points_cost': 'Points cost — viewer needs this many channel points to use this command. Set to 0 to make it free.',
  'comment_commands.groups[].commands_config[].cooldown': 'Per-command cooldown in seconds. Overrides the group cooldown.',
  'comment_commands.groups[].commands_config[].conditional': 'When true: points and cooldowns only apply if the command succeeds. If it fails, nothing is deducted and no cooldown is set.',
  'comment_commands.groups[].commands_config[].url': 'Direct URL for this specific command. This bypasses the group URL.',
  'comment_commands.groups[].commands_config[].handler': 'Override the handler for this command: rcon or http.',
  'comment_commands.groups[].commands_config[].roles': 'Per-command role override. Replaces the group allowed_roles for this command only.',
  'random_triggers.mode': 'deny-all means ONLY triggers in the list are eligible for $random. allow-all means ALL triggers are eligible EXCEPT those in the list.',
  'random_triggers.triggers': 'List of trigger names. Which ones are used depends on the mode. Triggers containing "$random" are automatically excluded to prevent infinite recursion.',
  'console.log_level': 'Visibility level: 0 = Hide everything, 1 = Silent (hide console, keep GUI), 2 = Standard (recommended), 3 = Advanced, 4 = Debug, 5 = Override (debugging only).',
  'console.visible': 'Show or hide the main console window when the tool starts.',
  'console.allow_close': 'If true, typing "exit" in the console shuts everything down cleanly. If false, the launcher exits immediately after starting programs.',
  'minecraft_server_api.enabled': 'Required for player death/respawn detection and datapack loading. Keep enabled unless you know you do not need these features.',
  'minecraft_server_api.api_port': 'Port for the internal Minecraft API bridge. Default: 29187.',
  'minecraft_server_api.web_server_port': 'Port for the webhook server that receives Minecraft events. Default: 29188.',
  'gui.enabled': 'Launch the graphical dashboard on startup. If disabled, you can still open it manually.',
  'update.enabled': 'Checks for new versions on startup and installs them automatically. It is strongly recommended to keep this enabled.',
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
  'plugin_sandbox.max_memory_mb': 'Maximum RAM per plugin process in megabytes.',
  'plugin_sandbox.max_cpu_time': 'Maximum CPU seconds per plugin (Linux only).',
  'plugin_sandbox.max_files': 'Maximum open file descriptors per plugin (Linux only).',
  'plugin_sandbox.max_processes': 'Maximum child processes per plugin (Linux only).',
  'plugin_sandbox.priority_class': 'Windows process priority for plugin subprocesses. below_normal reduces impact on the main tool.'
};

const FIELD_META = {
  'config_version': { basic: false, readonly: true, type: 'text' },
  'auto_update_config': { basic: true, type: 'bool' },
  'show_sudo_warning': { basic: false, type: 'bool' },
  'server_host': { basic: true, type: 'text', required: true },
  'control_method': { basic: true, type: 'select', options: ['DCS','ICS'] },
  'shutdown.enabled': { basic: true, type: 'bool' },
  'shutdown.delay_seconds': { basic: true, type: 'number', min: 0, max: 3600 },
  'java.xms': { basic: true, type: 'text', pattern: /^\d+[GgMm]$/ },
  'java.xmx': { basic: true, type: 'text', pattern: /^\d+[GgMm]$/ },
  'java.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'rcon.enabled': { basic: true, type: 'bool' },
  'rcon.password': { basic: true, type: 'password', required: true },
  'rcon.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'tiktok.user': { basic: true, type: 'text', required: true },
  'tiktok.reconnect_delay_seconds': { basic: false, type: 'number', min: 0 },
  'tiktok.autosave_interval_seconds': { basic: false, type: 'number', min: 1 },
  'tiktok.follow_tracking.mode': { basic: false, type: 'select', options: ['all_time','per_stream'] },
  'tiktok.follow_tracking.file': { basic: false, type: 'text' },
  'comment_commands.enabled': { basic: true, type: 'bool' },
  'comment_commands.cooldown': { basic: false, type: 'number', min: 0 },
  'comment_commands.user_cooldown': { basic: false, type: 'number', min: 0 },
  'random_triggers.mode': { basic: false, type: 'select', options: ['deny-all','allow-all'] },
  'console.log_level': { basic: false, type: 'number', min: 0, max: 5 },
  'console.visible': { basic: false, type: 'bool' },
  'console.allow_close': { basic: false, type: 'bool' },
  'minecraft_server_api.enabled': { basic: true, type: 'bool' },
  'minecraft_server_api.api_port': { basic: false, type: 'number', min: 1, max: 65535 },
  'minecraft_server_api.web_server_port': { basic: false, type: 'number', min: 1, max: 65535 },
  'gui.enabled': { basic: true, type: 'bool' },
  'update.enabled': { basic: true, type: 'bool' },
  'update.max_update_logs': { basic: false, type: 'number' },
  'overlay.enabled': { basic: true, type: 'bool' },
  'overlay.display_mode': { basic: true, type: 'select', options: ['overwrite','queue'] },
  'overlay.fade_in': { basic: false, type: 'number', min: 0 },
  'overlay.fade_out': { basic: false, type: 'number', min: 0 },
  'overlay.max_fails': { basic: false, type: 'number', min: 1 },
  'overlay.cooldown': { basic: false, type: 'number', min: 0 },
  'overlay.overlays': { basic: false, type: 'json' },
  'overlay.theme.background': { basic: false, type: 'color' },
  'overlay.theme.text': { basic: false, type: 'color' },
  'comment_commands.groups[].enabled': { basic: false, type: 'bool' },
  'comment_commands.groups[].prefix': { basic: false, type: 'text' },
  'comment_commands.groups[].handler': { basic: false, type: 'select', options: ['rcon','http'] },
  'comment_commands.groups[].mode': { basic: false, type: 'select', options: ['deny-all','allow-all'] },
  'comment_commands.groups[].cooldown': { basic: false, type: 'number', min: 0 },
  'comment_commands.groups[].user_cooldown': { basic: false, type: 'number', min: 0 },
  'comment_commands.groups[].trigger_comment_event': { basic: false, type: 'bool' },
  'comment_commands.groups[].url': { basic: false, type: 'text' },
  'api_key': { basic: true, type: 'password' },
  'port_policy.auto_resolve': { basic: true, type: 'bool' },
  'port_policy.session_only': { basic: true, type: 'bool' },
  'port_policy.max_offset': { basic: false, type: 'number', min: -1 },
  'plugin_sandbox.enabled': { basic: true, type: 'bool' },
  'plugin_sandbox.max_memory_mb': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.max_cpu_time': { basic: false, type: 'number', min: 0 },
  'plugin_sandbox.max_files': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.max_processes': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.priority_class': { basic: false, type: 'select', options: ['below_normal', 'idle'] }
};

function getMeta(path) {
  if (FIELD_META[path]) return FIELD_META[path];
  const p = path.replace(/\.groups\[\d+\]/, '.groups[]').replace(/\.triggers\[\d+\]/, '.triggers[]').replace(/\.overlays\[\d+\]/, '.overlays[]').replace(/\.commands_config\.\w+/, '.commands_config[]');
  return FIELD_META[p] || { basic: false, type: 'text' };
}

function getHelp(path) {
  if (HELP_TEXT[path]) return HELP_TEXT[path];
  const p = path.replace(/\.groups\[\d+\]/, '.groups[]').replace(/\.triggers\[\d+\]/, '.triggers[]').replace(/\.overlays\[\d+\]/, '.overlays[]').replace(/\.commands_config\.\w+/, '.commands_config[]');
  return HELP_TEXT[p] || '';
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
  }

  open(config) {
    this.original = JSON.parse(JSON.stringify(config));
    this.data = JSON.parse(JSON.stringify(config));
    this.unknownKeys = {};
    this.originalUnknownKeys = {};
    this.errors.clear();
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
    // Overlay preview auto-refresh when inputs change
    if (this._overlayInputHandler) return;
    this._overlayInputHandler = (e) => {
      if (!document.getElementById('overlay-preview-editor-frame')) return;
      if (this._overlayTimer) clearTimeout(this._overlayTimer);
      this._overlayTimer = setTimeout(() => this.refreshEditorPreview(), 600);
    };
    this.content.addEventListener('input', this._overlayInputHandler);
  }

  _detachInputListeners() {
    if (!this._inputHandler) return;
    this.content.removeEventListener('input', this._inputHandler);
    this.content.removeEventListener('change', this._inputHandler);
    this._inputHandler = null;
    if (this._inputTimer) { clearTimeout(this._inputTimer); this._inputTimer = null; }
    if (this._overlayInputHandler) {
      this.content.removeEventListener('input', this._overlayInputHandler);
      this._overlayInputHandler = null;
    }
    if (this._overlayTimer) { clearTimeout(this._overlayTimer); this._overlayTimer = null; }
  }

  close() {
    if (this.isDirty()) {
      showConfirmDialog('Unsaved Changes', 'You have unsaved changes. Close anyway?', 'Close', 'btn-danger').then(confirmed => {
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
      if (key === 'config_version') {
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
    let html = '<div class="sidebar-header">Navigation</div>';
    for (const [cat, keys] of Object.entries(CATEGORIES)) {
      const visibleKeys = keys.filter(k => k in this.data);
      if (!visibleKeys.length) continue;
      html += '<div class="sidebar-group">';
      html += `<div class="sidebar-group-title">${escapeHtml(cat)}</div>`;
      for (const key of visibleKeys) {
        const meta = SECTION_META[key] || { title: toTitle(key) };
        const hasErr = this.sectionHasError(key);
        const isActive = this.activeSection === key;
        html += `<a class="sidebar-item ${hasErr ? 'has-error' : ''} ${isActive ? 'active' : ''}" onclick="editor.scrollTo('section_${key}')">${escapeHtml(meta.title)}${hasErr ? '<span class="badge">!</span>' : ''}</a>`;
      }
      html += '</div>';
    }
    if (Object.keys(this.unknownKeys).length) {
      html += '<div class="sidebar-group">';
      html += '<div class="sidebar-group-title">Other</div>';
      const isActive = this.activeSection === '_unknown';
      html += `<a class="sidebar-item ${this.sectionHasError('_unknown') ? 'has-error' : ''} ${isActive ? 'active' : ''}" onclick="editor.scrollTo('section_unknown')">Unrecognized Settings</a>`;
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
      html = `<div class="search-empty"><h3>No results</h3><p>No settings match your search.</p></div>`;
    }
    this.content.innerHTML = html;
  }

  sectionMatchesSearch(key) {
    const meta = SECTION_META[key] || {};
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
    const meta = SECTION_META[key] || { title: toTitle(key), desc: '' };
    let body = '';
    if (key === 'theme') {
      body = this.buildThemeEditor(key, value);
    } else if (key === 'overlay') {
      body = this.buildOverlayEditor(key, value);
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
        if (path === 'comment_commands.groups') {
          html += this.buildGroupEditor(path, v);
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

  buildField(key, value, path) {
    const meta = getMeta(path);
    const label = toTitle(key);
    const help = getHelp(path);
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const isReq = meta.required;

    let inputHtml = '';
    if (meta.readonly) {
      inputHtml = `<input type="text" id="${id}" value="${escapeHtml(value !== undefined ? String(value) : '')}" data-path="${path}" data-type="string" readonly style="opacity:0.6;cursor:not-allowed;">`;
    } else if (meta.type === 'bool' || (meta.type === undefined && typeof value === 'boolean')) {
      inputHtml = `<input type="checkbox" class="toggle" id="${id}" ${value ? 'checked' : ''} data-path="${path}" data-type="bool">`;
    } else if (meta.type === 'select') {
      const onch = path.endsWith('.handler') ? ' onchange="editor.render()"' : '';
      inputHtml = `<select id="${id}" data-path="${path}" data-type="string"${onch}>${meta.options.map(o => `<option value="${o}" ${value === o ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
    } else if (meta.type === 'password') {
      inputHtml = `<input type="password" id="${id}" value="${escapeHtml(value || '')}" data-path="${path}" data-type="string">`;
    } else if (meta.type === 'number') {
      inputHtml = `<input type="number" id="${id}" value="${value !== undefined ? value : ''}" data-path="${path}" data-type="number"${meta.min !== undefined ? ` min="${meta.min}"` : ''}${meta.max !== undefined ? ` max="${meta.max}"` : ''}>`;
    } else {
      inputHtml = `<input type="text" id="${id}" value="${escapeHtml(value !== undefined ? String(value) : '')}" data-path="${path}" data-type="string">`;
    }

    const err = this.errors.get(path) || '';
    return `<div class="editor-field" data-path="${path}">
      <div class="field-label">${escapeHtml(label)}${isReq ? '<span class="required">*</span>' : ''}</div>
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

  buildGroupEditor(path, groups) {
    const help = getHelp(path);
    let cards = (groups || []).map((g, i) => this.buildGroupCard(path, g, i)).join('');
    return `<div class="editor-field full-width" data-path="${path}">
      <div class="field-label">Command Groups</div>
      <div class="field-widget">
        ${cards}
        <button class="btn btn-secondary" onclick="editor.addGroup('${path}')">Add Group</button>
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
      </div>
    </div>`;
  }

  buildGroupCard(path, g, i) {
    const p = `${path}[${i}]`;
    const roles = (g.allowed_roles || []).map(r => `<span class="tag-chip">${escapeHtml(r)}</span>`).join('');
    return `<div class="group-card" id="${p.replace(/[^a-zA-Z0-9]/g, '_')}">
      <div class="group-header"><h4>Group ${i + 1} — Prefix "${escapeHtml(g.prefix || '')}"</h4><button class="btn-icon" onclick="editor.removeArrayItem('${path}', ${i})">Remove</button></div>
      <div class="group-body">
        ${this.buildField('enabled', g.enabled, `${p}.enabled`)}
        ${this.buildField('prefix', g.prefix, `${p}.prefix`)}
        ${this.buildField('handler', g.handler, `${p}.handler`)}
        ${this.buildField('mode', g.mode, `${p}.mode`)}
        ${g.handler === 'http' ? this.buildField('url', g.url, `${p}.url`) : ''}
        ${this.buildRoleSelector(`${p}.allowed_roles`, g.allowed_roles)}
        ${this.buildTagEditor(`${p}.commands`, g.commands || [], { label: 'Commands' })}
        ${this.buildField('cooldown', g.cooldown, `${p}.cooldown`)}
        ${this.buildField('user_cooldown', g.user_cooldown, `${p}.user_cooldown`)}
        ${this.buildField('trigger_comment_event', g.trigger_comment_event, `${p}.trigger_comment_event`)}
        ${this.buildCommandsConfig(`${p}.commands_config`, g.commands_config, g.commands || [])}
      </div>
    </div>`;
  }

  buildCommandsConfig(path, cfg, commands) {
    const help = getHelp(path);
    let config = cfg;
    if (Array.isArray(config)) config = {};
    if (!commands.length) {
      return `<div class="editor-field full-width" data-path="${path}">
        <div class="field-label">Command Overrides</div>
        <div class="field-widget"><p class="field-desc">No commands defined in this group yet. Add commands above to configure per-command overrides.</p></div>
      </div>`;
    }
    let html = `<div class="editor-field full-width" data-path="${path}"><div class="field-label">Command Overrides</div><div class="field-widget">`;
    for (const cmd of commands) {
      const c = config[cmd] || {};
      const overrideKeys = Object.keys(c).filter(k => k !== 'undefined');
      let fieldsHtml = '';
      for (const key of overrideKeys) {
        fieldsHtml += this.buildOverrideWidget(key, c[key], `${path}.${cmd}.${key}`);
      }
      const used = new Set(overrideKeys);
      const available = ['points_cost','cooldown','user_cooldown','conditional','url','handler','roles'].filter(k => !used.has(k));
      html += `<details style="margin-bottom:0.6rem;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:0.6rem;">
        <summary style="cursor:pointer;font-size:0.9rem;font-weight:500;">${escapeHtml(cmd)}</summary>
        <div style="padding:0.6rem 0.25rem 0.2rem 0.25rem;">
          ${fieldsHtml}
          ${available.length ? `<div style="margin-top:0.5rem;"><select onchange="editor.addOverride('${path}.${cmd}', this.value);this.value=''" style="padding:0.35rem 0.5rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.85rem;"><option value="">+ Add override...</option>${available.map(k => `<option value="${k}">${toTitle(k)}</option>`).join('')}</select></div>` : ''}
        </div>
      </details>`;
    }
    html += `${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}</div></div>`;
    return html;
  }

  buildOverrideWidget(key, value, path) {
    const label = toTitle(key);
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    let widget = '';

    if (key === 'roles') {
      const roles = ['all','moderator','superfan','fanclub'];
      const current = value || [];
      const boxes = roles.map(r => {
        const checked = current.includes(r) ? 'checked' : '';
        return `<label style="margin-right:0.75rem;font-size:0.85rem;"><input type="checkbox" ${checked} data-role="${r}" onchange="editor.onRoleChange('${path}', this)">${toTitle(r)}</label>`;
      }).join('');
      widget = `<div>${boxes}</div>`;
    } else if (key === 'conditional') {
      widget = `<input type="checkbox" class="toggle" id="${id}" ${value ? 'checked' : ''} data-path="${path}" data-type="bool">`;
    } else if (key === 'handler') {
      widget = `<select id="${id}" data-path="${path}" data-type="string" style="padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);"><option value="">(inherit from group)</option><option value="rcon" ${value==='rcon'?'selected':''}>rcon</option><option value="http" ${value==='http'?'selected':''}>http</option></select>`;
    } else if (key === 'points_cost' || key === 'cooldown' || key === 'user_cooldown') {
      widget = `<input type="number" id="${id}" value="${value !== undefined && value !== '' ? escapeHtml(String(value)) : ''}" data-path="${path}" data-type="number" style="width:100%;padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);">`;
    } else {
      widget = `<input type="text" id="${id}" value="${escapeHtml(value || '')}" data-path="${path}" data-type="string" style="width:100%;padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);">`;
    }

    return `<div style="margin-bottom:0.6rem;padding:0.5rem;background:var(--elevated);border-radius:4px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.3rem;">
        <span style="font-size:0.85rem;color:var(--text);font-weight:500;">${escapeHtml(label)}</span>
        <button class="btn-icon" style="font-size:0.85rem;" onclick="editor.removeOverride('${path}')">Remove</button>
      </div>
      ${widget}
    </div>`;
  }

  addOverride(cmdPath, key) {
    const keys = cmdPath.split(/\.|\[(\d+)\]/).filter(k => k !== '' && k !== undefined);
    let target = this.data;
    for (let i = 0; i < keys.length - 1; i++) {
      const k = keys[i];
      if (!(k in target)) target[k] = {};
      target = target[k];
    }
    const last = keys[keys.length - 1];
    if (!target[last] || typeof target[last] !== 'object' || Array.isArray(target[last])) target[last] = {};
    let defaultValue = '';
    if (key === 'points_cost' || key === 'cooldown') defaultValue = 0;
    else if (key === 'conditional') defaultValue = false;
    else if (key === 'roles') defaultValue = [];
    target[last][key] = defaultValue;
    this._preserveDetailsAndRender();
  }

  removeOverride(path) {
    const keys = path.split(/\.|\[(\d+)\]/).filter(k => k !== '' && k !== undefined);
    let target = this.data;
    for (let i = 0; i < keys.length - 1; i++) {
      const k = keys[i];
      if (!(k in target)) return;
      target = target[k];
    }
    const last = keys[keys.length - 1];
    delete target[last];
    this._preserveDetailsAndRender();
  }

  _preserveDetailsAndRender() {
    // Speichere offene <details> anhand ihrer Summary-Texte
    const openSet = new Set();
    for (const details of this.content.querySelectorAll('details')) {
      if (details.open && details.querySelector('summary')) {
        openSet.add(details.querySelector('summary').textContent.trim());
      }
    }
    this.render();
    // Wiederherstellen
    for (const details of this.content.querySelectorAll('details')) {
      const summary = details.querySelector('summary');
      if (summary && openSet.has(summary.textContent.trim())) {
        details.open = true;
      }
    }
  }

  addGroup(path) {
    const arr = this.getValue(path) || [];
    arr.push({ enabled: true, prefix: '#', allowed_roles: ['moderator'], mode: 'deny-all', commands: [], commands_config: {}, handler: 'rcon', cooldown: 0, user_cooldown: 0, trigger_comment_event: true });
    this.setValue(path, arr);
    this.render();
  }

  buildThemeEditor(path, theme) {
    const pluginKeys = new Set(['death_counter','win_counter','timer','spotify']);
    let html = '';
    for (const [plugin, colors] of Object.entries(theme || {})) {
      if (pluginKeys.has(plugin)) continue; // plugin colors are managed in their own configs
      html += `<div style="margin-bottom:1.5rem;"><strong style="font-size:0.95rem;color:var(--text);display:block;margin-bottom:0.5rem;">${escapeHtml(toTitle(plugin))}</strong>`;
      for (const [ckey, cval] of Object.entries(colors)) {
        const p = `${path}.${plugin}.${ckey}`;
        const id = 'f_' + p.replace(/[^a-zA-Z0-9]/g, '_');
        html += `<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem;">
          <span style="font-size:0.85rem;color:var(--text-secondary);min-width:100px;">${escapeHtml(toTitle(ckey))}</span>
          <input type="color" id="${id}" value="${cval}" data-path="${p}" data-type="string" oninput="document.getElementById('${id}_hex').value=this.value">
          <input type="text" id="${id}_hex" value="${escapeHtml(cval)}" style="width:120px;padding:0.45rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:monospace;font-size:0.9rem;" oninput="document.getElementById('${id}').value=this.value">
        </div>`;
      }
      html += '</div>';
    }
    return html;
  }

  buildOverlayEditor(path, overlay) {
    const fields = this.buildObjectFields(path, overlay);
    const bgId = 'f_' + (path + '.theme.background').replace(/[^a-zA-Z0-9]/g, '_');
    const txtId = 'f_' + (path + '.theme.text').replace(/[^a-zA-Z0-9]/g, '_');
    return fields + `
      <div class="overlay-editor-preview">
        <h4>Live Preview</h4>
        <div class="overlay-editor-preview-wrap">
          <iframe id="overlay-preview-editor-frame" sandbox="allow-scripts" srcdoc="<html><body style='margin:0;background:#111;display:flex;align-items:center;justify-content:center;height:100vh;color:#666;font-family:sans-serif;font-size:14px;'>Adjust colors above to see preview</body></html>"></iframe>
        </div>
        <div class="overlay-editor-toolbar">
          <button class="btn btn--primary btn--sm" onclick="editor.refreshEditorPreview()" type="button">Update Preview</button>
          <button class="btn btn--secondary btn--sm" onclick="sendTestOverlay()" type="button">Send Test</button>
          <span style="font-size:0.78rem;color:var(--text-secondary);margin-left:auto;">Colors update on input, then click Refresh</span>
        </div>
        <div class="overlay-editor-test-form">
          <input type="text" id="overlay-test-title" value="Hello Stream!" placeholder="Title" style="flex:2;">
          <input type="text" id="overlay-test-subtitle" value="from Viewer123" placeholder="Subtitle" style="flex:2;">
          <input type="number" id="overlay-test-duration" value="3" placeholder="Secs" min="1" max="30" style="width:70px;">
          <button class="btn btn--primary btn--sm" onclick="sendTestOverlay()" type="button">Send</button>
        </div>
      </div>`;
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
      this.showToast('Unrecognized settings updated from YAML.', 'info');
    } catch (e) {
      this.showToast('Failed to parse YAML: ' + e.message, 'error');
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
      this.showToast('Please fix the highlighted errors before saving.', 'error');
      return;
    }
    this.mergeUnknownKeys();
    const diff = this.computeDiff();
    if (!diff.length) {
      this.showToast('No changes to save.', 'info');
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

      await putJSON('/config', { config: this.data, backup: true });
      this.original = JSON.parse(JSON.stringify(this.data));
      currentConfig = JSON.parse(JSON.stringify(this.data));
      this._updateSaveButton();
      this.close();
      await loadConfig();
      await postJSON('/reload', {});
      if (rconPasswordSet) {
        await postJSON('/server/restart', {});
      }
      this.showToast('Configuration saved and applied.', 'success');
    } catch (e) {
      this.showToast('Save failed: ' + e.message, 'error');
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
          if (v !== o) changes.push({ path: p, old: o === undefined ? '(none)' : o, new: v === undefined ? '(none)' : v });
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

  async refreshEditorPreview() {
    const frame = document.getElementById('overlay-preview-editor-frame');
    if (!frame) return;
    this.collect();
    const overlay = this.data.overlay || {};
    const theme = (overlay.theme || {});
    try {
      const res = await fetch(API + '/overlay/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chroma: true, theme: { background: theme.background, text: theme.text } })
      });
      const data = await res.json();
      frame.srcdoc = data.html;
    } catch (e) {
      this.showToast('Preview update failed: ' + e.message, 'error');
    }
  }
}

const editor = new ConfigEditor();

/* ─── Utilities ─── */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
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
    this.activeCategory = null;
    this.hasSchema = false;
  }

  async open(pluginName, displayName) {
    this.pluginName = pluginName;
    this.displayName = displayName || pluginName;
    this.searchQuery = '';
    document.getElementById('plugin-editor-search').value = '';
    this.errors.clear();

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
      this.showToast('Failed to load config: ' + e.message, 'error');
      return;
    }

    document.getElementById('plugin-editor-title').textContent = escapeHtml(this.displayName) + ' Configuration';
    this.render();
    document.getElementById('plugin-config-editor').classList.remove('hidden');
    this.setupScrollSpy();
    this._updateSaveButton();
    this._attachInputListeners();
  }

  isDirty() {
    return JSON.stringify(this.config) !== JSON.stringify(this.original);
  }

  _updateSaveButton() {
    const btn = document.getElementById('plugin-editor-save');
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
    if (this.isDirty()) {
      showConfirmDialog('Unsaved Changes', 'You have unsaved changes. Close anyway?', 'Close', 'btn-danger').then(confirmed => {
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
    const path = field.key;
    const id = 'pf_' + path.replace(/[^a-zA-Z0-9]/g, '_');
    const isReq = field.required;
    const label = field.label || toTitle(path.split('.').pop());
    const help = field.help || '';
    const err = this.errors.get(path) || '';

    let widget = '';
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

    return `<div class="editor-field" data-path="${escapeHtml(path)}">
      <div class="field-label">${escapeHtml(label)}${isReq ? '<span class="required">*</span>' : ''}</div>
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
      this.showToast('JSON is valid.', 'info');
    } catch (e) {
      this.showToast('Invalid JSON: ' + e.message, 'error');
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
      catch (e) { this.showToast('Invalid configuration: ' + e.message, 'error'); return false; }
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
      this.showToast('Please fix the highlighted errors before saving.', 'error');
      return;
    }
    const diff = this.computeDiff();
    if (!diff.length) {
      this.showToast('No changes to save.', 'info');
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
      this.showToast('Plugin configuration saved successfully.', 'success');
      // Only prompt to restart if the plugin is currently enabled
      // Disabled plugins should not trigger restart/reload prompts
      const plugin = currentPlugins.find(p => p.name === this.pluginName);
      if (plugin && plugin.enabled) {
        const display = this.displayName || this.pluginName;
        setTimeout(async () => {
          const confirmed = await showConfirmDialog(
            'Restart Plugin?',
            `Plugin "${display}" configuration updated.\n\nChanges may require the plugin to reload.\n\nRestart plugin now?`,
            'Restart Now'
          );
          if (confirmed) {
            restartPlugin(this.pluginName, display);
          }
        }, 300);
      }
    } catch (e) {
      this.showToast('Save failed: ' + e.message, 'error');
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
      this.showToast('Plugin configuration saved successfully.', 'success');
    } catch (e) {
      this.showToast('Save failed: ' + e.message, 'error');
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
          if (v !== o) changes.push({ path: p, old: o === undefined ? '(none)' : o, new: v === undefined ? '(none)' : v });
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
    this.wizardStep = 0; // 0=event, 1=plugin+command, 2=args+confirm
    this.wizardEditing = null; // null = creating, {event, idx} = editing
    this.wizardDraft = { event: '', plugin: '', command: '', args: {} };

    // Human-readable catalogs
    this.eventCatalog = {
      // TikTok
      'tiktok.follow': { name: 'New Follower', desc: 'When someone follows your TikTok account', category: 'tiktok', icon: '👤' },
      'tiktok.join': { name: 'Viewer Joins', desc: 'When someone joins your live stream', category: 'tiktok', icon: '🚪' },
      'tiktok.comment': { name: 'New Comment', desc: 'When someone sends a chat message', category: 'tiktok', icon: '💬' },
      'tiktok.like': { name: 'New Like', desc: 'When someone likes your stream', category: 'tiktok', icon: '❤️' },
      'tiktok.share': { name: 'New Share', desc: 'When someone shares your stream', category: 'tiktok', icon: '🔗' },
      'tiktok.gift': { name: 'Gift Received', desc: 'When someone sends a gift', category: 'tiktok', icon: '🎁' },
      // Minecraft
      'minecraft.player_death': { name: 'Player Dies', desc: 'When you or another player dies', category: 'minecraft', icon: '💀' },
      'minecraft.player_respawn': { name: 'Player Respawns', desc: 'When a player respawns after dying', category: 'minecraft', icon: '✨' },
      // Timer
      'timer.started': { name: 'Timer Starts', desc: 'When the countdown timer starts', category: 'timer', icon: '▶️' },
      'timer.paused': { name: 'Timer Pauses', desc: 'When the countdown timer is paused', category: 'timer', icon: '⏸️' },
      'timer.resumed': { name: 'Timer Resumes', desc: 'When the countdown timer resumes', category: 'timer', icon: '▶️' },
      'timer.reset': { name: 'Timer Resets', desc: 'When the countdown timer is reset', category: 'timer', icon: '🔄' },
      'timer.tick': { name: 'Timer Ticks', desc: 'Every second while the timer is running', category: 'timer', icon: '⏱️' },
      'timer.zero': { name: 'Timer Hits Zero', desc: 'When the countdown reaches zero', category: 'timer', icon: '⏰' },
      'timer.milestone': { name: 'Timer Milestone', desc: 'When the timer passes a configured milestone', category: 'timer', icon: '🎯' },
      // Server
      'server.started': { name: 'Server Starts', desc: 'When the Minecraft server finishes starting', category: 'server', icon: '🟢' },
      'server.stopping': { name: 'Server Stopping', desc: 'When the Minecraft server begins to shut down', category: 'server', icon: '🛑' },
    };

    this.pluginCatalog = {
      'timer': { name: 'Timer', desc: 'Countdown or count-up timer overlay', icon: '⏱️' },
      'spotify-control': { name: 'Spotify', desc: 'Control music playback', icon: '🎵' },
      'win-counter': { name: 'Win Counter', desc: 'Track wins or scores', icon: '🏆' },
      'death-counter': { name: 'Death Counter', desc: 'Count player deaths', icon: '💀' },
    };

    this.commandCatalog = {
      'timer': {
        'start': { name: 'Start Timer', desc: 'Begin the countdown from the current time', args: {} },
        'pause': { name: 'Pause Timer', desc: 'Pause the countdown', args: {} },
        'resume': { name: 'Resume Timer', desc: 'Continue a paused countdown', args: {} },
        'reset': { name: 'Reset Timer', desc: 'Reset the timer to its starting value', args: {} },
        'add_time': { name: 'Add Time', desc: 'Add seconds to the current timer', args: { seconds: { type: 'number', label: 'Seconds to add', default: 10, min: 1 } } },
        'set_time': { name: 'Set Time', desc: 'Set the timer to a specific number of seconds', args: { seconds: { type: 'number', label: 'Seconds to set', default: 60, min: 0 } } },
      },
      'spotify-control': {
        'play': { name: 'Play Music', desc: 'Start or resume playback', args: {} },
        'pause': { name: 'Pause Music', desc: 'Pause the current track', args: {} },
        'next': { name: 'Next Track', desc: 'Skip to the next song', args: {} },
        'previous': { name: 'Previous Track', desc: 'Go back to the previous song', args: {} },
        'volume': { name: 'Set Volume', desc: 'Change playback volume', args: { level: { type: 'number', label: 'Volume level (0–100)', default: 50, min: 0, max: 100 } } },
        'volume_up': { name: 'Volume Up', desc: 'Increase the volume', args: {} },
        'volume_down': { name: 'Volume Down', desc: 'Decrease the volume', args: {} },
        'shuffle': { name: 'Toggle Shuffle', desc: 'Turn shuffle on or off', args: {} },
        'repeat': { name: 'Toggle Repeat', desc: 'Turn repeat on or off', args: {} },
        'save': { name: 'Save Track', desc: 'Save the currently playing song to your library', args: {} },
        'playtrack': { name: 'Play Specific Track', desc: 'Search for and play a song', args: { query: { type: 'string', label: 'Song name or URL', default: '', placeholder: 'Never Gonna Give You Up' } } },
      },
      'win-counter': {
        'add_win': { name: 'Add Win', desc: 'Increase the win count', args: { amount: { type: 'number', label: 'How many wins', default: 1, min: 1 } } },
        'remove_win': { name: 'Remove Win', desc: 'Decrease the win count', args: { amount: { type: 'number', label: 'How many to remove', default: 1, min: 1 } } },
      },
      'death-counter': {
        'player_death': { name: 'Count Death', desc: 'Increase the death counter', args: {} },
      },
    };

    this.categoryLabels = {
      all: 'All Reactions',
      tiktok: 'TikTok Events',
      minecraft: 'Minecraft Events',
      timer: 'Timer Events',
      server: 'Server Events',
      custom: 'Custom Events',
    };

    this.templates = [
      { event: 'minecraft.player_death', plugin: 'spotify-control', command: 'pause', args: {}, title: 'Pause Music on Death', desc: 'Automatically pause Spotify when you die in Minecraft.' },
      { event: 'timer.zero', plugin: 'win-counter', command: 'add_win', args: { amount: 1 }, title: 'Add Win on Timer', desc: 'Award a win when the countdown timer hits zero.' },
      { event: 'tiktok.gift', plugin: 'timer', command: 'add_time', args: { seconds: 30 }, title: 'Add Time on Gift', desc: 'Add 30 seconds to the timer every time someone sends a gift.' },
    ];

    this._bindEvents();
  }

  _bindEvents() {
    document.getElementById('reaction-close')?.addEventListener('click', () => this.close());
    document.getElementById('reaction-add')?.addEventListener('click', () => this.startCreate());
    document.getElementById('reaction-wizard-back')?.addEventListener('click', () => this.wizardBack());
    document.getElementById('reaction-wizard-next')?.addEventListener('click', () => this.wizardNext());
    document.getElementById('reaction-delete-cancel')?.addEventListener('click', () => this._hideDeleteModal());
  }

  /* ─── Public API ─── */

  async open() {
    this.el.classList.remove('hidden');
    await this.load();
  }

  close() {
    if (this._dirty) {
      showConfirmDialog('Unsaved Changes', 'You have unsaved changes. Close anyway?', 'Close', 'btn-danger').then(confirmed => {
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
      const res = await fetchJSON('/event-commands');
      this.data = JSON.parse(JSON.stringify(res.event_commands || {}));
      this.original = JSON.parse(JSON.stringify(this.data));
      this._dirty = false;
      this._updateSaveButton();
      this._updateDashboardSummary();
      this.renderSidebar();
      this.renderList();
    } catch (e) {
      showToast('Failed to load reactions: ' + e.message, 'error');
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
      el.innerHTML = '<span style="color:var(--text-secondary);">No reactions set up yet.</span>';
    } else {
      el.innerHTML = `<span style="color:var(--success);">${count} reaction${count === 1 ? '' : 's'}</span> <span style="color:var(--text-secondary);">configured</span>`;
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

  renderSidebar() {
    const categories = ['all', 'tiktok', 'minecraft', 'timer', 'server', 'custom'];
    let html = '';
    for (const cat of categories) {
      const count = this._countInCategory(cat);
      const active = this.activeCategory === cat ? 'active' : '';
      html += `<div class="sidebar-filter ${active}" onclick="reactionEditor.setCategory('${cat}')">
        <span>${escapeHtml(this.categoryLabels[cat])}</span>
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

  _countInCategory(cat) {
    if (cat === 'all') {
      return Object.keys(this.data).reduce((sum, k) => sum + (this.data[k]?.length || 0), 0);
    }
    let count = 0;
    for (const event of Object.keys(this.data)) {
      const info = this.eventCatalog[event];
      if (cat === 'custom' && (!info || info.category === 'custom')) count += (this.data[event]?.length || 0);
      else if (info && info.category === cat) count += (this.data[event]?.length || 0);
    }
    return count;
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
      const catLabel = this.categoryLabels[info.category] || 'Custom';

      for (let idx = 0; idx < actions.length; idx++) {
        const action = actions[idx];
        const pluginInfo = this.pluginCatalog[action.target] || { name: action.target, icon: '🔌' };
        const cmdInfo = (this.commandCatalog[action.target] || {})[action.command] || { name: action.command };

        html += `<div class="reaction-card">
          <div class="reaction-card-header">
            <div class="reaction-meta">
              <span class="reaction-category-badge ${catClass}">${escapeHtml(catLabel)}</span>
              <span style="font-size:0.75rem;color:var(--text-secondary);">Event: ${escapeHtml(info.name)}</span>
            </div>
            <div class="reaction-card-actions">
              <button class="reaction-btn-sm reaction-btn-test" onclick="reactionEditor.testReaction('${escapeHtml(event)}', ${idx})">Test</button>
              <button class="reaction-btn-sm reaction-btn-edit" onclick="reactionEditor.startEdit('${escapeHtml(event)}', ${idx})">Edit</button>
              <button class="reaction-btn-sm reaction-btn-delete" onclick="reactionEditor.confirmDelete('${escapeHtml(event)}', ${idx})">Delete</button>
            </div>
          </div>
          <div class="reaction-card-body">
            <div class="reaction-flow">
              <div class="reaction-when">
                <span style="font-size:1.1rem;">${info.icon || '⚡'}</span>
                <span>${escapeHtml(info.name)}</span>
              </div>
              <span class="reaction-arrow">→</span>
              <div class="reaction-then">
                <span style="font-size:1.1rem;">${pluginInfo.icon || '🔌'}</span>
                <span>${escapeHtml(cmdInfo.name)}</span>
              </div>
            </div>
            ${Object.keys(action.args || {}).length ? `<div class="reaction-meta" style="margin-top:0.5rem;font-size:0.78rem;">Options: ${escapeHtml(JSON.stringify(action.args))}</div>` : ''}
          </div>
        </div>`;
      }
    }
    this.content.innerHTML = html;
  }

  renderEmptyState() {
    const isSearch = this.searchQuery !== '';
    const isFilter = this.activeCategory !== 'all';
    if (isSearch || isFilter) {
      this.content.innerHTML = `<div class="reaction-empty">
        <h3>No reactions found</h3>
        <p>Try a different search term or category filter.</p>
      </div>`;
      return;
    }
    let html = `<div class="reaction-empty">
      <h3>No reactions yet</h3>
      <p>Reactions let you automatically control plugins when something happens. For example: "When I die in Minecraft, pause my Spotify music." Pick a template below or create your own.</p>
      <div class="reaction-templates">`;
    for (const t of this.templates) {
      const ev = this.eventCatalog[t.event] || { name: t.event, icon: '⚡' };
      const pl = this.pluginCatalog[t.plugin] || { name: t.plugin, icon: '🔌' };
      html += `<div class="reaction-template-card" onclick="reactionEditor.useTemplate(${JSON.stringify(t).replace(/"/g, '&quot;')})">
        <div class="reaction-template-icon">${ev.icon} ${pl.icon}</div>
        <h4>${escapeHtml(t.title)}</h4>
        <p>${escapeHtml(t.desc)}</p>
      </div>`;
    }
    html += `</div>
      <button class="btn btn-primary" style="margin-top:1.5rem;padding:0.7rem 1.4rem;" onclick="reactionEditor.startCreate()">Create Your First Reaction</button>
    </div>`;
    this.content.innerHTML = html;
  }

  /* ─── Actions ─── */

  useTemplate(t) {
    this.wizardEditing = null;
    this.wizardStep = 0;
    this.wizardDraft = { event: t.event, plugin: t.plugin, command: t.command, args: JSON.parse(JSON.stringify(t.args || {})) };
    this._openWizard();
    this.wizardStep = 2; // skip to confirmation since template is complete
    this._renderWizard();
  }

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
          showToast(`Incomplete reaction for "${event}". Please edit and fix it before saving.`, 'error');
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
      showToast('Reactions saved successfully.', 'success');
    } catch (e) {
      showToast('Save failed: ' + e.message, 'error');
      throw e;
    }
  }

  async testReaction(event, idx) {
    const action = this.data[event]?.[idx];
    if (!action) return;
    try {
      await postJSON('/events', { type: event, data: { test: true } });
      showToast(`Test event sent for "${event}". Check if the plugin reacted.`, 'info');
    } catch (e) {
      showToast('Test failed: ' + e.message, 'error');
    }
  }

  confirmDelete(event, idx) {
    const action = this.data[event]?.[idx];
    if (!action) return;
    const evInfo = this.eventCatalog[event] || { name: event };
    const plInfo = this.pluginCatalog[action.target] || { name: action.target };
    const cmdInfo = (this.commandCatalog[action.target] || {})[action.command] || { name: action.command };
    const msg = `Delete reaction: "${evInfo.name} → ${cmdInfo.name}"? This cannot be undone.`;
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
    showToast('Reaction deleted.', 'info');
  }

  /* ─── Wizard ─── */

  _openWizard() {
    this.wizardEl.classList.remove('hidden');
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

    titleEl.textContent = this.wizardEditing ? 'Edit Reaction' : 'Create Reaction';
    stepsEl.innerHTML = [0, 1, 2].map(i => {
      let cls = '';
      if (i === this.wizardStep) cls = 'active';
      else if (i < this.wizardStep) cls = 'done';
      return `<div class="wizard-step-dot ${cls}"></div>`;
    }).join('');

    backBtn.style.visibility = this.wizardStep === 0 ? 'hidden' : 'visible';
    backBtn.textContent = 'Back';
    nextBtn.textContent = this.wizardStep === 2 ? (this.wizardEditing ? 'Save Changes' : 'Create Reaction') : 'Next';
    nextBtn.disabled = false;

    if (this.wizardStep === 0) {
      bodyEl.innerHTML = this._renderStepEvent();
    } else if (this.wizardStep === 1) {
      bodyEl.innerHTML = this._renderStepCommand();
    } else {
      bodyEl.innerHTML = this._renderStepConfirm();
    }
  }

  _renderStepEvent() {
    const groups = {
      tiktok: { label: 'TikTok Events', items: [] },
      minecraft: { label: 'Minecraft Events', items: [] },
      timer: { label: 'Timer Events', items: [] },
      server: { label: 'Server Events', items: [] },
    };
    for (const [key, info] of Object.entries(this.eventCatalog)) {
      const g = groups[info.category];
      if (g) g.items.push({ key, ...info });
    }

    let html = `<h3>Step 1: Choose what triggers the reaction</h3>
    <p class="muted-desc">Pick the event that should cause something to happen. You can also type a custom event name for advanced use.</p>`;

    for (const g of Object.values(groups)) {
      if (!g.items.length) continue;
      html += `<div style="margin-bottom:1.25rem;"><strong style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">${escapeHtml(g.label)}</strong>`;
      html += `<div class="event-grid" style="margin-top:0.5rem;">`;
      for (const item of g.items) {
        const selected = this.wizardDraft.event === item.key ? 'selected' : '';
        html += `<div class="event-option ${selected}" onclick="reactionEditor.selectEvent('${escapeHtml(item.key)}')">
          <span class="event-icon">${item.icon}</span>
          <h4>${escapeHtml(item.name)}</h4>
          <p>${escapeHtml(item.desc)}</p>
        </div>`;
      }
      html += `</div></div>`;
    }

    // Custom event input
    const customVal = this.wizardDraft.event && !this.eventCatalog[this.wizardDraft.event] ? escapeHtml(this.wizardDraft.event) : '';
    html += `<div style="margin-top:1rem;padding-top:1rem;border-top:1px solid var(--border);">
      <strong style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">Advanced</strong>
      <p class="muted-desc">Use a custom event name if you are integrating with external tools or custom plugins.</p>
      <input type="text" id="custom-event-input" value="${customVal}" placeholder="custom.event.name" style="width:100%;padding:0.6rem 0.8rem;background:var(--input-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:0.9rem;" oninput="reactionEditor.onCustomEventInput(this.value)" onchange="reactionEditor.selectEvent(this.value, true)">
    </div>`;

    return html;
  }

  _renderStepCommand() {
    let html = `<h3>Step 2: Choose what happens</h3>
    <p class="muted-desc">Select the plugin and the command that should run when <strong>${escapeHtml((this.eventCatalog[this.wizardDraft.event]?.name) || this.wizardDraft.event)}</strong> occurs.</p>`;

    // Plugin selection
    html += `<div style="margin-bottom:1rem;"><strong style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">1. Pick a Plugin</strong></div>`;
    html += `<div class="plugin-grid" style="margin-bottom:1.5rem;">`;
    for (const [key, info] of Object.entries(this.pluginCatalog)) {
      const selected = this.wizardDraft.plugin === key ? 'selected' : '';
      html += `<div class="plugin-option ${selected}" onclick="reactionEditor.selectPlugin('${escapeHtml(key)}')">
        <div style="font-size:1.5rem;">${info.icon}</div>
        <div class="plugin-option-name">${escapeHtml(info.name)}</div>
        <div class="plugin-option-desc">${escapeHtml(info.desc)}</div>
      </div>`;
    }
    html += `</div>`;

    // Command selection
    if (this.wizardDraft.plugin) {
      const commands = this.commandCatalog[this.wizardDraft.plugin] || {};
      html += `<div style="margin-bottom:1rem;"><strong style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">2. Pick a Command</strong></div>`;
      html += `<div class="command-grid">`;
      for (const [key, info] of Object.entries(commands)) {
        const selected = this.wizardDraft.command === key ? 'selected' : '';
        html += `<div class="command-option ${selected}" onclick="reactionEditor.selectCommand('${escapeHtml(key)}')">
          <h4>${escapeHtml(info.name)}</h4>
          <p>${escapeHtml(info.desc)}</p>
        </div>`;
      }
      html += `</div>`;
    } else {
      html += `<div style="padding:1.5rem;text-align:center;color:var(--text-secondary);border:1px dashed var(--border);border-radius:8px;">Select a plugin above to see available commands.</div>`;
    }

    return html;
  }

  _renderStepConfirm() {
    const evInfo = this.eventCatalog[this.wizardDraft.event] || { name: this.wizardDraft.event, icon: '⚡', desc: 'Custom event' };
    const plInfo = this.pluginCatalog[this.wizardDraft.plugin] || { name: this.wizardDraft.plugin, icon: '🔌' };
    const cmdInfo = (this.commandCatalog[this.wizardDraft.plugin] || {})[this.wizardDraft.command] || { name: this.wizardDraft.command, desc: '' };

    let html = `<h3>Step 3: Review and fine-tune</h3>
    <p class="muted-desc">Make sure everything looks right. Some commands let you set extra options below.</p>`;

    html += `<div class="reaction-preview">
      <div class="reaction-preview-label">Preview</div>
      <div class="reaction-preview-flow">
        <div class="reaction-when"><span style="font-size:1.1rem;">${evInfo.icon}</span> <span>${escapeHtml(evInfo.name)}</span></div>
        <span class="reaction-arrow">→</span>
        <div class="reaction-then"><span style="font-size:1.1rem;">${plInfo.icon}</span> <span>${escapeHtml(cmdInfo.name)}</span></div>
      </div>
    </div>`;

    // Dynamic args form
    const argSchema = cmdInfo.args || {};
    const hasArgs = Object.keys(argSchema).length > 0;
    if (hasArgs) {
      html += `<div class="args-form" style="margin-top:1.25rem;">`;
      html += `<strong style="font-size:0.85rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:0.75rem;">Options</strong>`;
      for (const [argKey, spec] of Object.entries(argSchema)) {
        const currentVal = this.wizardDraft.args[argKey] !== undefined ? this.wizardDraft.args[argKey] : (spec.default !== undefined ? spec.default : '');
        const id = `arg_${argKey}`;
        html += `<div class="form-group">`;
        html += `<label for="${id}">${escapeHtml(spec.label || argKey)}</label>`;
        if (spec.type === 'number') {
          html += `<input type="number" id="${id}" value="${escapeHtml(String(currentVal))}" ${spec.min !== undefined ? `min="${spec.min}"` : ''} ${spec.max !== undefined ? `max="${spec.max}"` : ''}>`;
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
        showToast('Please select an event first.', 'error');
        return;
      }
    } else if (this.wizardStep === 1) {
      if (!this.wizardDraft.plugin || !this.wizardDraft.command) {
        showToast('Please select a plugin and a command.', 'error');
        return;
      }
    } else if (this.wizardStep === 2) {
      this._collectArgs();
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
        const v = parseFloat(el.value);
        this.wizardDraft.args[key] = isNaN(v) ? (spec.default || 0) : v;
      } else {
        this.wizardDraft.args[key] = el.value;
      }
    }
  }

  _commitWizard() {
    const { event, plugin, command, args } = this.wizardDraft;
    if (!event || !plugin || !command) {
      showToast('Incomplete reaction. Please fill all steps.', 'error');
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
    showToast(this.wizardEditing ? 'Reaction updated.' : 'Reaction created.', 'success');
  }
}

const reactionEditor = new ReactionEditor();
const pluginEditor = new PluginConfigEditor();
const actionsEditor = new ActionsEditor();

/* ─── Unsaved changes warning on window close ─── */
let _closeInProgress = false;

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
  return editor.isDirty() || pluginEditor.isDirty() || actionsEditor.isDirty || reactionEditor.isDirty();
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
    showToast('Changes applied and plugin restart requested.', 'success');
  }
}

document.getElementById('btn-unsaved-save-exit').addEventListener('click', async () => {
  _closeInProgress = true;
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  try {
    await _saveAllEditors();
    await pywebview.api.approve_close();
    window.close();
  } catch (e) {
    showToast('Save failed before exit: ' + e.message, 'error');
    _closeInProgress = false;
  }
});

document.getElementById('btn-unsaved-exit-no-save').addEventListener('click', async () => {
  _closeInProgress = true;
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  await pywebview.api.approve_close();
  window.close();
});

document.getElementById('btn-unsaved-cancel').addEventListener('click', () => {
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  _closeInProgress = false;
});

/* ─── Update Checker ─── */
let _updateData = null;

async function checkAllUpdates() {
  const btn = document.getElementById('btn-check-updates');
  const summary = document.getElementById('updates-summary');
  const detail = document.getElementById('updates-detail');
  if (btn) btn.disabled = true;
  if (summary) summary.innerHTML = '<span class="muted">Checking for updates...</span>';
  if (detail) detail.classList.add('hidden');

  try {
    const [toolData, pluginData] = await Promise.all([
      fetchJSON('/updates/check').catch(() => null),
      fetchJSON('/plugins/updates').catch(() => null),
    ]);

    _updateData = { tool: toolData, plugins: pluginData };
    _renderUpdateResults();
  } catch (e) {
    if (summary) summary.innerHTML = '<span class="log-err">Update check failed.</span>';
    log('Update check failed: ' + e.message, 'err');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _renderUpdateResults() {
  const summary = document.getElementById('updates-summary');
  const detail = document.getElementById('updates-detail');
  if (!summary) return;

  const tool = _updateData?.tool;
  const plugins = _updateData?.plugins;
  const toolAvail = tool && tool.update_available;
  const pluginAvail = plugins && plugins.updates_available > 0;
  const total = (toolAvail ? 1 : 0) + (pluginAvail ? plugins.updates_available : 0);

  if (!toolAvail && !pluginAvail) {
    summary.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:center;">' +
      '<span style="color:var(--success);font-weight:500;">All up to date</span>' +
      '<span class="muted" style="font-size:0.85rem;">' +
      (tool ? 'Tool v' + tool.current_version : '') +
      '</span></div>' +
      '<button class="btn btn-primary" style="margin-top:1rem;width:100%;" onclick="checkAllUpdates()">Check for Updates</button>';
    detail.classList.add('hidden');
    return;
  }

  let html = '<div style="display:flex;justify-content:space-between;align-items:center;">' +
    '<span style="color:var(--warning);font-weight:500;">' + total + ' update(s) available</span>' +
    '<span class="muted" style="font-size:0.85rem;">' +
    (tool ? 'Tool v' + tool.current_version : '') +
    '</span></div>' +
    '<button class="btn btn-primary" style="margin-top:0.75rem;width:100%;" onclick="applyUpdates()">Apply Updates (Restart)</button>' +
    '<button class="btn btn-secondary" style="margin-top:0.5rem;width:100%;" onclick="checkAllUpdates()">Check Again</button>';

  summary.innerHTML = html;

  // Detail panel
  let detailHtml = '';
  if (toolAvail) {
    detailHtml +=
      '<div class="update-item">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;">' +
      '<div><strong>TikTok2Mc</strong><br><span class="muted" style="font-size:0.85rem;">' +
      tool.current_version + ' → <strong style="color:var(--accent);">' + tool.latest_version + '</strong></span></div>' +
      (tool.release_url ? '<a href="' + escapeHtml(tool.release_url) + '" target="_blank" class="btn btn-secondary" style="padding:0.3rem 0.7rem;font-size:0.85rem;text-decoration:none;">View Release</a>' : '') +
      '</div></div>';
  }
  if (pluginAvail && plugins.plugins) {
    for (const p of plugins.plugins) {
      if (!p.update_available) continue;
      detailHtml +=
        '<div class="update-item">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;">' +
        '<div><strong>' + escapeHtml(p.display_name || p.name) + '</strong><br><span class="muted" style="font-size:0.85rem;">' +
        p.current_version + ' → <strong style="color:var(--accent);">' + p.latest_version + '</strong></span></div>' +
        (p.error ? '<span class="log-err" style="font-size:0.85rem;">' + escapeHtml(p.error) + '</span>' : '') +
        '</div></div>';
    }
  }
  detail.innerHTML = detailHtml;
  detail.classList.remove('hidden');
}

async function applyUpdates() {
  const btn = document.querySelector('#updates-card .btn-primary');
  if (btn) btn.disabled = true;
  log('Installing plugin updates...', 'info');
  let result = null;
  try {
    result = await postJSON('/plugins/updates/install', {});
    if (result.installed > 0) {
      log(result.installed + ' plugin update(s) installed successfully.', 'info');
    }
    if (result.failed > 0) {
      log(result.failed + ' plugin update(s) failed.', 'err');
      for (const r of result.results) {
        if (!r.success) showToast('Update failed: ' + (r.display_name || r.name) + ' — ' + (r.error || 'unknown error'), 'error');
      }
    }
  } catch (e) {
    log('Plugin update install failed: ' + e.message, 'err');
    showToast('Plugin update install failed: ' + e.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
  showRestartDialog(
    'Apply Updates',
    result && result.installed > 0
      ? result.installed + ' plugin update(s) installed. Restart to complete and apply tool updates.'
      : 'Restart to apply tool updates.'
  );
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
  const ep = '/api/v1/events/stream';
  _sseSource = new EventSource(ep);
  _sseSource.onopen = () => {
    // Reset backoff on successful connection.
    _sseReconnectDelay = 2000;
  };
  _sseSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const type = data.type || '';
      const payload = data.data || {};
      if (type === 'log') {
        log(payload.msg || payload.message || '', payload.level || 'info');
      } else if (type === 'server.restarting') {
        log('Backend restart started', 'warn');
        _showRestartOverlay();
      } else if (type === 'server.started') {
        log('API server started (v' + (payload.version || '?') + ')', 'info');
        if (_restartPending) {
          window.location.reload();
        }
      } else if (type === 'server.stopping') {
        log('API server stopping', 'warn');
      } else if (type.startsWith('plugin.')) {
        log('Plugin: ' + (payload.msg || type), payload.level || 'info');
      } else if (type === 'dashboard.plugin_states') {
        renderLivePluginGrid(payload.plugins || {});
      } else if (type === 'dashboard.reactions_activity') {
        renderLiveReactionsFeed(payload.recent || []);
      } else if (type === 'dashboard.ecm_diagnostics') {
        updateEcmDiagnostics(payload);
      }
    } catch (_) {}
  };
  _sseSource.onerror = () => {
    log('Log stream disconnected — retrying...', 'warn');
    // EventSource auto-reconnects, but if the server is gone for long
    // it gives up.  We manually reconnect with backoff.
    if (_sseSource) {
      _sseSource.close();
      _sseSource = null;
    }
    if (_sseReconnectTimer) clearTimeout(_sseReconnectTimer);
    _sseReconnectTimer = setTimeout(() => {
      // Don't reconnect if we're shutting down or restarting.
      if (_shutdownTriggered || _shutdownNowClicked || _restartPending) return;
      connectLogStream();
    }, _sseReconnectDelay);
    // Exponential backoff up to 10s.
    _sseReconnectDelay = Math.min(_sseReconnectDelay * 1.5, 10000);
  };
}

/* ─── Live Dashboard Widgets ─── */

let _livePluginData = {};
let _liveReactionFeed = [];

function renderLivePluginGrid(plugins) {
  _livePluginData = plugins;
  const container = document.getElementById('live-plugin-grid');
  const empty = document.getElementById('live-plugin-empty');
  if (!container) return;
  const names = Object.keys(plugins);
  if (!names.length) {
    container.innerHTML = '';
    if (empty) empty.classList.remove('hidden');
    return;
  }
  if (empty) empty.classList.add('hidden');

  let html = '';
  for (const name of names) {
    const p = plugins[name];
    const health = p.health_status || 'unknown';
    const enabled = p.enabled;
    const hb = p.last_heartbeat;
    let hbText = '—';
    if (hb) {
      const secs = Math.floor((Date.now() / 1000) - hb);
      if (secs < 10) hbText = 'now';
      else if (secs < 60) hbText = secs + 's ago';
      else if (secs < 3600) hbText = Math.floor(secs / 60) + 'm ago';
      else hbText = Math.floor(secs / 3600) + 'h ago';
    }

    let statusDot = 'dot-unknown';
    if (!enabled) statusDot = 'dot-disabled';
    else if (health === 'healthy') statusDot = 'dot-healthy';
    else if (health === 'unhealthy') statusDot = 'dot-unhealthy';
    else if (health === 'dead') statusDot = 'dot-dead';

    html += `<div class="live-plugin-pill">
      <span class="live-plugin-dot ${statusDot}"></span>
      <span class="live-plugin-name">${escapeHtml(p.display_name || name)}</span>
      <span class="live-plugin-hb">${escapeHtml(hbText)}</span>
    </div>`;
  }
  container.innerHTML = html;
}

function renderLiveReactionsFeed(recent) {
  const container = document.getElementById('live-reactions-feed');
  const empty = document.getElementById('live-reactions-empty');
  if (!container) return;
  if (!recent.length) {
    container.innerHTML = '';
    if (empty) empty.classList.remove('hidden');
    return;
  }
  if (empty) empty.classList.add('hidden');

  // Prepend new items, keep max 20
  for (const item of recent.reverse()) {
    const exists = _liveReactionFeed.some(r =>
      r.timestamp === item.timestamp && r.event === item.event && r.command === item.command
    );
    if (!exists) _liveReactionFeed.unshift(item);
  }
  if (_liveReactionFeed.length > 20) _liveReactionFeed = _liveReactionFeed.slice(0, 20);

  let html = '';
  for (const item of _liveReactionFeed.slice(0, 10)) {
    const time = new Date(item.timestamp * 1000).toLocaleTimeString();
    const evInfo = reactionEditor.eventCatalog[item.event] || { name: item.event, icon: '⚡' };
    const plInfo = reactionEditor.pluginCatalog[item.target] || { name: item.target, icon: '🔌' };
    const cmdInfo = (reactionEditor.commandCatalog[item.target] || {})[item.command] || { name: item.command };
    const statusCls = item.status === 'ok' ? 'feed-ok' : 'feed-error';
    html += `<div class="live-reaction-item ${statusCls}">
      <span class="live-reaction-time">${escapeHtml(time)}</span>
      <span class="live-reaction-icon">${evInfo.icon || '⚡'}</span>
      <span class="live-reaction-text">${escapeHtml(evInfo.name)} → ${escapeHtml(plInfo.icon || '🔌')} ${escapeHtml(cmdInfo.name)}</span>
    </div>`;
  }
  container.innerHTML = html;
}

function updateEcmDiagnostics(payload) {
  // Update the reactions summary on the dashboard card if it shows 0
  const summary = document.getElementById('reactions-summary');
  if (summary && payload.total_reactions !== undefined) {
    const count = payload.total_reactions;
    if (count === 0) {
      summary.innerHTML = '<span style="color:var(--text-secondary);">No reactions set up yet.</span>';
    } else {
      summary.innerHTML = `<span style="color:var(--success);">${count} reaction${count === 1 ? '' : 's'}</span> <span style="color:var(--text-secondary);">configured</span>`;
    }
  }
}

/* ─── Overlay Preview ─── */

async function refreshOverlayPreview() {
  const frame = document.getElementById('overlay-preview-iframe');
  if (!frame) return;
  frame.src = '/api/v1/overlay?_t=' + Date.now();
}

async function sendTestOverlay() {
  const title = (document.getElementById('overlay-test-title')?.value || '').trim() || 'Hello Stream!';
  const subtitle = (document.getElementById('overlay-test-subtitle')?.value || '').trim() || '';
  const duration = parseInt(document.getElementById('overlay-test-duration')?.value) || 3;
  try {
    await postJSON('/overlay/display', { title, subtitle, duration, overlay_name: 'default' });
    showToast('Test overlay sent!', 'success');
  } catch (e) {
    showToast('Failed to send test overlay: ' + e.message, 'error');
  }
}

/* ─── Minecraft Console Terminal ─── */

const consoleTerminal = {
  _history: [],
  _historyIdx: -1,
  _connected: false,

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
    btn.textContent = 'Connecting...';
    try {
      const res = await fetch(API + '/rcon/connect', { method: 'POST' });
      if (!res.ok) throw new Error((await res.json()).detail || 'Connection failed');
      this._connected = true;
      status.textContent = 'Connected';
      status.className = 'console-status connected';
      btn.textContent = 'Disconnect';
      input.disabled = false;
      input.focus();
      this._print('Connected to RCON. Type a command and press Enter.', 'system');
    } catch (e) {
      this._print('Connection failed: ' + e.message, 'error');
      btn.textContent = 'Connect';
      status.textContent = 'Disconnected';
      status.className = 'console-status offline';
    } finally {
      btn.disabled = false;
    }
  },

  async disconnect() {
    const btn = document.getElementById('btn-console-connect');
    const input = document.getElementById('console-input');
    const status = document.getElementById('console-status');
    btn.disabled = true;
    try {
      await fetch(API + '/rcon/disconnect', { method: 'POST' });
    } catch (_) {}
    this._connected = false;
    status.textContent = 'Disconnected';
    status.className = 'console-status offline';
    btn.textContent = 'Connect';
    input.disabled = true;
    this._print('Disconnected from RCON.', 'system');
    btn.disabled = false;
  },

  async sendCommand(cmd) {
    if (!cmd.trim()) return;
    this._print('> ' + cmd, 'input');
    try {
      const res = await fetch(API + '/rcon/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd })
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Command failed');
      const data = await res.json();
      if (data.response) {
        this._print(data.response, 'output');
      } else {
        this._print('(no output)', 'output');
      }
    } catch (e) {
      this._print('Error: ' + e.message, 'error');
      if (e.message.includes('Not connected') || e.message.includes('RCON not connected')) {
        this._connected = false;
        const status = document.getElementById('console-status');
        const btn = document.getElementById('btn-console-connect');
        const input = document.getElementById('console-input');
        status.textContent = 'Disconnected';
        status.className = 'console-status offline';
        btn.textContent = 'Connect';
        input.disabled = true;
      }
    }
  },

  _print(text, cls = 'output') {
    const output = document.getElementById('console-output');
    const line = document.createElement('div');
    line.className = 'console-line console-line--' + cls;
    line.textContent = text;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
  },

  clear() {
    const output = document.getElementById('console-output');
    output.innerHTML = '';
    this._print('Console cleared.', 'system');
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('console-input');
  if (!input) return;
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const cmd = input.value;
      consoleTerminal._history.push(cmd);
      consoleTerminal._historyIdx = consoleTerminal._history.length;
      input.value = '';
      consoleTerminal.sendCommand(cmd);
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
});

/* ─── Init ─── */
async function init() {
  await loadHealth();
  await loadStatus();
  await loadConfig();
  await loadPlugins();
  await reactionEditor.load();
  updateRestartBanner();
  connectLogStream();
  checkAllUpdates();
  if (isFirstRun(currentConfig)) showWizard();
  else hideWizard();
  refreshOverlayPreview();
  _healthIntervalId = setInterval(loadHealth, 10000);
  _statusIntervalId = setInterval(loadStatus, 10000);
  _pluginsIntervalId = setInterval(loadPlugins, 5000);
  if (typeof pywebview !== 'undefined' && pywebview.api) {
    _closePollIntervalId = setInterval(_pollCloseRequest, 200);
  }
}
init();
