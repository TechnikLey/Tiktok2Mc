/**
 * @file Backup management and config-bundle export/import.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Backups ─── */
let _backupsData = { categories: [], total: 0 };

/** Fetch the backup inventory and render it. */
async function loadBackups() {
  try {
    const data = await fetchJSON('/backups');
    _backupsData = data && Array.isArray(data.categories) ? data : { categories: [], total: 0 };
    renderBackups();
  } catch (e) {
    log('Backups load failed: ' + e.message, 'err');
    const root = document.getElementById('backups-root');
    if (root) root.innerHTML = '<p class="text-muted">' + I18N.t('backups.failedLoad') + '</p>';
  }
}

/** Format a byte count using B, KB or MB units. */
function _formatBytes(n) {
  const v = Number(n) || 0;
  if (v < 1024) return v + ' B';
  if (v < 1048576) return (v / 1024).toFixed(1) + ' KB';
  return (v / 1048576).toFixed(1) + ' MB';
}

/** Return the localized label for a backup category. */
function _backupCategoryLabel(category) {
  if (category === 'config') return I18N.t('backups.catConfig');
  if (category === 'actions') return I18N.t('backups.catActions');
  if (category === 'event_commands') return I18N.t('backups.catEventCommands');
  if (category === 'plugin_registry') return I18N.t('backups.catPluginRegistry');
  if (category === 'migration') return I18N.t('backups.catMigration');
  if (category === '_other') return I18N.t('backups.catOther');
  if (category === 'hook_registry') return I18N.t('backups.catHookRegistry');
  if (category.startsWith('plugins/')) return I18N.t('backups.catPlugin') + ': ' + escapeHtml(category.slice('plugins/'.length));
  return escapeHtml(category);
}

/** Render the backup table with size, age and restore actions. */
function renderBackups() {
  const root = document.getElementById('backups-root');
  if (!root) return;
  if (!_backupsData.categories.length) {
    root.innerHTML = '<p class="text-muted">' + I18N.t('backups.empty') + '</p>';
    return;
  }
  const colWhen = I18N.t('backups.colWhen');
  const colFile = I18N.t('backups.colFile');
  const colSize = I18N.t('backups.colSize');
  const colAction = I18N.t('backups.colAction');
  const html = _backupsData.categories.map(cat => {
    const needsCustomTarget = cat.category === '_other' || cat.category === 'hook_registry';
    const rows = cat.entries.map(e => {
      const restoreBtn = e.restorable
        ? `<button class="btn btn--secondary btn--sm" onclick="restoreBackup('${e.category}', '${e.filename}')">${I18N.t('backups.restore')}</button>`
        : `<button class="btn btn--secondary btn--sm" onclick="restoreBackupCustom('${e.category}', '${e.filename}')">${I18N.t('backups.restore')}</button>`;
      return '<tr>' +
        '<td data-label="' + colWhen + '">' + escapeHtml(e.label || '—') + '</td>' +
        '<td class="backup-filename" data-label="' + colFile + '">' + escapeHtml(e.filename) + '</td>' +
        '<td data-label="' + colSize + '">' + _formatBytes(e.size) + '</td>' +
        '<td class="backup-actions" data-label="' + colAction + '">' + restoreBtn + '</td>' +
        '</tr>';
    }).join('');
    return '<section class="view-section backup-category">' +
      '<h3>' + _backupCategoryLabel(cat.category) + ' <span class="backup-count">' + cat.count + '</span></h3>' +
      '<div class="backup-table-wrap">' +
      '<table class="backup-table"><thead><tr>' +
      '<th>' + colWhen + '</th>' +
      '<th>' + colFile + '</th>' +
      '<th>' + colSize + '</th>' +
      '<th></th></tr></thead><tbody>' + rows + '</tbody></table>' +
      '</div></section>';
  }).join('');
  root.innerHTML = html;
}

/** Restore a backup from a known category. */
function restoreBackup(category, filename) {
  showConfirmDialog(
    I18N.t('backups.restoreTitle'),
    I18N.t('backups.restoreWarning', { filename }),
    I18N.t('backups.restore'),
    'btn-danger'
  ).then(confirmed => {
    if (!confirmed) return;
    postJSON('/backups/restore', { category, filename })
      .then(() => {
        showToast(I18N.t('backups.restored'), 'success');
        loadBackups();
      })
      .catch(e => showToast(e.message, 'error'));
  });
}

/** Restore a backup from a category that needs a user-supplied target name. */
async function restoreBackupCustom(category, filename) {
  const target = await showPromptDialog(
    I18N.t('backups.restoreTitle'),
    I18N.t('backups.restoreCustomTarget', { filename }),
    '',
    I18N.t('backups.restore'),
    'btn-danger'
  );
  if (!target) return;
  const confirmed = await showConfirmDialog(
    I18N.t('backups.restoreTitle'),
    I18N.t('backups.restoreCustomWarning', { filename, target }),
    I18N.t('backups.restore'),
    'btn-danger'
  );
  if (!confirmed) return;
  try {
    await postJSON('/backups/restore', { category, filename, target });
    showToast(I18N.t('backups.restored'), 'success');
    loadBackups();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

/** Create backups for the config, actions and plugin registry. */
async function createBackupsNow() {
  try {
    const res = await postJSON('/backups/create', { targets: ['config', 'actions', 'plugin_registry'] });
    const count = res.created ? res.created.length : 0;
    showToast(count > 0 ? I18N.t('backups.created', { count }) : I18N.t('backups.upToDate'), count > 0 ? 'success' : 'info');
    loadBackups();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

/* ─── Config Bundle ─── */

/** Convert an `ArrayBuffer` to a base64 string for the pywebview download bridge. */
function _arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/** Export the configuration bundle as a zip download. */
async function exportConfigBundle() {
  try {
    showToast(I18N.t('backups.bundleExporting'), 'info');
    const resp = await fetch(API + '/config-bundle', { headers: _withApiKey({}) });
    if (!resp.ok) await _throwResError(resp);
    const buf = await resp.arrayBuffer();
    const filename = 'tiktok2mc-config-bundle.zip';

    if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.download_file_b64) {
      const path = await pywebview.api.download_file_b64(_arrayBufferToBase64(buf), filename);
      if (path && !path.startsWith('error:')) {
        showToast(I18N.t('backups.bundleExportedPath', { path }), 'success');
      } else {
        showToast(I18N.t('backups.bundleExportFailed'), 'error');
      }
      return;
    }

    const blob = new Blob([buf], { type: 'application/zip' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(I18N.t('backups.bundleExportedPath', { path: filename }), 'success');
  } catch (e) {
    showToast(e.message || I18N.t('backups.bundleExportFailed'), 'error');
  }
}

/** Ask for a config bundle zip and upload it. */
function importConfigBundle() {
  const input = document.getElementById('bundle-file-input');
  if (!input) return;
  input.value = '';
  input.onchange = () => {
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;
    showConfirmDialog(
      I18N.t('backups.bundleImportTitle'),
      I18N.t('backups.bundleImportWarning'),
      I18N.t('backups.bundleImport'),
      'btn-primary'
    ).then(confirmed => {
      if (confirmed) _uploadConfigBundle(file);
    });
  };
  input.click();
}

/** Upload a config bundle zip after user confirmation. */
async function _uploadConfigBundle(file) {
  try {
    showToast(I18N.t('backups.bundleImporting'), 'info');
    const form = new FormData();
    form.append('file', file, file.name || 'bundle.zip');
    const resp = await fetch(API + '/config-bundle/import', {
      method: 'POST',
      headers: _withApiKey({}),
      body: form
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(body.detail || I18N.t('backups.bundleImportFailed', { msg: resp.status }));
    }
    showToast(I18N.t('backups.bundleImported', { count: body.count || 0 }), 'success');
    loadBackups();
  } catch (e) {
    showToast(e.message || I18N.t('backups.bundleImportFailed', { msg: '' }), 'error');
  }
}

