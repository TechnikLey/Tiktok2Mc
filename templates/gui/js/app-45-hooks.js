/**
 * @file Hook and builtin-hook manager.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Hook Management ─── */

/** Return the display status for a hook record. */
function getHookStatus(h) {
  if (h.error) return { label: I18N.t('common.error'), cls: 'status-error' };
  if (!h.enabled) return { label: I18N.t('common.disabled'), cls: 'status-disabled' };
  return { label: I18N.t('common.enabled'), cls: 'status-enabled' };
}

/** Fetch the hook registry and render the hook manager. */
async function loadHooks() {
  try {
    const data = await fetchJSON('/hooks');
    currentHooks = data.hooks || [];
    renderHookManager();
  } catch (e) {
    log('Hooks load failed: ' + e.message, 'err');
  }
}

/** Reload hooks and refresh the manager and dashboard navigation. */
async function refreshHooks() {
  try {
    await postJSON('/hooks/discover', {});
    await loadHooks();
    showToast(I18N.t('plugins.refreshed'), 'success');
  } catch (e) {
    showToast(I18N.t('hooks.refreshFailed', { msg: e.message }), 'error');
  }
}

/** Render the built-in action manager table. */
async function renderBuiltinManager() {
  const div = document.getElementById('builtin-list');
  if (!div) return;
  div.innerHTML = '<p class="muted">Loading...</p>';
  try {
    const data = await fetchJSON('/builtins');
    const builtins = data.builtins || [];
    if (!builtins.length) {
      div.innerHTML = '<p class="muted">No built-in actions.</p>';
      return;
    }
    let html = '<table class="plugin-table"><thead><tr><th>Name</th><th>Description</th><th>Actions</th></tr></thead><tbody>';
    for (const b of builtins) {
      const name = escapeHtml(b.name);
      html += '<tr>';
      html += '<td>' + escapeHtml(b.display_name || b.name) + '</td>';
      html += '<td>' + escapeHtml(b.description || '') + '</td>';
      html += '<td><button class="btn btn-secondary" style="padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="openInlineBuiltinConfig(\'' + name + '\', \'' + escapeHtml(b.display_name || b.name) + '\')">Edit Config</button></td>';
      html += '</tr>';
    }
    html += '</tbody></table>';
    div.innerHTML = html;
  } catch (e) {
    div.innerHTML = '<p class="muted">Failed to load built-ins: ' + escapeHtml(e.message) + '</p>';
  }
}

/** Open the inline configuration editor for a built-in action. */
function openInlineBuiltinConfig(name, displayName) {
  _hideAllEditors();
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelector('.nav-item[data-view="builtins"]')?.classList.add('active');
  builtinEditor.openInline(name, displayName);
}

/** Close the inline built-in configuration editor. */
function closeInlineBuiltinConfig() {
  builtinEditor.closeInline();
}

/** Render the hook manager table with enable, disable and config actions. */
function renderHookManager() {
  const tableDiv = document.getElementById('hook-manager-table');
  if (!tableDiv) return;
  if (!currentHooks.length) {
    tableDiv.innerHTML = '<p class="muted">' + I18N.t('hooks.noHooks') + '</p>';
    return;
  }
  let html = '<table class="plugin-table"><thead><tr><th>Name</th><th>Version</th><th>Plugin</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
  for (const h of currentHooks) {
    const status = getHookStatus(h);
    const hasError = !!h.error;
    const errorTitle = hasError ? ` title="${escapeHtml(h.error)}"` : '';
    const enableDisabled = hasError || h.enabled ? ' disabled' : '';
    const action = h.enabled
      ? `<button class="btn btn-danger" style="padding:0.3rem 0.6rem;font-size:0.8rem;" onclick="promptDisableHook('${h.name}', '${escapeHtml(h.display_name || h.name)}')">${I18N.t('common.disable')}</button>`
      : `<button class="btn btn-primary" style="padding:0.3rem 0.6rem;font-size:0.8rem;"${enableDisabled} onclick="promptEnableHook('${h.name}', '${escapeHtml(h.display_name || h.name)}')">${I18N.t('common.enable')}</button>`;
    const editDisabled = hasError ? ' disabled' : '';
    const canEdit = h.config_schema;
    html += `<tr${errorTitle}>
      <td data-label="Name">${escapeHtml(h.display_name || h.name)}${hasError ? ' <span class="status-error-indicator" title="' + escapeHtml(h.error) + '">⚠️</span>' : ''}</td>
      <td data-label="Version">${h.version || '-'}</td>
      <td data-label="Plugin">${h.plugin || '-'}</td>
      <td data-label="Status"><span class="plugin-status ${status.cls}">${status.label}</span></td>
      <td data-label="Actions">${action}${canEdit ? ` <button class="btn btn-secondary" style="padding:0.3rem 0.6rem;font-size:0.8rem;"${editDisabled} onclick="openInlineHookConfig('${h.name}', '${escapeHtml(h.display_name || h.name)}')">Edit Config</button>` : ''}</td>
    </tr>`;
    if (hasError) {
      html += `<tr class="error-detail-row"><td colspan="5"><span class="error-detail">${escapeHtml(h.error)}</span></td></tr>`;
    }
  }
  html += '</tbody></table>';
  tableDiv.innerHTML = html;
}

/** Confirm enabling a hook and update the registry; a restart is required. */
async function promptEnableHook(name, displayName) {
  const confirmed = await showConfirmDialog(
    I18N.t('hooks.enableTitle'),
    I18N.t('hooks.enableConfirm', { name: displayName || name }),
    I18N.t('common.enable'),
    'btn-primary'
  );
  if (!confirmed) return;
  try {
    await postJSON(`/hooks/${name}/enable`, {});
    showToast(I18N.t('hooks.enabledToast', { name: displayName || name }), 'success');
    log(`Hook ${name} enabled (restart required)`);
    await loadHooks();
  } catch (e) {
    const msg = I18N.t('hooks.enableFailed', { name: displayName || name, msg: e.message });
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

/** Confirm disabling a hook and update the registry; a restart is required. */
async function promptDisableHook(name, displayName) {
  const confirmed = await showConfirmDialog(
    I18N.t('hooks.disableTitle'),
    I18N.t('hooks.disableConfirm', { name: displayName || name }),
    I18N.t('common.disable'),
    'btn-danger'
  );
  if (!confirmed) return;
  try {
    await postJSON(`/hooks/${name}/disable`, {});
    showToast(I18N.t('hooks.disabledToast', { name: displayName || name }), 'info');
    log(`Hook ${name} disabled (restart required)`);
    await loadHooks();
  } catch (e) {
    const msg = I18N.t('hooks.disableFailed', { name: displayName || name, msg: e.message });
    showToast(msg, 'error');
    log(msg, 'err');
  }
}

/* ─── Hook Nav ─── */

/** Open the inline configuration editor for a hook. */
function openInlineHookConfig(hookName, displayName) {
  _hideAllEditors();
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelector('.nav-item[data-view="hooks"]')?.classList.add('active');
  hookEditor.openInline(hookName, displayName);
}

/** Close the inline hook configuration editor. */
function closeInlineHookConfig() {
  hookEditor.closeInline();
}

