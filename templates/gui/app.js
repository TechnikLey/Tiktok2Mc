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

async function pollShutdownStatus() {
  try {
    const data = await fetchJSON('/shutdown/status');
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
      if (_shutdownPollInterval) {
        clearInterval(_shutdownPollInterval);
        _shutdownPollInterval = null;
      }
    } else if (state === 'complete') {
      overlay.classList.add('hidden');
      _shutdownTriggered = false;
      if (_shutdownPollInterval) {
        clearInterval(_shutdownPollInterval);
        _shutdownPollInterval = null;
      }
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
    // If API fails during shutdown, keep showing overlay
    if (_shutdownTriggered || _shutdownNowClicked) {
      const overlay = document.getElementById('shutdown-overlay');
      const display = document.getElementById('shutdown-countdown-display');
      overlay.classList.remove('hidden');
      display.textContent = _shutdownNowClicked ? 'Shutting down...' : 'Preparing shutdown...';
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
  _shutdownNowClicked = true;
  try {
    const overlay = document.getElementById('shutdown-overlay');
    const display = document.getElementById('shutdown-countdown-display');
    overlay.classList.remove('hidden');
    display.textContent = 'Shutting down...';
    document.getElementById('btn-shutdown-now').disabled = true;
    document.getElementById('btn-shutdown-cancel').disabled = true;
    await fetch('/api/v1/shutdown/now', { method: 'POST' });
  } catch (e) {
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

function renderOverlayUrls() {
  const containers = [
    document.getElementById('overlay-urls'),
    document.getElementById('plugin-manager-urls')
  ];
  const en = currentPlugins.filter(p => p.enabled && p.port > 0);
  const html = en.length
    ? '<h3 style="margin:0 0 0.6rem 0;font-size:0.95rem;color:var(--text-secondary);">OBS Browser Sources</h3>' +
      en.map(p => {
        const u = `http://localhost:${p.port}`;
        return `<div class="url-row"><span style="font-size:0.85rem;min-width:100px;">${escapeHtml(p.display_name || p.name)}</span><code>${u}</code><button class="btn-copy" onclick="copyUrl(this,'${u}')">Copy</button></div>`;
      }).join('')
    : '';
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
  // Show overlay immediately — don't wait for backend (5s file watcher delay)
  _shutdownTriggered = true;
  const overlay = document.getElementById('shutdown-overlay');
  const display = document.getElementById('shutdown-countdown-display');
  overlay.classList.remove('hidden');
  display.textContent = 'Preparing shutdown...';
  document.getElementById('btn-shutdown-now').disabled = true;
  try {
    const res = await fetch('/api/v1/shutdown', { method: 'POST' });
    if (res.ok) {
      startShutdownPolling();
    } else {
      showToast('Shutdown signal failed: ' + res.status + ' ' + res.statusText, 'error');
    }
  } catch (e) {
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
    log('Setup saved successfully.');
    showRestartDialog('Setup Complete', 'Your settings have been saved. The tool must be restarted for changes to take effect.');
  } catch (e) {
    log('Failed to save setup: ' + e.message, 'err');
    showToast('Failed to save: ' + e.message, 'error');
  } finally { nextBtn.disabled = false; nextBtn.textContent = 'Save'; }
}
async function triggerRestart() {
  _restartPending = false;
  updateRestartBanner();
  try {
    const res = await fetch('/api/v1/restart', { method: 'POST' });
    if (res.ok) {
      document.querySelector('#restart-dialog .wizard-card').innerHTML = '<h2 style="border:none;padding:0;">Restarting...</h2><p class="muted">Please wait while the tool restarts.</p>';
    } else {
      showToast('Restart signal failed. Please restart manually.', 'error');
    }
  } catch (e) {
    showToast('Restart signal failed. Please restart manually.', 'error');
  }
}
document.getElementById('wizard-back').addEventListener('click', () => { if (wizardStep > 0) { wizardStep--; renderWizardStep(); } });
document.getElementById('wizard-next').addEventListener('click', wizardNext);

/* ─── Config Editor ─── */

const SECTION_ORDER = [
  'tiktok','rcon','server_host','control_method',
  'java','minecraft_server_api',
  'console',
  'theme',
  'update','shutdown','auto_update_config','show_sudo_warning','gui',
  'comment_commands','random_triggers'
];

const CATEGORIES = {
  'Connection': ['tiktok','rcon','server_host','control_method'],
  'Minecraft': ['java','minecraft_server_api'],
  'System': ['console','update','shutdown','auto_update_config','show_sudo_warning','gui'],
  'Appearance': ['theme'],
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
  theme: { title: 'Overlay Colors', desc: 'Customize colors for each plugin overlay. All values are CSS hex codes like #ff0000.', category: 'Appearance' },
  update: { title: 'Auto-Updater', desc: 'Checks for new versions on startup and installs them automatically. Strongly recommended.', category: 'System' },
  shutdown: { title: 'Auto-Shutdown', desc: 'Automatically shuts down the tool after your live stream ends.', category: 'System' },
  server_host: { title: 'Server Address', desc: 'Controls which network interfaces the tool listens on.', category: 'Connection' },
  control_method: { title: 'Control Method', desc: 'How the tool communicates with your streaming software.', category: 'Connection' },
  auto_update_config: { title: 'Auto-Update Config', desc: 'Automatically merge new options when the tool updates.', category: 'System' },
  show_sudo_warning: { title: 'Sudo Warning', desc: 'Linux only. Warns if running without sudo, which can cause permission issues.', category: 'System' }
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
  'update.max_update_logs': 'Maximum number of update log files to keep in logs/update_logs/. 0 = delete all after each update. -1 = keep forever.'
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
  'comment_commands.groups[].enabled': { basic: false, type: 'bool' },
  'comment_commands.groups[].prefix': { basic: false, type: 'text' },
  'comment_commands.groups[].handler': { basic: false, type: 'select', options: ['rcon','http'] },
  'comment_commands.groups[].mode': { basic: false, type: 'select', options: ['deny-all','allow-all'] },
  'comment_commands.groups[].cooldown': { basic: false, type: 'number', min: 0 },
  'comment_commands.groups[].user_cooldown': { basic: false, type: 'number', min: 0 },
  'comment_commands.groups[].trigger_comment_event': { basic: false, type: 'bool' },
  'comment_commands.groups[].url': { basic: false, type: 'text' }
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
  }

  isDirty() {
    return JSON.stringify(this.data) !== JSON.stringify(this.original);
  }

  close() {
    document.getElementById('config-editor').classList.add('hidden');
    document.getElementById('review-modal').classList.add('hidden');
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
        delete this.data[key];
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
    if (Array.isArray(g.commands_config)) g.commands_config = {};
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
    const pluginKeys = new Set(['like_goal','death_counter','win_counter','timer','overlay_text','spotify','channel_points']);
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
      if (!(k in target)) target[k] = {};
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
    // Role selectors handled via onRoleChange live updates
    // Commands config handled via onChange for each field? No, we need to collect them too.
    this.content.querySelectorAll('[data-path]').forEach(el => {
      const path = el.getAttribute('data-path');
      const type = el.getAttribute('data-type');
      if (!path || !type) return;
      if (path.includes('commands_config') && el.tagName === 'INPUT' && el.type === 'checkbox' && !el.classList.contains('toggle')) {
        // Handled by onRoleChange for roles, but we also need to collect toggle overrides
        const parentPath = path.substring(0, path.lastIndexOf('.'));
        // Actually the buildOverrideField for bool uses data-path directly
        // and the text inputs too. They should be collected above.
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
      await putJSON('/config', { config: this.data, backup: true });
      this.original = JSON.parse(JSON.stringify(this.data));
      currentConfig = JSON.parse(JSON.stringify(this.data));
      this.close();
      await loadConfig();
      this.showToast('Configuration saved successfully.', 'success');
      _restartPending = true;
      showRestartDialog('Configuration Saved', 'Some configuration changes require a restart.');
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
  }

  isDirty() {
    return JSON.stringify(this.config) !== JSON.stringify(this.original);
  }

  close() {
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
  return editor.isDirty() || pluginEditor.isDirty() || actionsEditor.isDirty;
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
  if (actionsEditor.isDirty) {
    await actionsEditor.save();
    if (actionsEditor.isDirty) {
      throw new Error('Actions editor could not be saved — check for errors.');
    }
  }
  if (editor.isDirty()) {
    editor.collect();
    editor.mergeUnknownKeys();
    await putJSON('/config', { config: editor.data, backup: true });
    editor.original = JSON.parse(JSON.stringify(editor.data));
    currentConfig = JSON.parse(JSON.stringify(editor.data));
  }
  if (pluginEditor.isDirty()) {
    pluginEditor.collect();
    const payload = JSON.parse(JSON.stringify(pluginEditor.config));
    payload._backup = true;
    await putJSON(`/plugins/${encodeURIComponent(pluginEditor.pluginName)}/config`, payload);
    pluginEditor.original = JSON.parse(JSON.stringify(pluginEditor.config));
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

/* ─── Init ─── */
async function init() {
  await loadHealth();
  await loadConfig();
  await loadPlugins();
  updateRestartBanner();
  if (isFirstRun(currentConfig)) showWizard();
  else hideWizard();
  setInterval(loadHealth, 10000);
  setInterval(loadPlugins, 5000);
  if (typeof pywebview !== 'undefined' && pywebview.api) {
    setInterval(_pollCloseRequest, 200);
  }
}
init();
