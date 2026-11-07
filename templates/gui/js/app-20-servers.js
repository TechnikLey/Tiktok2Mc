/**
 * @file Minecraft server manager, Java runtime, server plugins/modals and overlay URLs.
 *
 * The server-modal wiring block at the end must stay after the server functions it references.
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Server Manager ─── */
let _serverLifecycleInterval = null;

/** Start periodic polling of server lifecycle state. */
function startServerLifecyclePolling() {
  stopServerLifecyclePolling();
  updateServerLifecycleUI();
  _serverLifecycleInterval = setInterval(updateServerLifecycleUI, 5000);
}

/** Stop periodic server lifecycle polling. */
function stopServerLifecyclePolling() {
  if (_serverLifecycleInterval) {
    clearInterval(_serverLifecycleInterval);
    _serverLifecycleInterval = null;
  }
}

/** Fetch the server inventory, re-render the manager, refresh the console selector and load Java status. */
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

/** Fetch Java runtime status and render the installation banner when Java is missing. */
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

/** Render the Java status banner, including the install action when Java is unavailable. */
function renderJavaStatusBanner(data) {
  const el = document.getElementById('java-status-banner');
  if (!el) return;
  if (data && data.ok) {
    el.classList.add('hidden');
    el.innerHTML = '';
    return;
  }
  const reason = (data && data.reason) || 'No Java runtime was found on this system.';
  const minVer = (data && data.minJavaVersion) || 25;
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

/** Install a managed Java runtime and poll its progress until it finishes, fails or times out. */
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

/** Render server instance cards, the version library and the Minecraft plugin list. */
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

/** Render one server card with state-dependent actions and metadata. */
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

/** Render the installed server version library with safety and size badges. */
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

/** Return the CSS badge class for a server version's safety category. */
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

/** Return the localized badge label for a server version's safety category. */
function _versionBadgeLabel(version) {
  if (!_serverManagerCache) return I18N.t('servers.unsafe');
  const found = (_serverManagerCache.installed || []).find(v => v.version === version);
  if (!found) {
    if ((_serverManagerCache.safe_versions || []).includes(version)) return I18N.t('servers.safe');
    return I18N.t('servers.unsafe');
  }
  return found.type.toUpperCase();
}

/** Confirm switching to another server version, warning when that version is untested. */
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

/** Confirm and delete an installed server version. */
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

/** Refresh server cards and controls from the latest lifecycle state. */
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

/** Persist the auto-start flag for a server instance. */
async function toggleAutoStart(instanceId, enabled) {
  try {
    await putJSON('/servers/instances/' + encodeURIComponent(instanceId), { auto_start: enabled });
    showToast(I18N.t(enabled ? 'servers.autoStartEnabled' : 'servers.autoStartDisabled', { name: instanceId }), 'success');
  } catch (e) {
    showToast(I18N.t('servers.actionFailed', { msg: e.message }), 'error');
    await loadServerManager();
  }
}

/** Run a start, stop or restart action for a server instance and restore the card controls afterwards. */
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

/** Open a server instance folder, preferring the native pywebview bridge and falling back to the API. */
async function openServerFolder(instanceId) {
  // Preferred path: open the folder from the GUI process itself. On Linux the
  // backend API runs elevated (pkexec) with a sanitized environment that has
  // no DISPLAY, so a file manager started from the API can't show a window.
  // The GUI process has the real display, so a pywebview bridge call works
  // reliably here (same idea as the "Add Custom Version" file picker).
  const api = typeof pywebview !== 'undefined' && pywebview.api;
  if (api && api.open_folder) {
    try {
      const p = await fetchJSON('/servers/instances/' + encodeURIComponent(instanceId) + '/path');
      const path = p.path;
      if (!path) throw new Error(I18N.t('servers.openFolderFailedTitle'));
      const result = await api.open_folder(String(path));
      if (result && result !== 'true' && result !== 'ok') {
        showToast(I18N.t('servers.openFolderFailed', { msg: String(result) }), 'error');
      } else {
        showToast(I18N.t('servers.folderOpened', { path }), 'success');
      }
      return;
    } catch (e) {
      showToast(I18N.t('servers.openFolderFailed', { msg: e.message }), 'error');
      return;
    }
  }
  // Fallback: backend endpoint (browser / remote dev, no pywebview bridge).
  try {
    const res = await fetch(API + '/servers/instances/' + encodeURIComponent(instanceId) + '/open', { method: 'POST', headers: _withApiKey({}) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || I18N.t('servers.openFolderFailedTitle'));
    if (data.opened) {
      showToast(I18N.t('servers.folderOpened', { path: data.path }), 'success');
    } else {
      showToast(I18N.t('servers.openFolderFailed', { msg: data.error || I18N.t('servers.folderPath', { path: data.path }) }), 'error');
    }
  } catch (e) {
    showToast(I18N.t('servers.openFolderFailed', { msg: e.message }), 'error');
  }
}

/** Confirm and delete a server instance. */
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

/** Return the instance selected in the Minecraft plugin view, defaulting to the first cached instance. */
function _mcPluginsInstanceId() {
  const sel = document.getElementById('mc-plugins-instance-select');
  return sel ? sel.value : '';
}

/** Populate the Minecraft plugin instance selector from the cached server list. */
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

/** Load the Minecraft plugin list for the selected instance. */
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

/** Render Minecraft plugin cards and the enabled-plugin count for one instance. */
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
/** Return whether disabling or deleting a Minecraft plugin needs an extra confirmation. */
function _isCriticalMcPlugin(name) {
  return _CRITICAL_MC_PLUGINS.includes(name);
}

/** Enable or disable a Minecraft plugin for an instance. */
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

/** Confirm and delete a Minecraft plugin jar. */
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

/** Open the file picker for uploading a Minecraft plugin jar. */
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

/** Validate and upload the selected Minecraft plugin jar. */
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

/** Open the create-server modal with default values. */
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

/** Close the create-server modal. */
function closeServerCreateModal() {
  document.getElementById('server-create-modal')?.classList.add('hidden');
}

/** Create a server instance from the validated form values. */
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

/** Validate the create-server form and enable or disable its confirm button. */
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

/** Open the version download modal and populate available versions. */
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
    const safeSet = new Set(data.safe_versions || ['1.21.11', '26.3']);
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

/** Close the version download modal. */
function closeServerDownloadModal() {
  document.getElementById('server-download-modal')?.classList.add('hidden');
}

/* ─── Server Manager: Switch Version Modal ─── */

/** Open the version switch modal for the installed versions. */
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

/** Close the version switch modal. */
function closeServerSwitchModal() {
  document.getElementById('server-switch-modal')?.classList.add('hidden');
}

/** Download the selected server version and report already-installed versions. */
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
/** Open the custom jar upload modal with reset fields. */
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

/** Close the custom jar upload modal. */
function closeServerCustomModal() {
  document.getElementById('server-custom-modal')?.classList.add('hidden');
}

/** Validate the custom jar form, enabling the upload button only for a `.jar` file. */
function validateServerCustomForm() {
  const name = document.getElementById('server-custom-name')?.value?.trim();
  const file = document.getElementById('server-custom-file')?.files?.[0];
  const confirmBtn = document.getElementById('server-custom-confirm');
  if (confirmBtn) confirmBtn.disabled = !(name && file && file.name.endsWith('.jar'));
}

/** Upload the selected custom server jar. */
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

/** Render the copyable browser overlay URLs for the configured overlays. */
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

/** Send a test message to one overlay and reflect progress on its button. */
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
