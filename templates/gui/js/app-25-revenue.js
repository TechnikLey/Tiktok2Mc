/**
 * @file Revenue dashboard: configuration, statistics, charts and table rendering.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Revenue View ─── */

let _revenueData = { entries: [], file: {} };

/* Real TikTok payout model (community-estimated 2026 rates).
   Net = diamond value × $0.004 (creator cash-out). Gross = what the
   viewer actually spent: 2 coins become 1 diamond, coins cost ≈ $0.013
   on average, so gross = net × (2 × 0.013) / 0.005 ≈ net × 5.2 and the
   creator keeps ≈ 19 % of the viewer's spend. */
let REVENUE_NET_PER_DIAMOND_USD = 0.004;
const REVENUE_COINS_PER_DIAMOND = 2;
const REVENUE_USD_PER_COIN = 0.013;

/** Load the TikTok revenue settings used by the revenue view. */
async function loadRevenueConfig() {
  try {
    const data = await fetchJSON('/config');
    const rate = Number(data && data.config && data.config.tiktok && data.config.tiktok.diamond_value_usd);
    if (Number.isFinite(rate) && rate > 0) REVENUE_NET_PER_DIAMOND_USD = rate;
  } catch (e) {
    // keep default
  }
}

/** Round a monetary value to two decimal places. */
function _revenueRound2(value) {
  return Math.round(value * 100) / 100;
}

/** Return the creator's net share of gift revenue as a percentage. */
function _revenueNetSharePct() {
  return (
    (REVENUE_NET_PER_DIAMOND_USD /
      (REVENUE_COINS_PER_DIAMOND * REVENUE_USD_PER_COIN)) *
    100
  );
}

/** Convert a net USD amount to its gross value using the configured net share. */
function revenueGrossFromNet(netUsd) {
  const v = Number(netUsd) || 0;
  return _revenueRound2(
    (v * (REVENUE_COINS_PER_DIAMOND * REVENUE_USD_PER_COIN)) /
      REVENUE_NET_PER_DIAMOND_USD
  );
}

/** Enrich a revenue entry with gross values and derived display fields. */
function revenueEnrichEntry(e) {
  const net = Number(e && e.estimated_revenue_usd) || 0;
  const gross = revenueGrossFromNet(net);
  return {
    date: e && e.date,
    netUsd: _revenueRound2(net),
    grossUsd: gross,
    tiktokUsd: _revenueRound2(gross - net),
  };
}

/** Fetch revenue entries and render the revenue view. */
async function loadRevenueView() {
  await loadRevenueConfig();
  refreshUsdToEurRate();
  try {
    const data = await fetchJSON('/revenue');
    _revenueData = data && Array.isArray(data.entries) ? data : { entries: [], file: {} };
    renderRevenueView();
  } catch (e) {
    log('Revenue load failed: ' + e.message, 'err');
    const chart = document.getElementById('revenue-chart');
    const wrap = document.getElementById('revenue-table-wrap');
    if (chart) chart.innerHTML = '<p class="text-muted">' + I18N.t('revenue.failedLoad') + '</p>';
    if (wrap) wrap.innerHTML = '';
  }
}

/** Format a date as an ISO calendar day (`YYYY-MM-DD`). */
function _revenueISODate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Set the revenue filter to the last `days` days and re-render. */
function revenueSetPeriod(days) {
  const from = document.getElementById('revenue-from');
  const to = document.getElementById('revenue-to');
  if (days > 0) {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - (days - 1));
    from.value = _revenueISODate(start);
    to.value = _revenueISODate(end);
  } else {
    from.value = '';
    to.value = '';
  }
  document.querySelectorAll('.revenue-period').forEach(el => {
    el.classList.toggle('active', Number(el.dataset.days) === days);
  });
  revenueApplyFilters();
}

/** Clear the revenue date filters and show all entries. */
function revenueClearFilters() {
  document.getElementById('revenue-from').value = '';
  document.getElementById('revenue-to').value = '';
  document.querySelectorAll('.revenue-period').forEach(el => el.classList.remove('active'));
  revenueApplyFilters();
}

/** Apply the revenue date filters to the loaded entries. */
function revenueApplyFilters() {
  renderRevenueView();
}

/** Return revenue entries whose dates fall inside the inclusive ISO date range. */
function filterRevenueEntries(entries, from, to) {
  return (entries || []).filter(e => {
    if (from && e.date < from) return false;
    if (to && e.date > to) return false;
    return true;
  }).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

/** Compute revenue totals, averages, best/worst days and week-over-week change. */
function computeRevenueStats(entries) {
  const values = (entries || []).map(e => e.estimated_revenue_usd);
  const count = values.length;
  if (!count) {
    return {
      count: 0,
      totalUsd: 0,
      totalGrossUsd: 0,
      tiktokUsd: 0,
      averageUsd: 0,
      averageGrossUsd: 0,
      netSharePct: _revenueNetSharePct(),
      best: null,
      worst: null,
      lastChangeUsd: null,
      last7Usd: 0,
      prev7Usd: 0,
      delta7Usd: 0,
    };
  }
  let best = null;
  let worst = null;
  for (const e of entries) {
    if (!best || e.estimated_revenue_usd > best.value) best = { date: e.date, value: e.estimated_revenue_usd };
    if (!worst || e.estimated_revenue_usd < worst.value) worst = { date: e.date, value: e.estimated_revenue_usd };
  }
  const total = values.reduce((s, v) => s + v, 0);
  const totalGross = values.reduce((s, v) => s + revenueGrossFromNet(v), 0);
  const last = values[count - 1];
  const prev = values[count - 2];
  const last7 = values.slice(-7).reduce((s, v) => s + v, 0);
  const prev7 = values.slice(-14, -7).reduce((s, v) => s + v, 0);
  return {
    count,
    totalUsd: _revenueRound2(total),
    totalGrossUsd: _revenueRound2(totalGross),
    tiktokUsd: _revenueRound2(totalGross - total),
    averageUsd: _revenueRound2(total / count),
    averageGrossUsd: _revenueRound2(totalGross / count),
    netSharePct: _revenueNetSharePct(),
    best,
    worst,
    lastChangeUsd: count >= 2 ? _revenueRound2(last - prev) : null,
    last7Usd: _revenueRound2(last7),
    prev7Usd: _revenueRound2(prev7),
    delta7Usd: _revenueRound2(last7 - prev7),
  };
}

/** Format a USD amount with two decimals. */
function formatUSD(value) {
  const v = Number(value) || 0;
  const neg = v < 0;
  const abs = Math.abs(v);
  const parts = abs.toFixed(2).split('.');
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return (neg ? '-' : '') + '$' + parts.join('.');
}

/** Format an amount in EUR using German separators. */
function formatEUR(value) {
  const v = Number(value) || 0;
  const neg = v < 0;
  const [int, dec] = Math.abs(v).toFixed(2).split('.');
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return (neg ? '-' : '') + grouped + ',' + dec + ' €';
}

let USD_TO_EUR_RATE = 0.86; // 1 USD ≈ 0.86 EUR (default; refreshed at runtime)

/** Refresh the cached USD-to-EUR exchange rate, keeping the fallback on failure. */
async function refreshUsdToEurRate() {
  try {
    const res = await fetch('https://api.exchangerate.host/latest?base=USD&symbols=EUR');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    const rate = Number(data && data.rates && data.rates.EUR);
    if (Number.isFinite(rate) && rate > 0) {
      USD_TO_EUR_RATE = rate;
      return rate;
    }
    throw new Error('invalid rate');
  } catch (e) {
    // keep default (today's value) on error
    return USD_TO_EUR_RATE;
  }
}

/** Format a value in the currency selected by the current GUI language. */
function formatCurrency(value) {
  const v = Number(value) || 0;
  if (I18N.lang() === 'de') {
    return formatEUR(v * USD_TO_EUR_RATE);
  }
  return formatUSD(v);
}

/** Format a signed currency delta with an explicit plus or minus. */
function formatCurrencyDelta(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const sign = value > 0 ? '+' : '';
  return sign + formatCurrency(value);
}

/** Build the HTML for one revenue summary card with an optional delta. */
function _revenueCard(label, value, delta) {
  return '<div class="status-card">' +
    '<span class="status-card__label">' + escapeHtml(label) + '</span>' +
    '<span class="status-card__value' + (delta == null ? '' : (delta >= 0 ? ' success' : ' danger')) + '">' + value + '</span>' +
  '</div>';
}

/** Render the revenue summary cards. */
function renderRevenueSummary(entries) {
  const el = document.getElementById('revenue-summary');
  if (!el) return;
  const stats = computeRevenueStats(entries);
  const netPct = Math.round(stats.netSharePct || 0);
  const feePct = 100 - netPct;
  const html = [
    '<div class="status-card revenue-hero">' +
      '<span class="status-card__label">' + escapeHtml(I18N.t('revenue.net')) + '</span>' +
      '<span class="status-card__value revenue-hero__value">' + formatCurrency(stats.totalUsd) + '</span>' +
      '<span class="revenue-hero__sub">' + escapeHtml(I18N.t('revenue.netSub', { pct: netPct })) + '</span>' +
    '</div>',
    '<div class="status-card">' +
      '<span class="status-card__label">' + escapeHtml(I18N.t('revenue.gross')) + '</span>' +
      '<span class="status-card__value">' + formatCurrency(stats.totalGrossUsd) + '</span>' +
      '<span class="revenue-card-sub">' + escapeHtml(I18N.t('revenue.grossSub')) + '</span>' +
    '</div>',
    '<div class="status-card revenue-fee-card">' +
      '<span class="status-card__label">' + escapeHtml(I18N.t('revenue.tiktokShare')) + '</span>' +
      '<span class="status-card__value">' + formatCurrency(stats.tiktokUsd) + '</span>' +
      '<span class="revenue-card-sub">≈ ' + feePct + '%</span>' +
    '</div>',
    _revenueCard(I18N.t('revenue.daysWithRevenue'), String(stats.count)),
    _revenueCard(I18N.t('revenue.averagePerDay'), formatCurrency(stats.averageUsd)),
    _revenueCard(I18N.t('revenue.bestDay'), stats.best
      ? formatCurrency(stats.best.value) + ' <span class="text-muted">' + escapeHtml(stats.best.date) + '</span>'
      : '—'),
    _revenueCard(I18N.t('revenue.worstDay'), stats.worst
      ? formatCurrency(stats.worst.value) + ' <span class="text-muted">' + escapeHtml(stats.worst.date) + '</span>'
      : '—'),
    _revenueCard(I18N.t('revenue.last7Days'), formatCurrency(stats.last7Usd)),
    _revenueCard(I18N.t('revenue.last7VsPrev7'), formatCurrencyDelta(stats.delta7Usd), stats.delta7Usd),
  ];
  el.innerHTML = html.join('');
}

/** Render the stacked gross/net revenue bar chart. */
function renderRevenueChart(entries) {
  const el = document.getElementById('revenue-chart');
  if (!el) return;
  if (!entries.length) {
    el.innerHTML = '';
    return;
  }
  const today = _revenueISODate(new Date());
  const enriched = entries.map(revenueEnrichEntry);
  const max = Math.max(...enriched.map(e => e.grossUsd), 0.01);
  const labelEvery = Math.ceil(enriched.length / 12);
  const grossLabel = I18N.t('revenue.gross');
  const netLabel = I18N.t('revenue.net');
  const feeLabel = I18N.t('revenue.tiktokShare');
  el.innerHTML = enriched.map((e, i) => {
    const netH = Math.max(0, Math.round((e.netUsd / max) * 100));
    const feeH = Math.max(0, Math.round((e.tiktokUsd / max) * 100));
    const label = i % labelEvery === 0 || i === enriched.length - 1 ? e.date.slice(5) : '';
    const latest = e.date === today ? ' revenue-bar--latest' : '';
    const tip =
      e.date + '\n' +
      grossLabel + ': ' + formatCurrency(e.grossUsd) + '\n' +
      netLabel + ': ' + formatCurrency(e.netUsd) + '\n' +
      feeLabel + ': ' + formatCurrency(e.tiktokUsd);
    return '<div class="revenue-bar' + latest + '" title="' + escapeHtml(tip) + '">' +
      '<div class="revenue-bar-stack">' +
        (e.netUsd > 0 ? '<span class="revenue-bar-segment revenue-bar-segment--net" style="height:' + netH + '%"></span>' : '') +
        (e.tiktokUsd > 0 ? '<span class="revenue-bar-segment revenue-bar-segment--fee" style="height:' + feeH + '%"></span>' : '') +
      '</div>' +
      '<span class="revenue-bar-label">' + escapeHtml(label) + '</span>' +
    '</div>';
  }).join('');
}

/** Render the revenue table with day-to-day deltas. */
function renderRevenueTable(entries) {
  const wrap = document.getElementById('revenue-table-wrap');
  if (!wrap) return;
  if (!entries.length) {
    wrap.innerHTML = '';
    return;
  }
  const grossLabel = I18N.t('revenue.gross');
  const netLabel = I18N.t('revenue.net');
  const feeLabel = I18N.t('revenue.tiktokShare');
  const changeLabel = I18N.t('revenue.change');
  let html = '<table class="plugin-table revenue-table"><thead><tr>' +
    '<th>Date</th><th>' + grossLabel + '</th><th>' + netLabel + '</th><th>' + feeLabel + '</th><th>' + changeLabel + '</th>' +
    '</tr></thead><tbody>';
  let prev = null;
  for (const e of entries.map(revenueEnrichEntry)) {
    const delta = prev != null ? e.netUsd - prev : null;
    const deltaHtml = delta == null
      ? '—'
      : '<span class="revenue-delta ' + (delta >= 0 ? 'revenue-delta--up' : 'revenue-delta--down') + '">' + formatCurrencyDelta(delta) + '</span>';
    html += '<tr>' +
      '<td data-label="Date">' + escapeHtml(e.date) + '</td>' +
      '<td data-label="' + escapeHtml(grossLabel) + '">' + formatCurrency(e.grossUsd) + '</td>' +
      '<td data-label="' + escapeHtml(netLabel) + '" class="revenue-table__net">' + formatCurrency(e.netUsd) + '</td>' +
      '<td data-label="' + escapeHtml(feeLabel) + '">' + formatCurrency(e.tiktokUsd) + '</td>' +
      '<td data-label="' + escapeHtml(changeLabel) + '">' + deltaHtml + '</td>' +
    '</tr>';
    prev = e.netUsd;
  }
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

/** Render the already-loaded revenue entries. */
function renderRevenueView() {
  const fromEl = document.getElementById('revenue-from');
  const toEl = document.getElementById('revenue-to');
  const from = fromEl ? fromEl.value : '';
  const to = toEl ? toEl.value : '';
  const entries = filterRevenueEntries(_revenueData.entries, from, to);
  renderRevenueSummary(entries);
  renderRevenueChart(entries);
  renderRevenueTable(entries);
}

