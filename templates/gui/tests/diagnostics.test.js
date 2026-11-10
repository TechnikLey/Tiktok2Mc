import { describe, it, expect, afterEach } from 'vitest';

/* Tests for the Diagnostics view (js/app-93-diagnostics.js).
   fetchJSON is stubbed via globalThis.fetch; the view markup comes from
   index.html which is preloaded into jsdom by tests/setup.js. */

const healthPayload = {
  uptime_seconds: 90,
  total_components: 4,
  running: 3,
  degraded: 1,
  failed: 0,
  degraded_components: ['gift_catalog'],
  failed_components: [],
  states: { gift_catalog: 'degraded' },
};

const crashPayload = {
  crash_count: 1,
  history: [
    {
      timestamp: '2026-11-10T10:00:00Z',
      code: 'CONFIG-0002',
      severity: 'ERROR',
      module: 'core.config_gate',
      exception: 'ValueError: bad yaml',
      context: { component: 'event_command_mapper' },
      stack: 'Traceback ...',
    },
  ],
};

const codesPayload = {
  total: 2,
  codes: [
    {
      code: 'CONFIG-0002',
      subsystem: 'CONFIG',
      severity: 'ERROR',
      message: 'Broken YAML.',
      description: 'd',
      recovery_hint: 'r',
      impact: 'i',
    },
    {
      code: 'TIKTOK-0001',
      subsystem: 'TIKTOK',
      severity: 'WARNING',
      message: 'Connection lost.',
      description: 'd',
      recovery_hint: 'r',
      impact: 'i',
    },
  ],
};

function stubFetch(routes) {
  globalThis.fetch = async (url) => {
    const path = String(url).split('/api/v1')[1] || String(url);
    const hit = routes[path];
    if (!hit) throw new Error(`unexpected fetch: ${path}`);
    return { ok: true, status: 200, statusText: 'OK', json: async () => hit };
  };
}

describe('DiagnosticsView', () => {
  afterEach(() => {
    delete globalThis.fetch;
  });

  it('renders health stats and component lists', async () => {
    stubFetch({ '/diagnostics/health': healthPayload, '/diagnostics/crash-history': crashPayload, '/diagnostics/error-codes': codesPayload });
    await diagnosticsView.load();
    const health = document.getElementById('diag-health');
    expect(health.querySelector('.diag-component-list.diag-degraded').textContent).toContain('gift_catalog');
    expect(health.textContent).toContain('4');
  });

  it('renders crash history entries and empty state', async () => {
    stubFetch({ '/diagnostics/crash-history': crashPayload, '/diagnostics/health': healthPayload, '/diagnostics/error-codes': codesPayload });
    await diagnosticsView._loadCrashes();
    const list = document.getElementById('diag-crash-list');
    expect(list.querySelectorAll('.crash-report-item').length).toBe(1);
    expect(list.textContent).toContain('CONFIG-0002');
    // empty state shows the placeholder and clears the list
    stubFetch({ '/diagnostics/crash-history': { crash_count: 0, history: [] } });
    await diagnosticsView._loadCrashes();
    expect(document.getElementById('diag-crash-empty').classList.contains('hidden')).toBe(false);
    expect(list.innerHTML).toBe('');
  });

  it('renders error codes and populates the subsystem filter once', async () => {
    stubFetch({ '/diagnostics/error-codes': codesPayload });
    await diagnosticsView.loadCodes();
    const rows = document.querySelectorAll('#diag-codes-list .diag-table-row');
    expect(rows.length).toBe(2);
    expect(document.querySelector('#diag-codes-list .diag-code').textContent).toBe('CONFIG-0002');
    const select = document.getElementById('diag-subsystem');
    const options = [...select.options].map((o) => o.value).filter(Boolean);
    expect(options).toEqual(['CONFIG', 'TIKTOK']);
    // filter request passes the selected subsystem
    let requested = '';
    globalThis.fetch = async (url) => {
      requested = String(url);
      return { ok: true, status: 200, statusText: 'OK', json: async () => ({ total: 0, codes: [] }) };
    };
    select.value = 'TIKTOK';
    await diagnosticsView.loadCodes();
    expect(requested).toContain('subsystem=TIKTOK');
  });
});
