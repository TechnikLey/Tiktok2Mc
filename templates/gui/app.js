const API = '/api/v1';
let currentConfig = {};
let currentPlugins = [];
let wizardStep = 0;
let wizardData = {};

const PLUGIN_CONFIG_MAP = {
  overlaytxt: 'overlay_text',
  likegoal: 'like_goal',
  timer: 'timer',
  deathcounter: 'death_counter',
  wincounter: 'win_counter',
  spotify: 'spotify',
  channelpoints: 'channel_points'
};

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

/* ─── Logging ─── */
function log(msg, level = 'info') {
  const view = document.getElementById('log-view');
  const line = document.createElement('div');
  line.className = 'log-line log-' + level;
  line.textContent = new Date().toLocaleTimeString() + '  ' + msg;
  view.appendChild(line);
  view.scrollTop = view.scrollHeight;
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

async function loadPlugins() {
  const tbody = document.getElementById('plugin-list');
  try {
    const data = await fetchJSON('/plugins');
    currentPlugins = data.plugins || [];
    if (!currentPlugins.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="muted">No plugins found.</td></tr>';
      document.getElementById('overlay-urls').innerHTML = '';
      return;
    }
    tbody.innerHTML = currentPlugins.map(p => {
      const cls = p.enabled ? 'on' : 'off';
      const txt = p.enabled ? 'Enabled' : 'Disabled';
      return `<tr><td>${escapeHtml(p.display_name || p.name)}</td><td>${p.version || '-'}</td><td>${p.port || '-'}</td><td><button class="toggle-btn ${cls}" onclick="togglePlugin('${p.name}', ${p.enabled})">${txt}</button></td></tr>`;
    }).join('');
    renderOverlayUrls();
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="4" class="muted">Failed to load plugins.</td></tr>';
    log('Plugins load failed: ' + e.message, 'err');
  }
}

function renderOverlayUrls() {
  const c = document.getElementById('overlay-urls');
  const en = currentPlugins.filter(p => p.enabled && p.port > 0);
  if (!en.length) { c.innerHTML = ''; return; }
  c.innerHTML = '<h3 style="margin:0 0 0.6rem 0;font-size:0.95rem;color:var(--text-secondary);">OBS Browser Sources</h3>' +
    en.map(p => {
      const u = `http://localhost:${p.port}`;
      return `<div class="url-row"><span style="font-size:0.85rem;min-width:100px;">${escapeHtml(p.display_name || p.name)}</span><code>${u}</code><button class="btn-copy" onclick="copyUrl(this,'${u}')">Copy</button></div>`;
    }).join('');
}

function copyUrl(btn, url) {
  navigator.clipboard.writeText(url).then(() => {
    btn.textContent = 'Copied';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1500);
  });
}

async function togglePlugin(name, current) {
  try {
    await postJSON(`/plugins/${name}/${current ? 'disable' : 'enable'}`, {});
    await persistPluginEnabled(name, !current);
    await loadPlugins();
    log(`Plugin ${name} ${!current ? 'enabled' : 'disabled'}`);
  } catch (e) {
    log('Failed to toggle ' + name + ': ' + e.message, 'err');
  }
}

async function persistPluginEnabled(apiName, enabled) {
  const key = PLUGIN_CONFIG_MAP[apiName];
  if (!key) return;
  try {
    const cfgData = await fetchJSON('/config');
    const cfg = cfgData.config || {};
    if (cfg[key]) { cfg[key].enabled = enabled; await putJSON('/config', { config: cfg, backup: true }); }
  } catch (e) { log('Failed to persist plugin state: ' + e.message, 'err'); }
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
function showRestartDialog() {
  document.getElementById('restart-dialog').classList.remove('hidden');
  document.getElementById('wizard').classList.add('hidden');
}
function hideRestartDialog() {
  document.getElementById('restart-dialog').classList.add('hidden');
  document.getElementById('dashboard').classList.remove('hidden');
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
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">Set a secure password for the Minecraft RCON connection. This is required.</p>
      <div class="form-group"><label>RCON Password</label>
      <input type="password" id="w-rcon-password" value="${escapeHtml(wizardData.rcon_password)}" placeholder="Required" oninput="updatePasswordMeter()">
      <div class="inline-error" id="err-rcon-password">Please fix the password issues above.</div>
      <div class="strength-meter"><div class="strength-segment"></div><div class="strength-segment"></div><div class="strength-segment"></div></div>
      <div class="strength-label" id="strength-label">Enter a password to see strength</div>
      <div class="hint">Must be at least 8 characters with uppercase, lowercase, number and special character.</div></div>`;
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
    const pass = passInput.value;
    const issues = validatePassword(pass);
    if (issues.length > 0) {
      passInput.classList.add('invalid');
      document.getElementById('err-rcon-password').innerHTML = issues.map(i => '&bull; ' + i).join('<br>');
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
    showRestartDialog();
  } catch (e) {
    log('Failed to save setup: ' + e.message, 'err');
    alert('Failed to save: ' + e.message);
  } finally { nextBtn.disabled = false; nextBtn.textContent = 'Save'; }
}
async function triggerRestart() {
  try {
    const res = await fetch('/api/v1/restart', { method: 'POST' });
    if (res.ok) {
      document.querySelector('#restart-dialog .wizard-card').innerHTML = '<h2 style="border:none;padding:0;">Restarting...</h2><p class="muted">Please wait while the tool restarts.</p>';
    } else { alert('Restart signal failed. Please restart manually.'); }
  } catch (e) { alert('Restart signal failed. Please restart manually.'); }
}
document.getElementById('wizard-back').addEventListener('click', () => { if (wizardStep > 0) { wizardStep--; renderWizardStep(); } });
document.getElementById('wizard-next').addEventListener('click', wizardNext);
document.getElementById('btn-restart-now').addEventListener('click', triggerRestart);
document.getElementById('btn-restart-later').addEventListener('click', () => { hideRestartDialog(); loadConfig(); });

/* ─── Config Editor ─── */

const SECTION_ORDER = [
  'tiktok','rcon','java','comment_commands','control_method','server_host',
  'overlay_text','like_goal','timer','death_counter','win_counter',
  'spotify','channel_points','minecraft_server_api','console',
  'random_triggers','theme','update','shutdown','auto_update_config',
  'show_sudo_warning','gui'
];

const CATEGORIES = {
  'Connection': ['tiktok','rcon','server_host','control_method'],
  'Minecraft': ['java','minecraft_server_api'],
  'Streaming & Overlays': ['console','overlay_text','like_goal','timer','death_counter','win_counter'],
  'Chat & Commands': ['comment_commands','channel_points','random_triggers'],
  'Integrations': ['spotify'],
  'Appearance': ['theme'],
  'System': ['update','shutdown','auto_update_config','show_sudo_warning','gui']
};

const SECTION_META = {
  tiktok: { title: 'TikTok Live', desc: 'Connect the tool to your TikTok live stream. Set your username and connection behavior.', category: 'Connection' },
  rcon: { title: 'Remote Console (RCON)', desc: 'RCON allows the tool to send commands to your Minecraft server. Keep this enabled.', category: 'Connection' },
  java: { title: 'Minecraft Server', desc: 'Controls how much RAM the Minecraft server uses and which port it runs on.', category: 'Minecraft' },
  comment_commands: { title: 'Chat Commands', desc: 'Let viewers send commands via TikTok chat. You can create multiple groups with different prefixes, roles, and rules.', category: 'Chat & Commands' },
  random_triggers: { title: 'Random Trigger Filter', desc: 'Controls which triggers can be selected by the $random action in data/actions.mca.', category: 'Chat & Commands' },
  console: { title: 'Console Visibility', desc: 'Controls which windows and processes are shown when the tool starts.', category: 'Streaming & Overlays' },
  minecraft_server_api: { title: 'Minecraft Server API', desc: 'Handles communication between the tool and the Minecraft server. Required for player death/respawn detection.', category: 'Minecraft' },
  overlay_text: { title: 'Overlay Text', desc: 'Display text notifications on your stream. Triggered via >> in actions.mca. Works as an OBS Browser Source.', category: 'Streaming & Overlays' },
  like_goal: { title: 'Like Goal', desc: 'A progress bar tracking likes toward a goal. Fires triggers at set intervals.', category: 'Streaming & Overlays' },
  timer: { title: 'Stream Timer', desc: 'A standalone countdown timer for your stream. Can auto-pause on player death or post wins.', category: 'Streaming & Overlays' },
  death_counter: { title: 'Death Counter', desc: 'Displays the number of player deaths on stream as an overlay.', category: 'Streaming & Overlays' },
  win_counter: { title: 'Win Counter', desc: 'Tracks wins and losses on stream. Can subtract a win when the player dies.', category: 'Streaming & Overlays' },
  gui: { title: 'Dashboard', desc: 'The graphical user interface is served by the central API server and shown in a window.', category: 'System' },
  spotify: { title: 'Spotify Control', desc: 'Let viewers control your Spotify playback via chat. Displays the current track as an overlay.', category: 'Integrations' },
  channel_points: { title: 'Channel Points', desc: 'Awards loyalty points to active viewers. Viewers can check !points and redeem rewards.', category: 'Chat & Commands' },
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
  'comment_commands.groups[].url': 'HTTP endpoint that receives the command. You can use placeholders: {user} = viewer name, {text} = command text, {spotify_port} = resolved from spotify.port.',
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
  'overlay_text.enabled': 'Display text notifications on your stream. Triggered via >> in actions.mca. Works as an OBS Browser Source with a transparent background.',
  'overlay_text.port': 'Port for the OBS Browser Source overlay. Default: 29186.',
  'overlay_text.display_mode': 'overwrite = new message replaces the current one (recommended). queue = messages stack and show one after another. WARNING: Queue mode can pile up on busy streams.',
  'overlay_text.fade_in': 'Fade-in duration in milliseconds. This is NOT included in the Duration from >>commands. Set to 0 for instant appear.',
  'overlay_text.fade_out': 'Fade-out duration in milliseconds. Set to 0 for instant disappear.',
  'overlay_text.max_fails': 'Circuit breaker: after this many consecutive failures, the tool stops trying.',
  'overlay_text.cooldown': 'Seconds to wait before retrying after max_fails consecutive failures.',
  'overlay_text.overlays': 'Named overlay instances. Each name creates a separate URL. You can send text to a specific overlay from actions.mca using @NAME>> syntax.',
  'like_goal.enabled': 'Show a like progress bar on your stream as an OBS Browser Source.',
  'like_goal.port': 'Port for the Like Goal OBS overlay. Default: 29193.',
  'like_goal.display_text': 'Text displayed above the progress bar. Example: "Like Goal" or "Community Goal".',
  'like_goal.initial_goal': 'Number of likes needed to reach the first goal. Use underscores for readability in the config file (100_000 = 100000). Do NOT use dots or commas.',
  'like_goal.goal_multiplier': 'What happens after a goal is reached: 0 = reset likes to 0 and start over, 1 = increase goal by initial_goal each time, 2+ = multiply goal by this value each time.',
  'like_goal.triggers': 'Like triggers fire when total stream likes reach a threshold. Each needs a unique ID, an interval, and a function name that matches an entry in data/actions.mca.',
  'like_goal.triggers[].id': 'A unique name for this trigger. Used in logs.',
  'like_goal.triggers[].every': 'Like interval between activations. Example: 100 means the trigger fires every 100 likes.',
  'like_goal.triggers[].function': 'The trigger name used in data/actions.mca. This connects the config to your custom commands.',
  'like_goal.triggers[].payload': 'A label passed with the trigger. This is optional and defaults to "Community".',
  'like_goal.triggers[].enabled': 'Set to false to disable this trigger without deleting it.',
  'timer.enabled': 'A standalone countdown timer for your stream. Can be controlled via REST API (start, pause, reset).',
  'timer.port': 'Port for the timer OBS overlay. Default: 29189.',
  'timer.start_time': 'Starting minutes for the countdown. Example: 10 means 10 minutes.',
  'timer.auto_win': 'POST a win to WinCounter each time the timer reaches 0. Disabled by default so the timer runs standalone.',
  'timer.pause_on_death': 'Auto-pause the timer when the player dies. Requires MinecraftServerAPI to be enabled.',
  'death_counter.enabled': 'Display the number of player deaths on stream as an overlay.',
  'death_counter.port': 'Port for the Death Counter OBS overlay. Default: 29190.',
  'win_counter.enabled': 'Track wins and losses on stream as an overlay.',
  'win_counter.port': 'Port for the Win Counter OBS overlay. Default: 29191.',
  'win_counter.decrement_on_death': 'Subtract a win when the player dies. Disabled by default for standalone win tracking.',
  'gui.enabled': 'Launch the graphical dashboard on startup. If disabled, you can still open it manually.',
  'spotify.enabled': 'Let viewers control your Spotify playback via chat commands and stream events. Also displays the current track as an OBS overlay.',
  'spotify.port': 'Port for the Spotify web server, overlay, and chat command endpoint. Default: 29194.',
  'spotify.client_id': 'Your Spotify Developer App Client ID. Get it at https://developer.spotify.com/dashboard',
  'spotify.client_secret': 'Your Spotify Developer App Client Secret. Keep this private.',
  'spotify.redirect_uri': 'Must exactly match what you entered in your Spotify Developer App settings. Only change this if you also changed the port above.',
  'spotify.device_id': 'Target a specific Spotify device by ID. Leave empty to use whatever device is currently active. You can find device IDs via the API when Spotify is playing.',
  'spotify.volume_step': 'How much the volume changes per "$volume up" or "$volume down" command, in percent. Example: 10 means each command changes volume by 10%.',
  'spotify.playtrack_mode': 'replace = play the requested song immediately, replacing the current track. queue = add the requested song to the queue (plays after current track).',
  'channel_points.enabled': 'Award loyalty points to active viewers. Viewers can check their points with !points and redeem rewards with !redeem <name>.',
  'channel_points.port': 'Port for the channel points overlay and API. Default: 29195.',
  'channel_points.award_amount': 'How many points are awarded per interval to each active viewer.',
  'channel_points.award_interval_seconds': 'How often points are awarded, in seconds.',
  'channel_points.ping_timeout_minutes': 'How many minutes after last activity a viewer is considered inactive and stops earning points.',
  'channel_points.leaderboard_count': 'Number of top viewers shown on the leaderboard overlay.',
  'update.enabled': 'Checks for new versions on startup and installs them automatically. It is strongly recommended to keep this enabled.',
  'update.max_update_logs': 'Maximum number of update log files to keep in logs/update_logs/. 0 = delete all after each update. -1 = keep forever.',
  'theme.like_goal.background': 'Like goal overlay background color. Use a CSS hex code like #050505.',
  'theme.like_goal.text': 'Like goal overlay text color.',
  'theme.like_goal.accent': 'Like goal primary accent color.',
  'theme.like_goal.accent2': 'Like goal secondary accent color.',
  'theme.like_goal.danger': 'Like goal danger or warning color.',
  'theme.death_counter.background': 'Death counter overlay background color.',
  'theme.death_counter.text': 'Death counter overlay text color.',
  'theme.win_counter.background': 'Win counter overlay background color.',
  'theme.win_counter.text': 'Win counter overlay text color.',
  'theme.win_counter.danger': 'Win counter danger color.',
  'theme.win_counter.muted': 'Win counter muted color.',
  'theme.win_counter.separator': 'Win counter separator color.',
  'theme.timer.background': 'Timer overlay background color.',
  'theme.timer.text': 'Timer overlay text color.',
  'theme.timer.warning': 'Timer warning color.',
  'theme.timer.blink': 'Timer blink color.',
  'theme.timer.danger': 'Timer danger color.',
  'theme.overlay_text.background': 'Overlay text background color.',
  'theme.overlay_text.text': 'Overlay text text color.',
  'theme.spotify.background': 'Spotify overlay background color.',
  'theme.spotify.text': 'Spotify overlay text color.',
  'theme.spotify.accent': 'Spotify primary accent color.',
  'theme.spotify.accent2': 'Spotify secondary accent color.',
  'theme.channel_points.background': 'Channel points overlay background color.',
  'theme.channel_points.text': 'Channel points overlay text color.',
  'theme.channel_points.accent': 'Channel points primary accent color.',
  'theme.channel_points.accent2': 'Channel points secondary accent color.',
  'theme.channel_points.accent3': 'Channel points tertiary accent color.',
  'theme.channel_points.danger': 'Channel points danger color.'
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
  'overlay_text.enabled': { basic: true, type: 'bool' },
  'overlay_text.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'overlay_text.display_mode': { basic: false, type: 'select', options: ['overwrite','queue'] },
  'overlay_text.fade_in': { basic: false, type: 'number', min: 0 },
  'overlay_text.fade_out': { basic: false, type: 'number', min: 0 },
  'overlay_text.max_fails': { basic: false, type: 'number', min: 1 },
  'overlay_text.cooldown': { basic: false, type: 'number', min: 0 },
  'like_goal.enabled': { basic: true, type: 'bool' },
  'like_goal.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'like_goal.display_text': { basic: false, type: 'text' },
  'like_goal.initial_goal': { basic: false, type: 'number', min: 1 },
  'like_goal.goal_multiplier': { basic: false, type: 'number', min: 0 },
  'timer.enabled': { basic: true, type: 'bool' },
  'timer.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'timer.start_time': { basic: false, type: 'number', min: 1 },
  'timer.auto_win': { basic: false, type: 'bool' },
  'timer.pause_on_death': { basic: false, type: 'bool' },
  'death_counter.enabled': { basic: true, type: 'bool' },
  'death_counter.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'win_counter.enabled': { basic: true, type: 'bool' },
  'win_counter.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'win_counter.decrement_on_death': { basic: false, type: 'bool' },
  'gui.enabled': { basic: true, type: 'bool' },
  'spotify.enabled': { basic: true, type: 'bool' },
  'spotify.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'spotify.client_id': { basic: true, type: 'text' },
  'spotify.client_secret': { basic: true, type: 'password' },
  'spotify.redirect_uri': { basic: false, type: 'text' },
  'spotify.device_id': { basic: false, type: 'text' },
  'spotify.volume_step': { basic: false, type: 'number', min: 1, max: 100 },
  'spotify.playtrack_mode': { basic: false, type: 'select', options: ['replace','queue'] },
  'channel_points.enabled': { basic: true, type: 'bool' },
  'channel_points.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'channel_points.award_amount': { basic: false, type: 'number', min: 1 },
  'channel_points.award_interval_seconds': { basic: false, type: 'number', min: 1 },
  'channel_points.ping_timeout_minutes': { basic: false, type: 'number', min: 1 },
  'channel_points.leaderboard_count': { basic: false, type: 'number', min: 1 },
  'update.enabled': { basic: true, type: 'bool' },
  'update.max_update_logs': { basic: false, type: 'number' },
  'comment_commands.groups[].enabled': { basic: false, type: 'bool' },
  'comment_commands.groups[].prefix': { basic: false, type: 'text' },
  'comment_commands.groups[].handler': { basic: false, type: 'select', options: ['rcon','http'] },
  'comment_commands.groups[].mode': { basic: false, type: 'select', options: ['deny-all','allow-all'] },
  'comment_commands.groups[].cooldown': { basic: false, type: 'number', min: 0 },
  'comment_commands.groups[].user_cooldown': { basic: false, type: 'number', min: 0 },
  'comment_commands.groups[].trigger_comment_event': { basic: false, type: 'bool' },
  'comment_commands.groups[].url': { basic: false, type: 'text' },
  'like_goal.triggers[].id': { basic: false, type: 'text' },
  'like_goal.triggers[].every': { basic: false, type: 'number', min: 1 },
  'like_goal.triggers[].function': { basic: false, type: 'text' },
  'like_goal.triggers[].payload': { basic: false, type: 'text' },
  'like_goal.triggers[].enabled': { basic: false, type: 'bool' },
  'overlay_text.overlays[].name': { basic: false, type: 'text' }
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
    this.status = document.getElementById('save-status');
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
    this.setStatus('', '');
    this.activeSection = null;
    // Attach scroll spy
    const main = document.querySelector('.editor-main');
    if (main) {
      main.addEventListener('scroll', () => this.onScrollSpy(), { passive: true });
    }
    // Scroll to first section
    const first = this.content.querySelector('.section-card');
    if (first) { this.scrollTo(first.id); }
  }

  close() {
    document.getElementById('config-editor').classList.add('hidden');
    document.getElementById('review-modal').classList.add('hidden');
  }

  extractUnknownKeys() {
    for (const key of Object.keys(this.data)) {
      if (key === 'config_version') {
        delete this.data[key];
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
        if (path === 'like_goal.triggers') {
          html += this.buildTriggerTable(path, v);
        } else if (path === 'comment_commands.groups') {
          html += this.buildGroupEditor(path, v);
        } else if (path === 'overlay_text.overlays') {
          html += this.buildOverlayList(path, v);
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

  buildTriggerTable(path, triggers) {
    const help = getHelp(path);
    let rows = (triggers || []).map((t, i) => {
      const p = `${path}[${i}]`;
      return `<tr>
        <td><input type="text" value="${escapeHtml(t.id || '')}" data-path="${p}.id" data-type="string" placeholder="likes_standard"></td>
        <td><input type="number" value="${t.every !== undefined ? t.every : ''}" data-path="${p}.every" data-type="number" placeholder="100"></td>
        <td><input type="text" value="${escapeHtml(t.function || '')}" data-path="${p}.function" data-type="string" placeholder="likes"></td>
        <td><input type="text" value="${escapeHtml(t.payload || '')}" data-path="${p}.payload" data-type="string" placeholder="Community"></td>
        <td><input type="checkbox" class="toggle" ${t.enabled !== false ? 'checked' : ''} data-path="${p}.enabled" data-type="bool"></td>
        <td class="row-actions"><button class="btn-icon" onclick="editor.removeArrayItem('${path}', ${i})">Remove</button></td>
      </tr>`;
    }).join('');
    return `<div class="editor-field full-width" data-path="${path}">
      <div class="field-label">Like Triggers</div>
      <div class="field-widget">
        <table class="array-table">
          <thead><tr><th>ID</th><th>Every (likes)</th><th>Function</th><th>Payload</th><th>Enabled</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <button class="btn btn-secondary" style="margin-top:0.5rem;" onclick="editor.addTrigger('${path}')">Add Trigger</button>
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
      </div>
    </div>`;
  }

  addTrigger(path) {
    const arr = this.getValue(path) || [];
    arr.push({ id: '', every: 100, function: '', payload: 'Community', enabled: true });
    this.setValue(path, arr);
    this.render();
  }

  removeArrayItem(path, index) {
    const arr = this.getValue(path) || [];
    arr.splice(index, 1);
    this.setValue(path, arr);
    this.render();
  }

  buildOverlayList(path, overlays) {
    const help = getHelp(path);
    let items = (overlays || []).map((o, i) => {
      return `<div style="display:flex;gap:0.5rem;align-items:center;margin-bottom:0.5rem;">
        <input type="text" value="${escapeHtml(o.name || '')}" data-path="${path}[${i}].name" data-type="string" style="flex:1;" placeholder="default">
        <button class="btn-icon" onclick="editor.removeArrayItem('${path}', ${i})">Remove</button>
      </div>`;
    }).join('');
    return `<div class="editor-field full-width" data-path="${path}">
      <div class="field-label">Overlay Names</div>
      <div class="field-widget">
        ${items}
        <button class="btn btn-secondary" onclick="editor.addOverlay('${path}')">Add Overlay</button>
        ${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}
      </div>
    </div>`;
  }

  addOverlay(path) {
    const arr = this.getValue(path) || [];
    arr.push({ name: '' });
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
      html += `<details style="margin-bottom:0.6rem;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:0.6rem;">
        <summary style="cursor:pointer;font-size:0.9rem;font-weight:500;">${escapeHtml(cmd)}</summary>
        <div style="padding:0.6rem 0.25rem 0.2rem 0.25rem;">
          ${this.buildOverrideField('points_cost', c.points_cost, `${path}.${cmd}.points_cost`)}
          ${this.buildOverrideField('cooldown', c.cooldown, `${path}.${cmd}.cooldown`)}
          ${this.buildOverrideField('conditional', c.conditional, `${path}.${cmd}.conditional`)}
          ${this.buildOverrideField('url', c.url, `${path}.${cmd}.url`)}
          ${this.buildOverrideField('handler', c.handler, `${path}.${cmd}.handler`)}
          ${this.buildOverrideField('roles', c.roles, `${path}.${cmd}.roles`)}
        </div>
      </details>`;
    }
    html += `${help ? `<p class="field-desc">${escapeHtml(help)}</p>` : ''}</div></div>`;
    return html;
  }

  buildOverrideField(key, value, path) {
    const label = toTitle(key);
    const id = 'f_' + path.replace(/[^a-zA-Z0-9]/g, '_');

    if (value === undefined) {
      if (key === 'roles') value = [];
      else if (key === 'conditional') value = false;
      else value = '';
    }

    if (key === 'roles') {
      const roles = ['all','moderator','superfan','fanclub'];
      const current = value || [];
      const boxes = roles.map(r => {
        const checked = current.includes(r) ? 'checked' : '';
        return `<label style="margin-right:0.75rem;font-size:0.85rem;"><input type="checkbox" ${checked} data-role="${r}" onchange="editor.onRoleChange('${path}', this)">${toTitle(r)}</label>`;
      }).join('');
      return `<div style="margin-bottom:0.6rem;"><span style="font-size:0.85rem;color:var(--text);display:block;margin-bottom:0.3rem;">${escapeHtml(label)}</span><div>${boxes}</div></div>`;
    }
    if (key === 'conditional') {
      return `<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.6rem;"><input type="checkbox" class="toggle" id="${id}" ${value ? 'checked' : ''} data-path="${path}" data-type="bool"><label for="${id}" style="font-size:0.85rem;">${escapeHtml(label)}</label></div>`;
    }
    if (key === 'handler') {
      return `<div style="margin-bottom:0.6rem;"><label style="font-size:0.85rem;color:var(--text);display:block;margin-bottom:0.3rem;">${escapeHtml(label)}</label><select id="${id}" data-path="${path}" data-type="string" style="padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);"><option value="">(inherit from group)</option><option value="rcon" ${value==='rcon'?'selected':''}>rcon</option><option value="http" ${value==='http'?'selected':''}>http</option></select></div>`;
    }
    if (key === 'points_cost' || key === 'cooldown') {
      return `<div style="margin-bottom:0.6rem;"><label style="font-size:0.85rem;color:var(--text);display:block;margin-bottom:0.3rem;">${escapeHtml(label)}</label><input type="number" id="${id}" value="${value !== '' ? escapeHtml(String(value)) : ''}" data-path="${path}" data-type="number" style="width:100%;padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);"></div>`;
    }
    return `<div style="margin-bottom:0.6rem;"><label style="font-size:0.85rem;color:var(--text);display:block;margin-bottom:0.3rem;">${escapeHtml(label)}</label><input type="text" id="${id}" value="${escapeHtml(value || '')}" data-path="${path}" data-type="string" style="width:100%;padding:0.4rem 0.6rem;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);"></div>`;
  }

  addGroup(path) {
    const arr = this.getValue(path) || [];
    arr.push({ enabled: true, prefix: '#', allowed_roles: ['moderator'], mode: 'deny-all', commands: [], commands_config: {}, handler: 'rcon', cooldown: 0, user_cooldown: 0, trigger_comment_event: true });
    this.setValue(path, arr);
    this.render();
  }

  buildThemeEditor(path, theme) {
    let html = '';
    for (const [plugin, colors] of Object.entries(theme || {})) {
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

  onScrollSpy() {
    if (this._scrollTimer) clearTimeout(this._scrollTimer);
    this._scrollTimer = setTimeout(() => {
      const main = document.querySelector('.editor-main');
      if (!main) return;
      const offset = main.getBoundingClientRect().top + 80; // below topbar
      let best = null;
      let bestDist = Infinity;
      for (const card of this.content.querySelectorAll('.section-card')) {
        const rect = card.getBoundingClientRect();
        const dist = Math.abs(rect.top - offset);
        if (rect.top <= offset + 20 && dist < bestDist) {
          bestDist = dist;
          best = card.id;
        }
      }
      if (best && best.startsWith('section_')) {
        const key = best.substring('section_'.length);
        if (this.activeSection !== key) {
          this.activeSection = key;
          this.renderSidebar();
        }
      }
    }, 80);
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
    this.setStatus('Saving...', '');
    try {
      await putJSON('/config', { config: this.data, backup: true });
      currentConfig = JSON.parse(JSON.stringify(this.data));
      this.close();
      await loadConfig();
      this.showToast('Configuration saved successfully. Some changes may require a restart.', 'success');
    } catch (e) {
      this.setStatus('Save failed: ' + e.message, 'err');
      this.showToast('Save failed: ' + e.message, 'error');
    }
  }

  setStatus(msg, cls) {
    this.status.textContent = msg;
    this.status.className = 'save-status ' + (cls || '');
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

/* ─── Init ─── */
async function init() {
  await loadHealth();
  await loadConfig();
  await loadPlugins();
  if (isFirstRun(currentConfig)) showWizard();
  else hideWizard();
  setInterval(loadHealth, 10000);
  setInterval(loadPlugins, 5000);
}
init();
