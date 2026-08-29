import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const BACKUPS = {
  root: 'C:/backups',
  total: 2,
  categories: [
    {
      category: 'config',
      label: 'config',
      count: 1,
      entries: [
        {
          category: 'config',
          filename: 'config.v20260814_120000_000000.yaml.bak',
          label: '2026-08-14 12:00:00',
          size: 2048,
          restorable: true,
        },
      ],
    },
    {
      category: 'plugins/testplugin',
      label: 'plugins/testplugin',
      count: 1,
      entries: [
        {
          category: 'plugins/testplugin',
          filename: 'config.v20260814_110000_000000.yaml.bak',
          label: '2026-08-14 11:00:00',
          size: 300,
          restorable: true,
        },
      ],
    },
    {
      category: '_other',
      label: '_other',
      count: 1,
      entries: [
        {
          category: '_other',
          filename: 'gifts.json.v20260814_100000_000000.json.bak',
          label: '2026-08-14 10:00:00',
          size: 42,
          restorable: false,
        },
      ],
    },
  ],
};

describe('_formatBytes', () => {
  it('formats byte sizes', () => {
    expect(window._formatBytes(0)).toBe('0 B');
    expect(window._formatBytes(1023)).toBe('1023 B');
    expect(window._formatBytes(1024)).toBe('1.0 KB');
    expect(window._formatBytes(1536)).toBe('1.5 KB');
    expect(window._formatBytes(1048576)).toBe('1.0 MB');
  });

  it('handles missing input', () => {
    expect(window._formatBytes(undefined)).toBe('0 B');
  });
});

describe('_backupCategoryLabel', () => {
  it('localizes known categories', () => {
    I18N.setLang('en');
    expect(window._backupCategoryLabel('config')).toBe('Config');
    expect(window._backupCategoryLabel('actions')).toBe('Actions');
    expect(window._backupCategoryLabel('plugin_registry')).toBe('Plugin Registry');
    expect(window._backupCategoryLabel('migration')).toBe('Pre-Migration Snapshots');
  });

  it('labels plugin categories with the plugin name', () => {
    expect(window._backupCategoryLabel('plugins/timer')).toBe('Plugin: timer');
  });

  it('escapes unknown category names', () => {
    expect(window._backupCategoryLabel('a<b>')).toBe('a&lt;b&gt;');
  });

  it('labels _other and hook_registry categories', () => {
    I18N.setLang('en');
    expect(window._backupCategoryLabel('_other')).toBe('Other');
    expect(window._backupCategoryLabel('hook_registry')).toBe('Hook Registry');
  });
});

describe('renderBackups', () => {
  beforeEach(() => {
    I18N.setLang('en');
    window._backupsData = BACKUPS;
  });

  it('renders one section per category', () => {
    window.renderBackups();
    const root = document.getElementById('backups-root');
    const sections = root.querySelectorAll('.backup-category');
    expect(sections.length).toBe(3);
    expect(root.textContent).toContain('Config');
    expect(root.textContent).toContain('Plugin: testplugin');
  });

  it('shows restore buttons for all entries', () => {
    window.renderBackups();
    const root = document.getElementById('backups-root');
    const buttons = root.querySelectorAll('[onclick^="restoreBackup"]');
    expect(buttons.length).toBe(3);
  });

  it('shows filenames, timestamps and sizes', () => {
    window.renderBackups();
    const text = document.getElementById('backups-root').textContent;
    expect(text).toContain('config.v20260814_120000_000000.yaml.bak');
    expect(text).toContain('2026-08-14 12:00:00');
    expect(text).toContain('2.0 KB');
  });

  it('renders an empty state when there are no backups', () => {
    window._backupsData = { categories: [], total: 0 };
    window.renderBackups();
    expect(document.getElementById('backups-root').textContent).toContain('No backups yet');
  });
});

describe('loadBackups', () => {
  it('fetches and renders backups', async () => {
    globalThis.fetch = async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => BACKUPS,
    });
    await window.loadBackups();
    expect(window._backupsData.total).toBe(2);
    expect(document.getElementById('backups-root').textContent).toContain('Config');
  });

  it('shows an error message on failure', async () => {
    globalThis.fetch = async () => ({ ok: false, status: 500, statusText: 'Server Error', json: async () => ({}) });
    await window.loadBackups();
    expect(document.getElementById('backups-root').textContent).toContain('Failed to load backups');
  });
});

describe('createBackupsNow', () => {
  it('posts and shows a success toast', async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({ created: [{ target: 'config', category: 'config', path: 'x.bak' }], skipped: [] }),
    }));
    globalThis.fetch = fetchSpy;
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});
    await window.createBackupsNow();
    const call = fetchSpy.mock.calls[0][0];
    expect(call).toBe('/api/v1/backups/create');
    expect(JSON.parse(fetchSpy.mock.calls[0][1].body).targets).toContain('config');
    expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/backup/i), 'success');
    toastSpy.mockRestore();
  });

  it('shows a neutral toast when nothing was created', async () => {
    globalThis.fetch = async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({ created: [], skipped: ['config'] }),
    });
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});
    await window.createBackupsNow();
    expect(toastSpy).toHaveBeenCalledWith(expect.any(String), 'info');
    toastSpy.mockRestore();
  });
});

describe('restoreBackup', () => {
  beforeEach(() => {
    document.getElementById('confirm-dialog').classList.add('hidden');
    I18N.setLang('en');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('restores after the user confirms', async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({ status: 'ok', target: 'config.yaml' }),
    }));
    globalThis.fetch = fetchSpy;
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    window.restoreBackup('config', 'config.v20260814_120000_000000.yaml.bak');
    document.getElementById('btn-confirm-ok').click();
    await new Promise(r => setTimeout(r, 0));

    const call = fetchSpy.mock.calls[0][0];
    expect(call).toBe('/api/v1/backups/restore');
    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body).toEqual({ category: 'config', filename: 'config.v20260814_120000_000000.yaml.bak' });
    expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/restored/i), 'success');
    toastSpy.mockRestore();
  });

  it('does not post when the user cancels', async () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    window.restoreBackup('config', 'config.v20260814_120000_000000.yaml.bak');
    document.getElementById('btn-confirm-cancel').click();
    await new Promise(r => setTimeout(r, 0));

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe('restoreBackupCustom', () => {
  beforeEach(() => {
    document.getElementById('confirm-dialog').classList.add('hidden');
    document.getElementById('prompt-dialog').classList.add('hidden');
    I18N.setLang('en');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('restores with a custom target after prompt and confirm', async () => {
    const promptSpy = vi.spyOn(window, 'showPromptDialog').mockResolvedValue('data/gifts.json');
    const confirmSpy = vi.spyOn(window, 'showConfirmDialog').mockResolvedValue(true);
    const fetchSpy = vi.fn(async () => ({
      ok: true, status: 200, statusText: 'OK',
      json: async () => ({ status: 'ok', target: 'data/gifts.json' }),
    }));
    globalThis.fetch = fetchSpy;
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    await window.restoreBackupCustom('_other', 'gifts.json.bak');

    expect(promptSpy).toHaveBeenCalled();
    expect(confirmSpy).toHaveBeenCalled();
    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body).toEqual({ category: '_other', filename: 'gifts.json.bak', target: 'data/gifts.json' });
    expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/restored/i), 'success');
    toastSpy.mockRestore();
  });

  it('does not post when user cancels the prompt', async () => {
    vi.spyOn(window, 'showPromptDialog').mockResolvedValue(null);
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    await window.restoreBackupCustom('_other', 'gifts.json.bak');

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('does not post when user cancels the confirmation', async () => {
    vi.spyOn(window, 'showPromptDialog').mockResolvedValue('data/gifts.json');
    vi.spyOn(window, 'showConfirmDialog').mockResolvedValue(false);
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    await window.restoreBackupCustom('_other', 'gifts.json.bak');

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
