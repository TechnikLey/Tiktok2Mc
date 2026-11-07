/**
 * @file First-run config wizard, password validation and restart handling.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
async function promptShutdown() {
  const confirmed = await showConfirmDialog(
    I18N.t('dialog.shutdownTitle'),
    I18N.t('dialog.shutdownMessage'),
    I18N.t('dialog.shutdown'),
    'btn-danger'
  );
  if (!confirmed) return;
  startLocalShutdownCountdown();
}

/** Open the main configuration editor view. */
function openConfigEditor() {
  // Ensure currentConfig is loaded before opening
  if (currentConfig && Object.keys(currentConfig).length > 0) {
    editor.open(currentConfig);
  } else {
    // Reload config first
    fetchJSON('/config').then(data => {
      currentConfig = data.config || {};
      editor.open(currentConfig);
    }).catch(() => {
      editor.open(currentConfig); // open with whatever we have
    });
  }
}

/** Load `config.yaml` into the configuration editor. */
async function loadConfig() {
  try {
    const data = await fetchJSON('/config');
    currentConfig = data.config || {};
  } catch (e) {
    log('Config load failed: ' + e.message, 'err');
    return;
  }
  const el = document.getElementById('config-summary');
  if (!el) return;
  const tiktok = currentConfig.tiktok || {};
  const rcon = currentConfig.rcon || {};
  el.innerHTML = `
    <div class="field-row"><span>${I18N.t('wizard.tiktokUserLabel')}</span><span>${escapeHtml(tiktok.user || '—')}</span></div>
    <div class="field-row"><span>${I18N.t('config.serverHost')}</span><span>${escapeHtml(currentConfig.server_host || '—')}</span></div>
    <div class="field-row"><span>${I18N.t('config.rconEnabled')}</span><span>${rcon.enabled ? I18N.t('common.yes') : I18N.t('common.no')}</span></div>
    <div class="field-row"><span>${I18N.t('config.controlMethod')}</span><span>${escapeHtml(currentConfig.control_method || '—')}</span></div>`;
}

/* ─── Wizard (preserved) ─── */
/** Return whether the configuration still looks like a first-run install. */
function isFirstRun(cfg) {
  const tiktok = cfg.tiktok || {};
  const rcon = cfg.rcon || {};
  return tiktok.user === 'your_tiktok_username' || !rcon.password;
}
/** Show the first-run setup wizard. */
function showWizard() {
  document.getElementById('wizard').classList.remove('hidden');
  document.getElementById('dashboard').classList.add('hidden');
  const rawTiktokUser = (currentConfig.tiktok || {}).user || '';
  const rawRconPassword = (currentConfig.rcon || {}).password || '';
  const tiktokOk = rawTiktokUser && rawTiktokUser !== 'your_tiktok_username';
  const rconOk = !!rawRconPassword;
  // Skip already-configured steps
  wizardStep = tiktokOk ? 1 : 0;
  wizardData = {
    tiktok_user: tiktokOk ? rawTiktokUser : '',
    rcon_password: rconOk ? rawRconPassword : '',
  };
  renderWizardStep();
}
/** Hide the first-run setup wizard. */
function hideWizard() {
  document.getElementById('wizard').classList.add('hidden');
  document.getElementById('dashboard').classList.remove('hidden');
}
let _restartPending = false;

/** Show the restart-required dialog. */
function showRestartDialog(title, message) {
  const card = document.querySelector('#restart-dialog .wizard-card');
  card.innerHTML = `
    <h2 style="border:none;padding:0;">${escapeHtml(title || I18N.t('wizard.restartRequired'))}</h2>
    <p class="muted" style="margin-bottom:1.5rem;">${escapeHtml(message || I18N.t('wizard.restartMessage'))}</p>
    <div style="display:flex;gap:1rem;justify-content:center;">
      <button class="btn btn-primary" id="btn-restart-now">${I18N.t('restart.now')}</button>
      <button class="btn btn-secondary" id="btn-restart-later">${I18N.t('restart.later')}</button>
    </div>
  `;
  // Re-attach listeners since we replaced the innerHTML
  document.getElementById('btn-restart-now').addEventListener('click', triggerRestart);
  document.getElementById('btn-restart-later').addEventListener('click', () => { hideRestartDialog(); loadConfig(); });
  document.getElementById('wizard').classList.add('hidden');
  document.getElementById('restart-dialog').classList.remove('hidden');
}
/** Hide the restart-required dialog. */
function hideRestartDialog() {
  document.getElementById('restart-dialog').classList.add('hidden');
  document.getElementById('wizard').classList.add('hidden');
  document.getElementById('dashboard').classList.remove('hidden');
  updateRestartBanner();
}

/** Show or hide the persistent restart banner based on pending state. */
function updateRestartBanner() {
  const banner = document.getElementById('restart-pending-banner');
  if (banner) {
    banner.classList.toggle('hidden', !_restartPending);
  }
}
/** Render the current step of the first-run wizard. */
function renderWizardStep() {
  const steps = document.getElementById('wizard-steps');
  const content = document.getElementById('wizard-content');
  const backBtn = document.getElementById('wizard-back');
  const nextBtn = document.getElementById('wizard-next');
  // Only 2 configurable steps + review: tiktok, rcon, review
  const totalSteps = 3;
  steps.innerHTML = [0, 1, 2].map(i => `<div class="step-dot ${i === wizardStep ? 'active' : i < wizardStep ? 'done' : ''}"></div>`).join('');
  backBtn.disabled = wizardStep === 0;
  backBtn.style.visibility = wizardStep === 0 ? 'hidden' : 'visible';
  nextBtn.textContent = wizardStep === 2 ? I18N.t('wizard.save') : I18N.t('wizard.next');
  if (wizardStep === 0) {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">${I18N.t('wizard.step0Hint')}</p>
      <div class="form-group"><label>${I18N.t('wizard.tiktokUser')}</label>
      <input type="text" id="w-tiktok-user" value="${escapeHtml(wizardData.tiktok_user)}" placeholder="${I18N.t('wizard.tiktokUserPlaceholder')}">
      <div class="inline-error" id="err-tiktok-user">${I18N.t('wizard.tiktokUserError')}</div>
      <div class="hint">${I18N.t('wizard.tiktokUserHint')}</div></div>`;
  } else if (wizardStep === 1) {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">${I18N.t('wizard.step1Hint')}</p>
      <div class="form-group"><label>${I18N.t('wizard.rconPassword')} <span style="color:var(--color-danger);">*</span></label>
      <input type="password" id="w-rcon-password" value="${escapeHtml(wizardData.rcon_password)}" placeholder="${I18N.t('wizard.passwordPlaceholder')}" oninput="updatePasswordMeter()">
      <div class="inline-error" id="err-rcon-password">${I18N.t('wizard.passwordError')}</div>
      <div class="strength-meter"><div class="strength-segment"></div><div class="strength-segment"></div><div class="strength-segment"></div></div>
      <div class="strength-label" id="strength-label">${I18N.t('wizard.strengthEnter')}</div>
      <div class="hint">${I18N.t('wizard.strengthHint')}</div></div>`;
    setTimeout(updatePasswordMeter, 0);
  } else {
    content.innerHTML = `<p class="muted" style="margin-bottom:1.5rem;">${I18N.t('wizard.step2Hint')}</p>
      <div style="background:var(--input-bg);padding:1rem;border-radius:8px;margin-bottom:1rem;">
      <div class="field-row"><span>${I18N.t('wizard.tiktokUserLabel')}</span><span>${escapeHtml(wizardData.tiktok_user || '—')}</span></div>
      <div class="field-row"><span>${I18N.t('wizard.rconPasswordLabel')}</span><span>${wizardData.rcon_password ? '********' : I18N.t('common.notSet')}</span></div></div>
      <p class="muted" style="font-size:0.85rem;margin:0;">${I18N.t('wizard.pluginsDisabledHint')}</p>`;
  }
}
/** Validate the RCON password policy (length, case, digit and special character). */
function validatePassword(pass) {
  const issues = [];
  if (pass.length < 8) issues.push(I18N.t('pass.minLength'));
  if (!/[A-Z]/.test(pass)) issues.push(I18N.t('pass.upper'));
  if (!/[a-z]/.test(pass)) issues.push(I18N.t('pass.lower'));
  if (!/[0-9]/.test(pass)) issues.push(I18N.t('pass.number'));
  if (!/[^A-Za-z0-9]/.test(pass)) issues.push(I18N.t('pass.special'));
  return issues;
}
/** Classify password strength as weak, medium or strong. */
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
/** Update the password strength meter for the current input. */
function updatePasswordMeter() {
  const pass = document.getElementById('w-rcon-password').value;
  const strength = getPasswordStrength(pass);
  const segments = document.querySelectorAll('.strength-segment');
  const label = document.getElementById('strength-label');
  segments.forEach(s => s.className = 'strength-segment');
  if (pass.length > 0) {
    if (strength === 'weak') { segments[0].classList.add('weak'); label.textContent = I18N.t('wizard.weak'); label.style.color = 'var(--danger)'; }
    else if (strength === 'medium') { segments[0].classList.add('medium'); segments[1].classList.add('medium'); label.textContent = I18N.t('wizard.medium'); label.style.color = 'var(--warning)'; }
    else { segments.forEach(s => s.classList.add('strong')); label.textContent = I18N.t('wizard.strong'); label.style.color = 'var(--success)'; }
  } else { label.textContent = I18N.t('wizard.strengthEnter'); label.style.color = 'var(--text-secondary)'; }
}
/** Advance the wizard, validating the current step first. */
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
    const pass = passInput.value.trim();
    if (!pass) {
      passInput.classList.add('invalid');
      document.getElementById('err-rcon-password').classList.add('visible');
      return;
    }
    wizardData.rcon_password = pass;
  }
  if (wizardStep === 2) { await wizardSave(); return; }
  wizardStep++;
  renderWizardStep();
}

/** Save the wizard's TikTok and RCON settings and offer a server restart. */
async function wizardSave() {
  const nextBtn = document.getElementById('wizard-next');
  nextBtn.disabled = true;
  nextBtn.textContent = I18N.t('wizard.saving');
  try {
    const cfgData = await fetchJSON('/config');
    const cfg = cfgData.config || {};
    if (!cfg.tiktok) cfg.tiktok = {};
    cfg.tiktok.user = wizardData.tiktok_user;
    if (!cfg.rcon) cfg.rcon = {};
    if (wizardData.rcon_password && wizardData.rcon_password !== '__REDACTED__') {
      cfg.rcon.password = wizardData.rcon_password;
    }
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
    showToast(I18N.t('wizard.setupComplete'), 'success');
  } catch (e) {
    log('Failed to save setup: ' + e.message, 'err');
    showToast(I18N.t('wizard.saveFailed', { msg: e.message }), 'error');
  } finally { nextBtn.disabled = false; nextBtn.textContent = I18N.t('wizard.save'); }
}
/** Show the full-screen restart overlay. */
function _showRestartOverlay() {
  _stopDashboardPolling();
  if (_sseSource) { _sseSource.close(); _sseSource = null; }
  const card = document.querySelector('#restart-dialog .wizard-card');
  if (card) {
    card.innerHTML = '<h2 style="border:none;padding:0;">' + I18N.t('wizard.restarting') + '</h2><p class="muted">' + I18N.t('wizard.restartWait') + '</p>';
  }
  document.getElementById('restart-dialog').classList.remove('hidden');
}

/** Restart the managed server and wait for it to come back. */
async function triggerRestart() {
  _restartPending = true;
  updateRestartBanner();
  try {
    const res = await fetch(API + '/restart', { method: 'POST', headers: _withApiKey({}) });
    if (res.ok) {
      _showRestartOverlay();
      // The supervisor keeps the API server alive and publishes
      // server.restarting / server.started events via SSE.  If the
      // browser misses the events, fall back to a timeout.
      _waitForRestartCompletion();
    } else {
      _restartPending = false;
      updateRestartBanner();
      showToast(I18N.t('wizard.restartSignalFailed'), 'error');
      document.getElementById('restart-dialog').classList.add('hidden');
    }
  } catch (e) {
    _restartPending = false;
    updateRestartBanner();
    showToast(I18N.t('wizard.restartSignalFailed'), 'error');
    document.getElementById('restart-dialog').classList.add('hidden');
  }
}

/** Wait for a restart to complete, resolving early on a matching SSE event and otherwise timing out. */
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
/** Dismiss the restart banner. */
function dismissRestartBanner() {
  _restartPending = false;
  updateRestartBanner();
}
/** Record whether a restart is pending and persist the flag for reloads. */
function setRestartPending(pending) {
  _restartPending = pending;
  updateRestartBanner();
}
document.getElementById('wizard-back').addEventListener('click', () => { if (wizardStep > 0) { wizardStep--; renderWizardStep(); } });
document.getElementById('wizard-next').addEventListener('click', wizardNext);
