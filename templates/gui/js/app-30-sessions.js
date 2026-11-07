/**
 * @file Viewer-session list, formatting and report download.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Sessions ─── */
let _sessionsData = { total: 0, sessions: [], total_gifts: 0, total_gift_value_usd: 0, total_likes: 0, total_follows: 0, total_comments: 0, total_shares: 0, total_joins: 0 };

/** Fetch recorded stream sessions and render the sessions view. */
async function loadSessions() {
  try {
    const data = await fetchJSON('/sessions');
    _sessionsData = data && Array.isArray(data.sessions) ? data : { total: 0, sessions: [] };
    renderSessionsView();
  } catch (e) {
    log('Sessions load failed: ' + e.message, 'err');
    const wrap = document.getElementById('sessions-table-wrap');
    const summary = document.getElementById('sessions-summary');
    if (wrap) wrap.innerHTML = '<p class="text-muted">' + I18N.t('sessions.failedLoad') + '</p>';
    if (summary) summary.innerHTML = '';
  }
}

/** Format a duration in seconds as hours, minutes and seconds. */
function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  return h > 0 ? h + 'h ' + mm + 'm ' + ss + 's' : (m > 0 ? m + 'm ' + ss + 's' : s + 's');
}

/** Render the session summary cards. */
function renderSessionsSummary() {
  const el = document.getElementById('sessions-summary');
  if (!el) return;
  const d = _sessionsData;
  const cards = [
    { label: I18N.t('sessions.total'), value: String(d.total) },
    { label: I18N.t('sessions.totalGifts'), value: String(d.total_gifts || 0) },
    { label: I18N.t('sessions.totalGiftValue'), value: formatCurrency(d.total_gift_value_usd) },
    { label: I18N.t('sessions.totalLikes'), value: String(d.total_likes || 0) },
    { label: I18N.t('sessions.totalFollows'), value: String(d.total_follows || 0) },
    { label: I18N.t('sessions.totalComments'), value: String(d.total_comments || 0) },
    { label: I18N.t('sessions.totalShares'), value: String(d.total_shares || 0) },
    { label: I18N.t('sessions.totalJoins'), value: String(d.total_joins || 0) },
  ];
  el.innerHTML = cards.map(c =>
    '<div class="status-card">' +
      '<span class="status-card__label">' + escapeHtml(c.label) + '</span>' +
      '<span class="status-card__value">' + c.value + '</span>' +
    '</div>'
  ).join('');
}

/** Render the session table, newest first. */
function renderSessionsTable() {
  const wrap = document.getElementById('sessions-table-wrap');
  if (!wrap) return;
  const sessions = _sessionsData.sessions || [];
  if (!sessions.length) {
    wrap.innerHTML = '<p class="text-muted">' + I18N.t('sessions.noData') + '</p>';
    return;
  }
  const reversed = [...sessions].reverse();
  const rows = reversed.map(s =>
    '<tr>' +
      '<td data-label="' + I18N.t('sessions.colStart') + '">' + escapeHtml(s.start || '') + '</td>' +
      '<td data-label="' + I18N.t('sessions.colDuration') + '">' + formatDuration(s.duration_seconds) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colGifts') + '">' + String(s.gifts || 0) + ' <span class="text-muted">(' + formatCurrency(s.gift_value_usd) + ')</span></td>' +
      '<td data-label="' + I18N.t('sessions.colLikes') + '">' + String(s.likes || 0) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colFollows') + '">' + String(s.follows || 0) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colComments') + '">' + String(s.comments || 0) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colShares') + '">' + String(s.shares || 0) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colJoins') + '">' + String(s.joins || 0) + '</td>' +
    '</tr>'
  ).join('');
  wrap.innerHTML = '<table class="plugin-table"><thead><tr>' +
    '<th>' + I18N.t('sessions.colStart') + '</th>' +
    '<th>' + I18N.t('sessions.colDuration') + '</th>' +
    '<th>' + I18N.t('sessions.colGifts') + '</th>' +
    '<th>' + I18N.t('sessions.colLikes') + '</th>' +
    '<th>' + I18N.t('sessions.colFollows') + '</th>' +
    '<th>' + I18N.t('sessions.colComments') + '</th>' +
    '<th>' + I18N.t('sessions.colShares') + '</th>' +
    '<th>' + I18N.t('sessions.colJoins') + '</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/** Render the loaded sessions. */
function renderSessionsView() {
  renderSessionsSummary();
  renderSessionsTable();
}

/** Download the Markdown session report through pywebview or a browser blob. */
async function downloadSessionsReport() {
  try {
    showToast(I18N.t('sessions.downloading'), 'info');
    const resp = await fetch(API + '/sessions/report', { headers: _withApiKey({}) });
    if (!resp.ok) await _throwResError(resp);
    const content = await resp.text();
    const filename = 'tiktok2mc-session-report-' + new Date().toISOString().slice(0, 10) + '.md';

    if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.download_file) {
      const path = await pywebview.api.download_file(content, filename);
      if (path && !path.startsWith('error:')) {
        showToast(I18N.t('sessions.reportSaved', { path }), 'success');
      } else {
        showToast(I18N.t('sessions.downloadFailed'), 'error');
      }
      return;
    }

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(I18N.t('sessions.reportSaved', { path: filename }), 'success');
  } catch (e) {
    showToast(e.message || I18N.t('sessions.downloadFailed'), 'error');
  }
}

