/**
 * @file Viewer-session list, analytics details, all-time leaderboards and report download.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Sessions ─── */
let _sessionsData = {
  total: 0,
  sessions: [],
  total_gifts: 0,
  total_gift_events: 0,
  total_gift_units: 0,
  total_gift_diamonds: 0,
  total_gift_value_usd: 0,
  total_unique_gifters: 0,
  total_unique_viewers: 0,
  total_likes: 0,
  total_likes_raw: 0,
  total_likes_counted: 0,
  total_follows: 0,
  total_comments: 0,
  total_shares: 0,
  total_joins: 0,
};
let _sessionsLeaderboard = {};
let _sessionsDetail = null;

/** Return a whole number as a display string, tolerating missing values. */
function _sessionNumber(value) {
  return String(Math.trunc(Number(value) || 0));
}

/** Return the most useful display name for a viewer, gift or top entry. */
function _sessionEntryName(entry) {
  if (!entry) return '—';
  return String(
    entry.display_name ||
    entry.name ||
    entry.username ||
    entry.entry_key ||
    entry.user_key ||
    entry.gift_name ||
    '—'
  );
}

/** Fetch recorded stream sessions, render the view and refresh leaderboards. */
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
    return;
  }
  await loadAnalyticsLeaderboard();
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
    { label: I18N.t('sessions.total'), value: _sessionNumber(d.total) },
    { label: I18N.t('sessions.giftEvents'), value: _sessionNumber(d.total_gift_events) },
    { label: I18N.t('sessions.giftUnits'), value: _sessionNumber(d.total_gift_units != null ? d.total_gift_units : d.total_gifts) },
    { label: I18N.t('sessions.totalGiftValue'), value: formatCurrency(d.total_gift_value_usd) },
    { label: I18N.t('sessions.giftDiamonds'), value: _sessionNumber(d.total_gift_diamonds) },
    { label: I18N.t('sessions.uniqueGifters'), value: _sessionNumber(d.total_unique_gifters) },
    { label: I18N.t('sessions.uniqueViewers'), value: _sessionNumber(d.total_unique_viewers) },
    { label: I18N.t('sessions.totalLikes'), value: _sessionNumber(d.total_likes_counted != null ? d.total_likes_counted : d.total_likes) },
    { label: I18N.t('sessions.likesRaw'), value: _sessionNumber(d.total_likes_raw) },
    { label: I18N.t('sessions.totalFollows'), value: _sessionNumber(d.total_follows) },
    { label: I18N.t('sessions.totalComments'), value: _sessionNumber(d.total_comments) },
    { label: I18N.t('sessions.totalShares'), value: _sessionNumber(d.total_shares) },
    { label: I18N.t('sessions.totalJoins'), value: _sessionNumber(d.total_joins) },
  ];
  el.innerHTML = cards.map(c =>
    '<div class="status-card">' +
      '<span class="status-card__label">' + escapeHtml(c.label) + '</span>' +
      '<span class="status-card__value">' + c.value + '</span>' +
    '</div>'
  ).join('');
}

/** Render the session table, newest first, with a button per detail view. */
function renderSessionsTable() {
  const wrap = document.getElementById('sessions-table-wrap');
  if (!wrap) return;
  const sessions = _sessionsData.sessions || [];
  if (!sessions.length) {
    wrap.innerHTML = '<p class="text-muted">' + I18N.t('sessions.noData') + '</p>';
    return;
  }
  // The API already returns newest-first; sort defensively so the view stays
  // correct for legacy JSONL fallbacks that return entries in file order.
  const ordered = [...sessions].sort((a, b) => String(b.start || '').localeCompare(String(a.start || '')));
  const rows = ordered.map(s => {
    const sessionId = s.session_id || '';
    const detailsCell = sessionId
      ? '<button class="btn btn--secondary btn--sm" data-session-id="' + escapeHtml(sessionId) +
        '" onclick="showSessionDetail(this.dataset.sessionId)" data-i18n="sessions.details">' +
        escapeHtml(I18N.t('sessions.details')) + '</button>'
      : '<span class="text-muted">-</span>';
    return '<tr>' +
      '<td data-label="' + I18N.t('sessions.colStart') + '">' + escapeHtml(s.start || '') + '</td>' +
      '<td data-label="' + I18N.t('sessions.colDuration') + '">' + formatDuration(s.duration_seconds) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colGiftEvents') + '">' + _sessionNumber(s.gift_events != null ? s.gift_events : s.gifts) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colGiftUnits') + '">' + _sessionNumber(s.gift_units != null ? s.gift_units : s.gifts) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colValue') + '">' + formatCurrency(s.gift_value_usd) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colDiamonds') + '">' + _sessionNumber(s.gift_diamonds) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colUniqueViewers') + '">' + _sessionNumber(s.unique_viewers) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colLikes') + '">' + _sessionNumber(s.likes_counted != null ? s.likes_counted : s.likes) +
        ' <span class="text-muted">/ ' + _sessionNumber(s.likes_raw != null ? s.likes_raw : s.likes) + '</span></td>' +
      '<td data-label="' + I18N.t('sessions.colFollows') + '">' + _sessionNumber(s.follows) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colComments') + '">' + _sessionNumber(s.comments) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colShares') + '">' + _sessionNumber(s.shares) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colJoins') + '">' + _sessionNumber(s.joins) + '</td>' +
      '<td data-label="' + I18N.t('sessions.colDetails') + '">' + detailsCell + '</td>' +
    '</tr>';
  }).join('');
  wrap.innerHTML = '<table class="plugin-table"><thead><tr>' +
    '<th>' + I18N.t('sessions.colStart') + '</th>' +
    '<th>' + I18N.t('sessions.colDuration') + '</th>' +
    '<th>' + I18N.t('sessions.colGiftEvents') + '</th>' +
    '<th>' + I18N.t('sessions.colGiftUnits') + '</th>' +
    '<th>' + I18N.t('sessions.colValue') + '</th>' +
    '<th>' + I18N.t('sessions.colDiamonds') + '</th>' +
    '<th>' + I18N.t('sessions.colUniqueViewers') + '</th>' +
    '<th>' + I18N.t('sessions.colLikes') + '</th>' +
    '<th>' + I18N.t('sessions.colFollows') + '</th>' +
    '<th>' + I18N.t('sessions.colComments') + '</th>' +
    '<th>' + I18N.t('sessions.colShares') + '</th>' +
    '<th>' + I18N.t('sessions.colJoins') + '</th>' +
    '<th>' + I18N.t('sessions.colDetails') + '</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/** Render the loaded sessions. */
function renderSessionsView() {
  renderSessionsSummary();
  renderSessionsTable();
}

/** Return the leaderboard groups rendered in the sessions view. */
function _sessionLeaderboardGroups() {
  return [
    { key: 'top_gifters_value', title: 'sessions.topGiftersValue', format: entry => formatCurrency(entry.value) },
    { key: 'top_gifters_units', title: 'sessions.topGiftersUnits', format: entry => _sessionNumber(entry.units) },
    { key: 'top_likers', title: 'sessions.topLikers', format: entry => _sessionNumber(entry.value) },
    { key: 'top_commenters', title: 'sessions.topCommenters', format: entry => _sessionNumber(entry.value) },
    { key: 'top_gifts_units', title: 'sessions.topGiftsUnits', format: entry => _sessionNumber(entry.units) },
    { key: 'top_gifts_value', title: 'sessions.topGiftsValue', format: entry => formatCurrency(entry.value) },
  ];
}

/** Render one ranked top-list table. */
function _renderTopEntries(entries, valueLabel, formatter) {
  if (!Array.isArray(entries) || !entries.length) {
    return '<p class="text-muted">' + escapeHtml(I18N.t('sessions.noEntries')) + '</p>';
  }
  const rows = entries.map((entry, index) =>
    '<tr>' +
      '<td>' + (index + 1) + '</td>' +
      '<td>' + escapeHtml(_sessionEntryName(entry)) + '</td>' +
      '<td>' + formatter(entry) + '</td>' +
    '</tr>'
  ).join('');
  return '<table class="plugin-table"><thead><tr>' +
    '<th>#</th>' +
    '<th>' + escapeHtml(I18N.t('sessions.colName')) + '</th>' +
    '<th>' + escapeHtml(valueLabel) + '</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/** Render the all-time leaderboards from the loaded analytics response. */
function renderSessionsLeaderboard() {
  const el = document.getElementById('sessions-leaderboard');
  if (!el) return;
  const groups = _sessionLeaderboardGroups();
  const hasAny = groups.some(group =>
    Array.isArray(_sessionsLeaderboard[group.key]) && _sessionsLeaderboard[group.key].length
  );
  if (!hasAny) {
    el.innerHTML = '<p class="text-muted">' + escapeHtml(I18N.t('sessions.noEntries')) + '</p>';
    return;
  }
  el.innerHTML = '<div class="sessions-top-grid">' + groups.map(group =>
    '<div class="sessions-top-block">' +
      '<h4>' + escapeHtml(I18N.t(group.title)) + '</h4>' +
      _renderTopEntries(_sessionsLeaderboard[group.key], I18N.t('sessions.colValue'), group.format) +
    '</div>'
  ).join('') + '</div>';
}

/** Fetch and render the all-time leaderboards. */
async function loadAnalyticsLeaderboard() {
  const el = document.getElementById('sessions-leaderboard');
  if (!el) return;
  try {
    const data = await fetchJSON('/analytics/leaderboard');
    _sessionsLeaderboard = data && typeof data === 'object' ? data : {};
    renderSessionsLeaderboard();
  } catch (e) {
    log('Analytics leaderboard load failed: ' + e.message, 'err');
    el.innerHTML = '<p class="text-muted">' + escapeHtml(I18N.t('sessions.leaderboardFailed')) + '</p>';
  }
}

/** Open and load the detail panel for one session. */
async function showSessionDetail(sessionId) {
  if (!sessionId) return;
  const section = document.getElementById('sessions-detail-section');
  const el = document.getElementById('sessions-detail');
  if (!section || !el) return;
  section.hidden = false;
  el.innerHTML = '<p class="text-muted">' + escapeHtml(I18N.t('sessions.loadingDetail')) + '</p>';
  try {
    const data = await fetchJSON('/sessions/' + encodeURIComponent(sessionId));
    if (!data || typeof data !== 'object') throw new Error('invalid session detail');
    _sessionsDetail = data;
    renderSessionDetail(data);
  } catch (e) {
    log('Session detail load failed: ' + e.message, 'err');
    el.innerHTML = '<p class="text-muted">' + escapeHtml(I18N.t('sessions.detailFailed')) + '</p>';
  }
}

/** Hide the session detail panel. */
function closeSessionDetail() {
  const section = document.getElementById('sessions-detail-section');
  if (section) section.hidden = true;
  _sessionsDetail = null;
}

/** Render the viewer detail table of one session. */
function _renderSessionViewers(viewers) {
  if (!Array.isArray(viewers) || !viewers.length) {
    return '<p class="text-muted">' + escapeHtml(I18N.t('sessions.noDetails')) + '</p>';
  }
  const rows = viewers.map(viewer =>
    '<tr>' +
      '<td>' + escapeHtml(_sessionEntryName(viewer)) + '</td>' +
      '<td>' + _sessionNumber(viewer.gift_units) + '</td>' +
      '<td>' + formatCurrency(viewer.gift_value_usd) + '</td>' +
      '<td>' + _sessionNumber(viewer.likes_counted) + ' <span class="text-muted">/ ' + _sessionNumber(viewer.likes_raw) + '</span></td>' +
      '<td>' + _sessionNumber(viewer.comments) + '</td>' +
      '<td>' + _sessionNumber(viewer.follows) + '</td>' +
      '<td>' + _sessionNumber(viewer.shares) + '</td>' +
      '<td>' + _sessionNumber(viewer.joins) + '</td>' +
    '</tr>'
  ).join('');
  return '<table class="plugin-table"><thead><tr>' +
    '<th>' + I18N.t('sessions.colViewer') + '</th>' +
    '<th>' + I18N.t('sessions.colGiftUnits') + '</th>' +
    '<th>' + I18N.t('sessions.colValue') + '</th>' +
    '<th>' + I18N.t('sessions.colLikes') + '</th>' +
    '<th>' + I18N.t('sessions.colComments') + '</th>' +
    '<th>' + I18N.t('sessions.colFollows') + '</th>' +
    '<th>' + I18N.t('sessions.colShares') + '</th>' +
    '<th>' + I18N.t('sessions.colJoins') + '</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/** Render the per-gift detail table of one session. */
function _renderSessionGifts(gifts) {
  if (!Array.isArray(gifts) || !gifts.length) {
    return '<p class="text-muted">' + escapeHtml(I18N.t('sessions.noDetails')) + '</p>';
  }
  const rows = gifts.map(gift =>
    '<tr>' +
      '<td>' + escapeHtml(gift.gift_name || gift.gift_id || '—') + '</td>' +
      '<td>' + _sessionNumber(gift.events) + '</td>' +
      '<td>' + _sessionNumber(gift.units) + '</td>' +
      '<td>' + _sessionNumber(gift.diamonds) + '</td>' +
      '<td>' + formatCurrency(gift.value_usd) + '</td>' +
      '<td>' + _sessionNumber(gift.unique_gifters) + '</td>' +
      '<td>' + _sessionNumber(gift.largest_combo_units) + '</td>' +
    '</tr>'
  ).join('');
  return '<table class="plugin-table"><thead><tr>' +
    '<th>' + I18N.t('sessions.colGift') + '</th>' +
    '<th>' + I18N.t('sessions.colEvents') + '</th>' +
    '<th>' + I18N.t('sessions.colGiftUnits') + '</th>' +
    '<th>' + I18N.t('sessions.colDiamonds') + '</th>' +
    '<th>' + I18N.t('sessions.colValue') + '</th>' +
    '<th>' + I18N.t('sessions.colUniqueGifters') + '</th>' +
    '<th>' + I18N.t('sessions.colLargestCombo') + '</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/** Return the top-list groups shown in the session detail panel. */
function _sessionDetailTopGroups() {
  return [
    { key: 'top_gifters_value', title: 'sessions.topGiftersValue', format: entry => formatCurrency(entry.value) },
    { key: 'top_gifters_units', title: 'sessions.topGiftersUnits', format: entry => _sessionNumber(entry.units) },
    { key: 'top_likers', title: 'sessions.topLikers', format: entry => _sessionNumber(entry.value) },
    { key: 'top_commenters', title: 'sessions.topCommenters', format: entry => _sessionNumber(entry.value) },
    { key: 'top_gifts_units', title: 'sessions.topGiftsUnits', format: entry => _sessionNumber(entry.units) },
    { key: 'top_gifts_value', title: 'sessions.topGiftsValue', format: entry => formatCurrency(entry.value) },
    { key: 'largest_gift', title: 'sessions.largestGift', format: entry => formatCurrency(entry.value) },
    { key: 'largest_combo', title: 'sessions.largestCombo', format: entry => _sessionNumber(entry.units) },
  ];
}

/** Render one session's totals, top lists, viewers and gift details. */
function renderSessionDetail(detail) {
  const el = document.getElementById('sessions-detail');
  if (!el) return;
  const cards = [
    { label: I18N.t('sessions.giftEvents'), value: _sessionNumber(detail.gift_events) },
    { label: I18N.t('sessions.giftUnits'), value: _sessionNumber(detail.gift_units != null ? detail.gift_units : detail.gifts) },
    { label: I18N.t('sessions.totalGiftValue'), value: formatCurrency(detail.gift_value_usd) },
    { label: I18N.t('sessions.giftDiamonds'), value: _sessionNumber(detail.gift_diamonds) },
    { label: I18N.t('sessions.uniqueGifters'), value: _sessionNumber(detail.unique_gifters) },
    { label: I18N.t('sessions.uniqueViewers'), value: _sessionNumber(detail.unique_viewers) },
    { label: I18N.t('sessions.totalLikes'), value: _sessionNumber(detail.likes_counted != null ? detail.likes_counted : detail.likes) },
    { label: I18N.t('sessions.likesRaw'), value: _sessionNumber(detail.likes_raw) },
    { label: I18N.t('sessions.totalFollows'), value: _sessionNumber(detail.follows) },
    { label: I18N.t('sessions.totalComments'), value: _sessionNumber(detail.comments) },
    { label: I18N.t('sessions.totalShares'), value: _sessionNumber(detail.shares) },
    { label: I18N.t('sessions.totalJoins'), value: _sessionNumber(detail.joins) },
    { label: I18N.t('sessions.reconnects'), value: _sessionNumber(detail.reconnect_count) },
  ];
  const meta = [];
  if (detail.tiktok_user) meta.push(I18N.t('sessions.sessionUser') + ': ' + detail.tiktok_user);
  if (detail.end_reason) meta.push(I18N.t('sessions.endReason') + ': ' + detail.end_reason);
  if (detail.largest_gift_name) meta.push(I18N.t('sessions.largestGift') + ': ' + detail.largest_gift_name);
  if (detail.largest_combo_name) meta.push(I18N.t('sessions.largestCombo') + ': ' + detail.largest_combo_name);

  const tops = detail.tops && typeof detail.tops === 'object' ? detail.tops : {};
  const topGroups = _sessionDetailTopGroups().filter(group =>
    Array.isArray(tops[group.key]) && tops[group.key].length
  );
  const topHtml = topGroups.length
    ? '<div class="sessions-top-grid">' + topGroups.map(group =>
        '<div class="sessions-top-block">' +
          '<h4>' + escapeHtml(I18N.t(group.title)) + '</h4>' +
          _renderTopEntries(tops[group.key], I18N.t('sessions.colValue'), group.format) +
        '</div>'
      ).join('') + '</div>'
    : '<p class="text-muted">' + escapeHtml(I18N.t('sessions.noEntries')) + '</p>';

  el.innerHTML =
    '<p class="sessions-detail-meta">' +
      escapeHtml((detail.start || '') + ' → ' + (detail.end || '') + ' · ' + formatDuration(detail.duration_seconds)) +
    '</p>' +
    (meta.length ? '<p class="text-muted sessions-detail-meta">' + escapeHtml(meta.join(' · ')) + '</p>' : '') +
    '<div class="status-grid">' + cards.map(card =>
      '<div class="status-card">' +
        '<span class="status-card__label">' + escapeHtml(card.label) + '</span>' +
        '<span class="status-card__value">' + card.value + '</span>' +
      '</div>'
    ).join('') + '</div>' +
    '<h4>' + escapeHtml(I18N.t('sessions.topLists')) + '</h4>' + topHtml +
    '<h4>' + escapeHtml(I18N.t('sessions.viewers')) + '</h4>' + _renderSessionViewers(detail.viewers) +
    '<h4>' + escapeHtml(I18N.t('sessions.gifts')) + '</h4>' + _renderSessionGifts(detail.gift_stats);
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
