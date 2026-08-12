import { describe, it, expect, beforeEach } from 'vitest';

const ENTRIES = [
  { date: '2026-08-01', estimated_revenue_usd: 10 },
  { date: '2026-08-02', estimated_revenue_usd: 20 },
  { date: '2026-08-03', estimated_revenue_usd: 30 },
  { date: '2026-08-04', estimated_revenue_usd: 5 },
];

describe('filterRevenueEntries', () => {
  it('filters by inclusive date range', () => {
    const out = window.filterRevenueEntries(ENTRIES, '2026-08-02', '2026-08-03');
    expect(out.map(e => e.date)).toEqual(['2026-08-02', '2026-08-03']);
  });

  it('applies only a lower bound', () => {
    const out = window.filterRevenueEntries(ENTRIES, '2026-08-03', '');
    expect(out.map(e => e.date)).toEqual(['2026-08-03', '2026-08-04']);
  });

  it('applies only an upper bound', () => {
    const out = window.filterRevenueEntries(ENTRIES, '', '2026-08-02');
    expect(out.map(e => e.date)).toEqual(['2026-08-01', '2026-08-02']);
  });

  it('returns all entries sorted when no bounds given', () => {
    const out = window.filterRevenueEntries(ENTRIES, '', '');
    expect(out.map(e => e.date)).toEqual([
      '2026-08-01', '2026-08-02', '2026-08-03', '2026-08-04',
    ]);
  });

  it('handles unsorted input and undefined entries', () => {
    const shuffled = [ENTRIES[2], ENTRIES[0], ENTRIES[1]];
    const out = window.filterRevenueEntries(shuffled, '', '');
    expect(out.map(e => e.date)).toEqual(['2026-08-01', '2026-08-02', '2026-08-03']);
    expect(window.filterRevenueEntries(undefined, '', '')).toEqual([]);
  });
});

describe('computeRevenueStats', () => {
  it('computes totals, averages, best and worst days', () => {
    const stats = window.computeRevenueStats(ENTRIES);
    expect(stats.count).toBe(4);
    expect(stats.totalUsd).toBe(65);
    expect(stats.averageUsd).toBe(16.25);
    expect(stats.best).toEqual({ date: '2026-08-03', value: 30 });
    expect(stats.worst).toEqual({ date: '2026-08-04', value: 5 });
    expect(stats.lastChangeUsd).toBe(-25);
  });

  it('computes last7 vs prev7 windows', () => {
    const many = Array.from({ length: 20 }, (_, i) => ({
      date: `2026-07-${String(i + 1).padStart(2, '0')}`,
      estimated_revenue_usd: 10,
    }));
    const stats = window.computeRevenueStats(many);
    expect(stats.last7Usd).toBe(70);
    expect(stats.prev7Usd).toBe(70);
    expect(stats.delta7Usd).toBe(0);
  });

  it('returns a safe empty result', () => {
    const stats = window.computeRevenueStats([]);
    expect(stats.count).toBe(0);
    expect(stats.totalUsd).toBe(0);
    expect(stats.best).toBeNull();
    expect(stats.worst).toBeNull();
    expect(stats.lastChangeUsd).toBeNull();
  });

  it('returns null lastChange for a single entry', () => {
    const stats = window.computeRevenueStats([ENTRIES[0]]);
    expect(stats.lastChangeUsd).toBeNull();
    expect(stats.totalUsd).toBe(10);
  });
});

describe('formatCurrency', () => {
  it('formats USD with thousands separators', () => {
    expect(window.formatCurrency(1234.5)).toBe('$1,234.50');
  });

  it('formats zero and negatives', () => {
    expect(window.formatCurrency(0)).toBe('$0.00');
    expect(window.formatCurrency(-5.1)).toBe('-$5.10');
  });

  it('handles non-numeric input', () => {
    expect(window.formatCurrency(undefined)).toBe('$0.00');
  });
});

describe('formatCurrencyDelta', () => {
  it('prefixes positive and negative deltas', () => {
    expect(window.formatCurrencyDelta(5)).toBe('+$5.00');
    expect(window.formatCurrencyDelta(-2)).toBe('-$2.00');
  });

  it('treats null/NaN as no change', () => {
    expect(window.formatCurrencyDelta(null)).toBe('—');
    expect(window.formatCurrencyDelta(NaN)).toBe('—');
  });
});

describe('revenue rendering', () => {
  beforeEach(() => {
    window._revenueData = { entries: ENTRIES, file: {} };
  });

  it('renders summary cards with computed values', () => {
    window.renderRevenueSummary(ENTRIES);
    const el = document.getElementById('revenue-summary');
    const text = el.textContent;
    expect(text).toContain('$65.00');
    expect(text).toContain('16.25');
    expect(text).toContain('2026-08-03');
    expect(text).toContain('Last 7 vs prev 7');
  });

  it('renders a bar per entry in the chart', () => {
    window.renderRevenueChart(ENTRIES);
    const el = document.getElementById('revenue-chart');
    expect(el.querySelectorAll('.revenue-bar').length).toBe(4);
  });

  it('shows an empty state in the chart', () => {
    window.renderRevenueChart([]);
    const el = document.getElementById('revenue-chart');
    expect(el.textContent).toContain('No revenue data');
  });

  it('renders a history row with day-over-day change', () => {
    window.renderRevenueTable(ENTRIES);
    const el = document.getElementById('revenue-table-wrap');
    const rows = el.querySelectorAll('tbody tr');
    expect(rows.length).toBe(4);
    expect(rows[2].textContent).toContain('2026-08-03');
    expect(rows[2].textContent).toContain('+$10.00');
    expect(rows[3].textContent).toContain('-$25.00');
  });

  it('renders the filtered view end-to-end', () => {
    document.getElementById('revenue-from').value = '2026-08-03';
    document.getElementById('revenue-to').value = '';
    window.renderRevenueView();
    const wrap = document.getElementById('revenue-table-wrap');
    expect(wrap.querySelectorAll('tbody tr').length).toBe(2);
  });
});
