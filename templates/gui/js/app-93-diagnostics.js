/**
 * Diagnostics view: health summary, crash history and the error-code catalog.
 *
 * Loads data from the `/diagnostics` endpoints and renders three sections in
 * the `view-diagnostics` container. Everything is escaped before it enters
 * the DOM; the subsystem filter re-queries `/diagnostics/error-codes`.
 */

/* global fetchJSON, I18N, showToast, escapeHtml */

class DiagnosticsView {
  /** Create the diagnostics view and cache its DOM elements. */
  constructor() {
    this.healthEl = document.getElementById('diag-health');
    this.crashListEl = document.getElementById('diag-crash-list');
    this.crashEmptyEl = document.getElementById('diag-crash-empty');
    this.codesListEl = document.getElementById('diag-codes-list');
    this.subsystemEl = document.getElementById('diag-subsystem');
    this._subsystemsLoaded = false;
  }

  /** Fetch health, crash history and error codes, then render everything. */
  async load() {
    const health = this._loadHealth();
    const crashes = this._loadCrashes();
    const codes = this.loadCodes();
    await Promise.allSettled([health, crashes, codes]);
  }

  /**
   * Fetch and render the health summary.
   *
   * @returns {Promise<void>} resolves regardless of fetch success
   * @private
   */
  async _loadHealth() {
    if (!this.healthEl) return;
    try {
      const data = await fetchJSON('/diagnostics/health');
      this._renderHealth(data);
    } catch (e) {
      this.healthEl.innerHTML = '<p class="muted">' + I18N.t('diagnostics.loadFailed') + '</p>';
    }
  }

  /**
   * Render the health summary card: uptime, component counts and the
   * degraded/failed component lists.
   *
   * @param {Object} data - health summary from `/diagnostics/health`
   * @private
   */
  _renderHealth(data) {
    const uptime = Number(data.uptime_seconds || 0);
    const mins = Math.floor(uptime / 60);
    const secs = Math.floor(uptime % 60);
    const degraded = data.degraded_components || [];
    const failed = data.failed_components || [];
    const row = (label, value) =>
      '<div class="diag-stat"><span class="diag-stat-label">' + label + '</span>' +
      '<span class="diag-stat-value">' + value + '</span></div>';
    const list = (items, emptyKey, cls) => items.length
      ? '<ul class="diag-component-list ' + cls + '">' +
        items.map(c => '<li>' + escapeHtml(c) + '</li>').join('') + '</ul>'
      : '<p class="muted">' + I18N.t(emptyKey) + '</p>';

    this.healthEl.innerHTML =
      '<div class="diag-stats">' +
      row(I18N.t('diagnostics.health.uptime'), mins + ':' + String(secs).padStart(2, '0') + ' min') +
      row(I18N.t('diagnostics.health.components'), String(data.total_components || 0)) +
      row(I18N.t('diagnostics.health.running'), String(data.running || 0)) +
      row(I18N.t('diagnostics.health.degraded'), String(data.degraded || 0)) +
      row(I18N.t('diagnostics.health.failed'), String(data.failed || 0)) +
      '</div>' +
      '<h4 class="diag-subhead">' + I18N.t('diagnostics.health.degradedList') + '</h4>' +
      list(degraded, 'diagnostics.health.noneDegraded', 'diag-degraded') +
      '<h4 class="diag-subhead">' + I18N.t('diagnostics.health.failedList') + '</h4>' +
      list(failed, 'diagnostics.health.noneFailed', 'diag-failed');
  }

  /**
   * Fetch and render the crash history.
   *
   * @returns {Promise<void>} resolves regardless of fetch success
   * @private
   */
  async _loadCrashes() {
    if (!this.crashListEl) return;
    try {
      const data = await fetchJSON('/diagnostics/crash-history');
      const history = data.history || [];
      if (!history.length) {
        this.crashListEl.innerHTML = '';
        if (this.crashEmptyEl) this.crashEmptyEl.classList.remove('hidden');
        return;
      }
      if (this.crashEmptyEl) this.crashEmptyEl.classList.add('hidden');
      this.crashListEl.innerHTML = history.map(c => `
        <div class="crash-report-item">
          <div class="crash-report-meta">
            <span class="crash-report-time">${escapeHtml(c.timestamp || I18N.t('common.unknown'))}</span>
            <span class="crash-report-module">${escapeHtml(c.code || '—')}</span>
          </div>
          <div class="crash-report-type">${escapeHtml(c.exception || I18N.t('common.unknown'))}</div>
          ${c.context ? '<div class="crash-detail-context">' + escapeHtml(typeof c.context === 'string' ? c.context : JSON.stringify(c.context)) + '</div>' : ''}
        </div>
      `).join('');
    } catch (e) {
      this.crashListEl.innerHTML = '<p class="muted">' + I18N.t('diagnostics.loadFailed') + '</p>';
    }
  }

  /**
   * Fetch and render the error-code catalog for the selected subsystem.
   * Also populates the subsystem filter once from an unfiltered response.
   *
   * @returns {Promise<void>} resolves regardless of fetch success
   */
  async loadCodes() {
    if (!this.codesListEl) return;
    const subsystem = this.subsystemEl ? this.subsystemEl.value : '';
    const url = '/diagnostics/error-codes' + (subsystem ? '?subsystem=' + encodeURIComponent(subsystem) : '');
    try {
      const data = await fetchJSON(url);
      const codes = data.codes || [];
      if (!subsystem && !this._subsystemsLoaded) {
        this._populateSubsystems(codes);
      }
      if (!codes.length) {
        this.codesListEl.innerHTML = '<p class="muted">' + I18N.t('diagnostics.codes.empty') + '</p>';
        return;
      }
      this.codesListEl.innerHTML = '<div class="diag-table">' +
        '<div class="diag-table-head"><span>' + I18N.t('diagnostics.codes.colCode') + '</span>' +
        '<span>' + I18N.t('diagnostics.codes.colSeverity') + '</span>' +
        '<span>' + I18N.t('diagnostics.codes.colMessage') + '</span></div>' +
        codes.map(c => `
          <div class="diag-table-row">
            <span class="diag-code">${escapeHtml(c.code || '')}</span>
            <span class="diag-severity diag-severity-${escapeHtml((c.severity || '').toLowerCase())}">${escapeHtml(c.severity || '')}</span>
            <span>${escapeHtml(c.message || '')}</span>
          </div>
        `).join('') +
        '</div>';
    } catch (e) {
      this.codesListEl.innerHTML = '<p class="muted">' + I18N.t('diagnostics.loadFailed') + '</p>';
    }
  }

  /**
   * Fill the subsystem filter dropdown from the unfiltered code list.
   *
   * @param {Array<Object>} codes - error-code dicts with `code` fields
   * @private
   */
  _populateSubsystems(codes) {
    if (!this.subsystemEl) return;
    this._subsystemsLoaded = true;
    const seen = {};
    codes.forEach(c => {
      const code = c.code || '';
      const sub = code.split('-')[0];
      if (sub && !seen[sub]) seen[sub] = true;
    });
    const current = this.subsystemEl.value;
    Object.keys(seen).sort().forEach(sub => {
      const opt = document.createElement('option');
      opt.value = sub;
      opt.textContent = sub;
      this.subsystemEl.appendChild(opt);
    });
    this.subsystemEl.value = current;
  }

  /**
   * Report a failed diagnostics fetch as a toast.
   *
   * @param {string} endpoint - endpoint name for the message
   */
  reportError(endpoint) {
    showToast(I18N.t('diagnostics.loadFailed') + ' (' + endpoint + ')', 'error');
  }
}

const diagnosticsView = new DiagnosticsView();
