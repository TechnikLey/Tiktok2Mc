/**
 * @file Plugin manager, plugin pages/frames and readme modal.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/** Return the operating-system identifier used by plugin compatibility checks. */
function _currentOS() {
  const p = (navigator.platform || '').toLowerCase();
  return p.includes('win') ? 'windows' : 'linux';
}

/** Return the localized platform label. */
function _platformLabel(platform) {
  if (!platform || platform === 'all') return I18N.t('plugins.platformAll');
  if (platform === 'linux') return I18N.t('plugins.platformLinux');
  if (platform === 'windows') return I18N.t('plugins.platformWindows');
  return platform;
}

/** Return whether a plugin supports the current platform. */
function _isPlatformCompatible(plugin) {
  const pp = plugin.platform || 'all';
  return pp === 'all' || pp === _currentOS();
}

/** Render the plugin manager table, including error details and row actions. */
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
      : (p.platform && p.platform !== 'all' ? '<span class="plugin-status status-info">' + _platformLabel(p.platform) + '</span>' : '<span class="text-muted">' + _platformLabel(p.platform) + '</span>');
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

/** Return the DOM id of a plugin's dashboard view. */
function pluginPageViewId(name) {
  return PLUGIN_PAGE_PREFIX + name;
}

/** Return the active GUI theme identifier. */
function _currentGuiTheme() {
  return document.documentElement.getAttribute('data-theme') || 'dark';
}

/** Build a plugin dashboard URL with the current theme applied. */
function _pluginPageUrl(name, theme) {
  let url = API + '/plugins/' + encodeURIComponent(name) + '/dashboard';
  if (theme) url += '?theme=' + encodeURIComponent(theme);
  return url;
}

/** Retarget existing plugin iframes to a new theme. */
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

/** Render dashboard navigation entries for plugins that provide pages. */
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

/** Open a plugin dashboard page, creating and loading its iframe lazily. */
function openPluginDashboard(name) {
  const view = document.getElementById('view-' + pluginPageViewId(name));
  if (!view) return;
  const frame = view.querySelector('iframe');
  if (frame && !frame.src && frame.dataset.src) frame.src = frame.dataset.src;
  switchView(pluginPageViewId(name));
}

/* ─── Plugin View ─── */

/** Open the inline configuration editor for a plugin. */
function openInlinePluginConfig(pluginName, displayName) {  _hideAllEditors();
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelector('.nav-item[data-view="plugins"]')?.classList.add('active');
  pluginEditor.openInline(pluginName, displayName);
}

/** Close the inline plugin configuration editor. */
function closeInlinePluginConfig() {
  pluginEditor.closeInline();
}

/** Copy a URL to the clipboard and show a confirmation toast. */
function copyUrl(btn, url) {
  navigator.clipboard.writeText(url).then(() => {
    btn.textContent = I18N.t('common.copied');
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = I18N.t('common.copy'); btn.classList.remove('copied'); }, 1500);
  });
}

/** Return whether a plugin is built in (and therefore not user-installable). */
function isBuiltinPlugin(name) {
  // Bundled status comes from the plugin manifest ("bundled": true) via
  // GET /plugins — the frontend must not hardcode plugin names.
  const plugin = currentPlugins.find(p => p.name === name);
  return !!(plugin && plugin.bundled);
}

/** Confirm enabling a plugin, warn for external plugins and update the registry. */
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

/** Confirm disabling a plugin and update the registry. */
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

/** Restart a plugin by disabling it, waiting briefly and enabling it again. */
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

/** Open a plugin README in a sanitized Markdown modal. */
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

/** Close the README modal. */
function closeReadmeModal() {
  document.getElementById('readme-modal')?.classList.add('hidden');
}

