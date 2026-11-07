/**
 * @file Shutdown countdown, TikTok connection-failure dialog and shared confirm/prompt dialogs.
 *
 * Also owns the small UI-shell helpers used by the navigation and dashboard parts.
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Shutdown Countdown (local — just closes the GUI window) ─── */
let _shutdownCountdownInterval = null;
let _shutdownCountdownValue = 30;
let _healthIntervalId = null;
let _statusIntervalId = null;
let _pluginsIntervalId = null;
let _hooksIntervalId = null;
let _closePollIntervalId = null;
let _uptimeIntervalId = null;
let _lastTiktokEventTime = 0;
let _tiktokLiveState = null; // null = unknown, true = live, false = not live
let _tiktokConnectDisabled = false; // bridge DISABLE_TIKTOK_CONNECT flag

/* ─── Server Manager Placeholder Data ─── */
let _serverManagerCache = null;
let _serverActionInProgress = false;

/** Stop every dashboard refresh interval and forget its handle. */
function _stopDashboardPolling() {
  if (_healthIntervalId) { clearInterval(_healthIntervalId); _healthIntervalId = null; }
  if (_statusIntervalId) { clearInterval(_statusIntervalId); _statusIntervalId = null; }
  if (_pluginsIntervalId) { clearInterval(_pluginsIntervalId); _pluginsIntervalId = null; }
  if (_hooksIntervalId) { clearInterval(_hooksIntervalId); _hooksIntervalId = null; }
  if (_uptimeIntervalId) { clearInterval(_uptimeIntervalId); _uptimeIntervalId = null; }
}

/** Close the dashboard for shutdown: stop polling, close the SSE stream and request the native window to close. */
function _closeWindowForShutdown() {
  _stopDashboardPolling();
  if (_sseSource) { _sseSource.close(); _sseSource = null; }
  try { window.close(); } catch (_) {}
  if (typeof pywebview !== 'undefined' && pywebview.api) {
    try { pywebview.api.close_app(); } catch (_) {}
  }
}

/** Show the local 30-second shutdown countdown and disable its action buttons until the user chooses. */
function startLocalShutdownCountdown() {
  _shutdownCountdownValue = 30;
  const overlay = document.getElementById('shutdown-overlay');
  const display = document.getElementById('shutdown-countdown-display');
  const shutdownNowBtn = document.getElementById('btn-shutdown-now');
  const cancelBtn = document.getElementById('btn-shutdown-cancel');

  overlay.classList.remove('hidden');
  display.textContent = _shutdownCountdownValue + ' ' + I18N.t('dialog.seconds');
  shutdownNowBtn.disabled = false;
  cancelBtn.disabled = false;

  if (_shutdownCountdownInterval) clearInterval(_shutdownCountdownInterval);
  _shutdownCountdownInterval = setInterval(() => {
    _shutdownCountdownValue--;
    if (_shutdownCountdownValue <= 0) {
      clearInterval(_shutdownCountdownInterval);
      _shutdownCountdownInterval = null;
      display.textContent = I18N.t('dialog.shuttingDown');
      shutdownNowBtn.disabled = true;
      cancelBtn.disabled = true;
      _closeWindowForShutdown();
      return;
    }
  display.textContent = _shutdownCountdownValue + ' ' + I18N.t('dialog.seconds');
  }, 1000);
}

document.getElementById('btn-shutdown-now').addEventListener('click', () => {
  if (_shutdownCountdownInterval) {
    clearInterval(_shutdownCountdownInterval);
    _shutdownCountdownInterval = null;
  }
  document.getElementById('shutdown-countdown-display').textContent = I18N.t('dialog.shuttingDown');
  document.getElementById('btn-shutdown-now').disabled = true;
  document.getElementById('btn-shutdown-cancel').disabled = true;
  _closeWindowForShutdown();
});

document.getElementById('btn-shutdown-cancel').addEventListener('click', () => {
  if (_shutdownCountdownInterval) {
    clearInterval(_shutdownCountdownInterval);
    _shutdownCountdownInterval = null;
  }
  document.getElementById('shutdown-overlay').classList.add('hidden');
});


/* ─── TikTok Connection Failure Dialog ─── */
let _tiktokFailedDialogActive = false;

/** Show the blocking dialog that explains repeated TikTok connection failures. */
function showTiktokFailedDialog(maxFails) {
  const dlg = document.getElementById('tiktok-failed-dialog');
  if (!dlg || _tiktokFailedDialogActive) return;
  const msg = document.getElementById('tiktok-failed-message');
  if (msg) {
    msg.textContent = I18N.t('dialog.tiktokFailed.message', { count: maxFails || 1 });
  }
  const hint = document.getElementById('tiktok-failed-hint');
  if (hint) {
    hint.textContent = I18N.t('dialog.tiktokFailed.hint');
  }
  dlg.classList.remove('hidden');
  _tiktokFailedDialogActive = true;
  _tiktokConnectDisabled = true;
  _updateTiktokStatusDisplay();
}

/** Hide the TikTok connection failure dialog. */
function hideTiktokFailedDialog() {
  const dlg = document.getElementById('tiktok-failed-dialog');
  if (!dlg) return;
  dlg.classList.add('hidden');
  _tiktokFailedDialogActive = false;
}

document.getElementById('btn-tiktok-failed-reconnect')?.addEventListener('click', async () => {
  hideTiktokFailedDialog();
  try {
    const result = await postJSON('/triggers/tiktok-connection', {});
    if (result.status === 'ok' || result.status === 'success') {
      _tiktokConnectDisabled = !result.connected;
      _updateTiktokStatusDisplay();
      showToast(I18N.t('triggers.connectionNow', { state: result.connected ? I18N.t('triggers.on') : I18N.t('triggers.off') }), 'success');
      log(`[TIKTOK] Reconnect requested from failure dialog: ${result.connected ? 'ON' : 'OFF'}`, 'info');
    } else {
      showToast((result.message || I18N.t('triggers.toggleFailedTitle')), 'error');
    }
  } catch (e) {
    showToast(I18N.t('triggers.toggleFailed', { msg: e.message }), 'error');
  }
});

document.getElementById('btn-tiktok-failed-keep-off')?.addEventListener('click', () => {
  hideTiktokFailedDialog();
  showToast(I18N.t('dialog.tiktokFailed.keepOffConfirmed'), 'info');
});


/* ─── Dialogs ─── */
/**
 * Show a modal confirmation dialog.
 *
 * Returns a promise resolving to `true` when confirmed; Escape and the cancel button resolve to `false`.
 */
function showConfirmDialog(title, message, okText = I18N.t('common.confirm'), okClass = 'btn-primary', messageClass = '') {
  return new Promise((resolve) => {
    const dlg = document.getElementById('confirm-dialog');
    const titleEl = document.getElementById('confirm-title');
    const msgEl = document.getElementById('confirm-message');
    const okBtn = document.getElementById('btn-confirm-ok');
    const cancelBtn = document.getElementById('btn-confirm-cancel');

    titleEl.textContent = title;
    msgEl.textContent = message;
    msgEl.className = 'muted dialog-desc' + (messageClass ? ' ' + messageClass : '');
    okBtn.textContent = okText;
    okBtn.className = 'btn ' + okClass;

    const cleanup = () => {
      dlg.classList.add('hidden');
      document.removeEventListener('keydown', onKey);
      okBtn.replaceWith(okBtn.cloneNode(true));
      cancelBtn.replaceWith(cancelBtn.cloneNode(true));
    };

    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      cleanup();
      resolve(false);
    };

    const newOk = okBtn.cloneNode(true);
    const newCancel = cancelBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOk, okBtn);
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);

    newOk.addEventListener('click', () => { cleanup(); resolve(true); });
    newCancel.addEventListener('click', () => { cleanup(); resolve(false); });

    dlg.classList.remove('hidden');
    document.addEventListener('keydown', onKey);
  });
}

/** Show a modal prompt dialog and resolve to the trimmed input, or `null` when cancelled. */
function showPromptDialog(title, message, defaultValue = '', okText = I18N.t('common.confirm'), okClass = 'btn-primary') {
  return new Promise((resolve) => {
    const dlg = document.getElementById('prompt-dialog');
    const titleEl = document.getElementById('prompt-title');
    const msgEl = document.getElementById('prompt-message');
    const input = document.getElementById('prompt-input');
    const okBtn = document.getElementById('btn-prompt-ok');
    const cancelBtn = document.getElementById('btn-prompt-cancel');

    titleEl.textContent = title;
    msgEl.textContent = message;
    msgEl.className = 'muted dialog-desc';
    okBtn.textContent = okText;
    okBtn.className = 'btn ' + okClass;
    input.value = defaultValue;

    const cleanup = () => {
      dlg.classList.add('hidden');
      document.removeEventListener('keydown', onKey);
      okBtn.replaceWith(okBtn.cloneNode(true));
      cancelBtn.replaceWith(cancelBtn.cloneNode(true));
    };

    const submit = () => {
      const val = input.value.trim();
      cleanup();
      resolve(val || null);
    };

    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        cleanup();
        resolve(null);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        submit();
      }
    };

    const newOk = okBtn.cloneNode(true);
    const newCancel = cancelBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOk, okBtn);
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);

    newOk.addEventListener('click', submit);
    newCancel.addEventListener('click', () => { cleanup(); resolve(null); });

    dlg.classList.remove('hidden');
    input.focus();
    input.select();
    document.addEventListener('keydown', onKey);
  });
}

