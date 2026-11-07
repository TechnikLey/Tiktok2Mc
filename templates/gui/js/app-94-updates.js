/**
 * @file Update checks/application and update notification.
 *
 * The update-button wiring block at the end must stay after the update functions it references.
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Update Checker ─── */
let _updateData = null;
let _lastResultToastCode = null;
let _autoInstallEnabled = true;
let _updateNotificationShown = false;

/** Check the tool, plugin and hook update endpoints in parallel and render the result. */
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

/** Render update-check results grouped by component with version details. */
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

/** Install pending plugin and hook updates, then offer the required restart. */
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

/** Show the update-available notification. */
function showUpdateNotification(version) {
  const desc = document.getElementById('update-notification-desc');
  if (desc) {
    desc.textContent = I18N.t('updates.popupDesc', { version: version });
  }
  document.getElementById('update-notification-dialog').classList.remove('hidden');
}

/** Hide the update-available notification. */
function hideUpdateNotification() {
  document.getElementById('update-notification-dialog').classList.add('hidden');
}

/** Start the self-update for the application itself. */
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

document.getElementById('btn-update-now').addEventListener('click', () => {
  hideUpdateNotification();
  triggerToolUpdate();
});

document.getElementById('btn-update-dismiss').addEventListener('click', hideUpdateNotification);
