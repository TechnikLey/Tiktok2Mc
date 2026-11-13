import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('loadSessions', () => {
  afterEach(() => { vi.restoreAllMocks(); });

  it('fetches /sessions and calls renderSessionsView', async () => {
    const data = { total: 2, sessions: [{ gifts: 10 }, { gifts: 5 }], total_gifts: 15, total_gift_value_usd: 1.23, total_likes: 100, total_follows: 3, total_comments: 7, total_shares: 2, total_joins: 9 };
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => data }));
    const renderSpy = vi.spyOn(window, 'renderSessionsView').mockImplementation(() => {});

    await window.loadSessions();

    expect(renderSpy).toHaveBeenCalled();
    expect(window._sessionsData.total).toBe(2);
    renderSpy.mockRestore();
  });

  it('shows error message on fetch failure', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('net'); });
    document.getElementById('sessions-table-wrap').innerHTML = '';
    const logSpy = vi.spyOn(window, 'log').mockImplementation(() => {});

    await window.loadSessions();

    expect(document.getElementById('sessions-table-wrap').innerHTML).toContain('Failed to load');
    logSpy.mockRestore();
  });
});

describe('formatDuration', () => {
  it('returns seconds only for <1min', () => { expect(window.formatDuration(45)).toBe('45s'); });
  it('returns minutes and seconds', () => { expect(window.formatDuration(125)).toBe('2m 05s'); });
  it('returns hours minutes seconds', () => { expect(window.formatDuration(3661)).toBe('1h 01m 01s'); });
  it('returns zero', () => { expect(window.formatDuration(0)).toBe('0s'); });
  it('handles NaN', () => { expect(window.formatDuration(NaN)).toBe('0s'); });
});

describe('renderSessionsSummary', () => {
  it('renders analytics status cards', () => {
    window._sessionsData = {
      total: 3, sessions: [], total_gifts: 42, total_gift_events: 30, total_gift_units: 42,
      total_gift_diamonds: 84, total_gift_value_usd: 9.99, total_unique_gifters: 6,
      total_unique_viewers: 25, total_likes: 500, total_likes_raw: 700, total_likes_counted: 500,
      total_follows: 10, total_comments: 25, total_shares: 5, total_joins: 20,
    };
    window.renderSessionsSummary();
    const el = document.getElementById('sessions-summary');
    expect(el.querySelectorAll('.status-card').length).toBe(13);
    expect(el.textContent).toContain('42');
    expect(el.textContent).toContain('500');
    expect(el.textContent).toContain('700');
    expect(el.textContent).toContain('84');
  });
});

describe('renderSessionsTable', () => {
  it('shows no-data message when empty', () => {
    window._sessionsData = { total: 0, sessions: [] };
    window.renderSessionsTable();
    expect(document.getElementById('sessions-table-wrap').innerHTML).toContain('No sessions');
  });

  it('renders rows for each session', () => {
    window._sessionsData = {
      total: 2,
      sessions: [
        { start: '2026-08-15T20:00:00Z', duration_seconds: 3600, gifts: 5, gift_value_usd: 1.0, likes: 100, follows: 2, comments: 10, shares: 1, joins: 4 },
        { start: '2026-08-16T21:00:00Z', duration_seconds: 7200, gifts: 8, gift_value_usd: 2.5, likes: 200, follows: 5, comments: 20, shares: 3, joins: 7 },
      ],
      total_gifts: 13, total_gift_value_usd: 3.5, total_likes: 300, total_follows: 7, total_comments: 30, total_shares: 4, total_joins: 11,
    };
    window.renderSessionsTable();
    const rows = document.getElementById('sessions-table-wrap').querySelectorAll('tbody tr');
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('8');
    expect(rows[0].textContent).toContain('2h 00m 00s');
  });

  it('renders a details button for analytics sessions', () => {
    window._sessionsData = {
      total: 1,
      sessions: [{ session_id: 's1', start: '2026-08-16T21:00:00Z', duration_seconds: 60 }],
    };
    window.renderSessionsTable();
    const button = document.querySelector('#sessions-table-wrap tbody button');
    expect(button).not.toBeNull();
    expect(button.dataset.sessionId).toBe('s1');
  });
});

describe('renderSessionsLeaderboard', () => {
  it('renders all populated leaderboard groups', () => {
    window._sessionsLeaderboard = {
      top_gifters_value: [{ username: 'alice', display_name: 'Alice', value: 1.5, units: 2, diamonds: 4 }],
      top_gifters_units: [{ username: 'alice', display_name: 'Alice', value: 2, units: 2, diamonds: 4 }],
      top_likers: [{ username: 'bob', display_name: 'Bob', value: 10, units: 12, diamonds: 0 }],
      top_commenters: [{ username: 'carol', display_name: 'Carol', value: 3, units: 0, diamonds: 0 }],
      top_gifts_units: [{ entry_key: '1', name: 'Rose', value: 5, units: 5, diamonds: 5 }],
      top_gifts_value: [{ entry_key: '1', name: 'Rose', value: 0.02, units: 5, diamonds: 5 }],
    };
    window.renderSessionsLeaderboard();
    const el = document.getElementById('sessions-leaderboard');
    expect(el.querySelectorAll('table').length).toBe(6);
    expect(el.textContent).toContain('Alice');
    expect(el.textContent).toContain('Rose');
  });

  it('shows a message without leaderboard data', () => {
    window._sessionsLeaderboard = {};
    window.renderSessionsLeaderboard();
    expect(document.getElementById('sessions-leaderboard').textContent).toContain('No data');
  });
});

describe('showSessionDetail', () => {
  afterEach(() => { vi.restoreAllMocks(); });

  it('loads and renders viewers, gifts and top lists', async () => {
    const detail = {
      session_id: 's1', start: '2026-08-16T21:00:00Z', end: '2026-08-16T23:00:00Z',
      duration_seconds: 7200, gift_events: 2, gift_units: 5, gift_diamonds: 5,
      gift_value_usd: 0.02, unique_gifters: 1, unique_viewers: 1, likes_counted: 4,
      likes_raw: 10, follows: 1, comments: 1, shares: 1, joins: 1, reconnect_count: 0,
      viewers: [{ username: 'alice', display_name: 'Alice', gift_units: 5, gift_value_usd: 0.02, likes_counted: 4, likes_raw: 10, comments: 1, follows: 1, shares: 1, joins: 1 }],
      gift_stats: [{ gift_id: '1', gift_name: 'Rose', events: 1, units: 5, diamonds: 5, value_usd: 0.02, unique_gifters: 1, largest_combo_units: 5 }],
      tops: {
        top_gifters_value: [{ entry_key: 'user:alice', name: 'Alice', value: 0.02, units: 5, diamonds: 5 }],
        largest_gift: [{ entry_key: '', name: 'Rose', value: 0.02, units: 1, diamonds: 5 }],
      },
    };
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => detail }));
    const logSpy = vi.spyOn(window, 'log').mockImplementation(() => {});

    await window.showSessionDetail('s1');

    const el = document.getElementById('sessions-detail');
    expect(document.getElementById('sessions-detail-section').hidden).toBe(false);
    expect(el.textContent).toContain('Alice');
    expect(el.textContent).toContain('Rose');
    expect(el.querySelectorAll('.status-card').length).toBe(13);
    expect(window._sessionsDetail.session_id).toBe('s1');
    logSpy.mockRestore();
  });

  it('shows an error when the detail request fails', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('net'); });
    const logSpy = vi.spyOn(window, 'log').mockImplementation(() => {});

    await window.showSessionDetail('missing');

    expect(document.getElementById('sessions-detail').innerHTML).toContain('Failed to load');
    logSpy.mockRestore();
  });
});

describe('downloadSessionsReport', () => {
  const REPORT_MD = '# Session Report\n- Sessions: 1';

  beforeEach(() => {
    URL.createObjectURL = () => 'blob:mock';
    URL.revokeObjectURL = () => {};
    HTMLAnchorElement.prototype.click = () => {};
  });

  afterEach(() => { vi.restoreAllMocks(); });

  it('saves via pywebview when download_file is available', async () => {
    const dlSpy = vi.fn(async () => 'C:/reports/report.md');
    window.pywebview.api.download_file = dlSpy;
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, text: async () => REPORT_MD }));
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    await window.downloadSessionsReport();

    expect(dlSpy).toHaveBeenCalledTimes(1);
    const [content, filename] = dlSpy.mock.calls[0];
    expect(content).toBe(REPORT_MD);
    expect(filename).toMatch(/tiktok2mc-session-report-.*\.md/);
    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining('saved'), 'success');
  });

  it('falls back to browser download', async () => {
    delete window.pywebview.api.download_file;
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, text: async () => REPORT_MD }));
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});
    const appendSpy = vi.spyOn(document.body, 'appendChild').mockImplementation(() => {});
    const removeSpy = vi.spyOn(document.body, 'removeChild').mockImplementation(() => {});

    await window.downloadSessionsReport();

    expect(appendSpy).toHaveBeenCalled();
    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining('saved'), 'success');
    appendSpy.mockRestore();
    removeSpy.mockRestore();
  });

  it('shows error toast on failure', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 500, statusText: 'Err', json: async () => ({}), text: async () => '' }));
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    await window.downloadSessionsReport();

    expect(toastSpy).toHaveBeenCalledWith(expect.any(String), 'error');
  });
});
