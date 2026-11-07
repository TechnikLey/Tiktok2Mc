/**
 * @file Editor instances, unsaved-change guards and close-request handling.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
const reactionEditor = new ReactionEditor();
const commentCommandsEditor = new CommentCommandsEditor();
const pluginEditor = new PluginConfigEditor();
const actionsEditor = new ActionsEditor();

/* ─── Unsaved changes warning on window close ─── */
let _closeInProgress = false;
let _pendingNavigation = null;

// Fallback for browser testing (no pywebview API)
if (typeof pywebview === 'undefined' || !pywebview.api) {
  window.addEventListener('beforeunload', function (e) {
    if (isAnyEditorDirty()) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
}

/** Return whether any open editor has unsaved changes. */
function isAnyEditorDirty() {
  return editor.isDirty() || pluginEditor.isDirty() || actionsEditor.isDirty || reactionEditor.isDirty() || commentCommandsEditor.isDirty() || chatbotEditor.isDirty();
}

/* Detect close requests from pywebview's on_closing (deadlock-free polling) */
/** Poll the native window for a pending close request and handle it. */
async function _pollCloseRequest() {
  if (_closeInProgress) return;
  try {
    const requested = await pywebview.api.close_requested();
    if (!requested) return;
    await pywebview.api.reset_close_request();
    await _handleCloseRequest();
  } catch (_) {}
}

/** Handle a window close request: close immediately when clean, otherwise ask the user to save or discard. */
async function _handleCloseRequest() {
  if (_closeInProgress) return;
  if (!isAnyEditorDirty()) {
    _closeInProgress = true;
    await pywebview.api.approve_close();
    window.close();
    return;
  }
  _closeInProgress = true;
  document.getElementById('btn-unsaved-save-exit').textContent = I18N.t('dialog.saveExit');
  document.getElementById('btn-unsaved-exit-no-save').textContent = I18N.t('dialog.exitNoSave');
  document.getElementById('unsaved-changes-modal').classList.remove('hidden');
}

/** Save every dirty editor, reload state and restart the server or plugins when required. */
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
  if (commentCommandsEditor.isDirty()) {
    await commentCommandsEditor.save();
    if (commentCommandsEditor.isDirty()) {
      throw new Error('Comment commands editor could not be saved — check for errors.');
    }
  }
  if (chatbotEditor.isDirty()) {
    await chatbotEditor.save();
    if (chatbotEditor.isDirty()) {
      throw new Error('Chatbot editor could not be saved — check for errors.');
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
    showToast(I18N.t('plugins.changesAppliedRestart'), 'success');
  }
}

/** Discard unsaved changes in every editor and restore the loaded values. */
function _discardAllEditors() {
  if (actionsEditor.isDirty) {
    actionsEditor.isDirty = false;
    actionsEditor._updateSaveButton();
  }
  if (reactionEditor.isDirty()) {
    reactionEditor._dirty = false;
    reactionEditor._updateSaveButton();
  }
  if (commentCommandsEditor.isDirty()) {
    commentCommandsEditor._dirty = false;
    commentCommandsEditor._updateSaveButton();
  }
  if (editor.isDirty()) {
    editor.data = JSON.parse(JSON.stringify(editor.original));
    currentConfig = JSON.parse(JSON.stringify(editor.original));
    editor._updateSaveButton();
  }
  if (pluginEditor.isDirty()) {
    pluginEditor.config = JSON.parse(JSON.stringify(pluginEditor.original));
    pluginEditor._updateSaveButton();
  }
}

document.getElementById('btn-unsaved-save-exit').addEventListener('click', async () => {
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  const navigate = _pendingNavigation;
  _pendingNavigation = null;
  try {
    await _saveAllEditors();
    if (navigate) {
      navigate();
    } else {
      _closeInProgress = true;
      await pywebview.api.approve_close();
      window.close();
    }
  } catch (e) {
    showToast(I18N.t('plugins.saveFailedExit', { msg: e.message }), 'error');
    _closeInProgress = false;
  }
});

document.getElementById('btn-unsaved-exit-no-save').addEventListener('click', async () => {
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  const navigate = _pendingNavigation;
  _pendingNavigation = null;
  if (navigate) {
    _discardAllEditors();
    navigate();
  } else {
    _closeInProgress = true;
    await pywebview.api.approve_close();
    window.close();
  }
});

document.getElementById('btn-unsaved-cancel').addEventListener('click', () => {
  document.getElementById('unsaved-changes-modal').classList.add('hidden');
  _pendingNavigation = null;
  _closeInProgress = false;
});

