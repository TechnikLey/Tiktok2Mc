import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('Help', () => {
  function resetModal() {
    const modal = document.getElementById('help-modal');
    if (modal) modal.classList.add('hidden');
  }

  beforeEach(() => {
    resetModal();
    I18N.setLang('en');
  });

  afterEach(() => {
    resetModal();
    vi.restoreAllMocks();
  });

  it('exposes Help on window', () => {
    expect(window.Help).toBeDefined();
    expect(typeof Help.openHelp).toBe('function');
    expect(typeof Help.closeHelp).toBe('function');
    expect(typeof Help.isOpen).toBe('function');
    expect(typeof Help.formatApiError).toBe('function');
  });

  it('covers every main view with a help topic', () => {
    expect(Help.topics).toContain('status');
    expect(Help.topics).toContain('plugins');
    expect(Help.topics).toContain('hooks');
    expect(Help.topics).toContain('overlays');
    expect(Help.topics).toContain('actions');
    expect(Help.topics).toContain('reactions');
    expect(Help.topics).toContain('commentCommands');
    expect(Help.topics).toContain('settings');
    expect(Help.topics).toContain('log');
    expect(Help.topics).toContain('console');
    expect(Help.topics).toContain('servers');
    expect(Help.topics).toContain('revenue');
    expect(Help.topics).toContain('triggers');
    expect(Help.topics).toContain('backups');
    expect(Help.topics).toContain('updates');
    expect(Help.topics).toContain('shortcuts');
  });

  it('renders every main view with a help button in the header', () => {
    const buttons = document.querySelectorAll('.btn-help');
    expect(buttons.length).toBeGreaterThanOrEqual(10);
    for (const btn of buttons) {
      expect(btn.getAttribute('onclick')).toMatch(/Help\.openHelp\('/);
    }
  });

  it('openHelp shows the modal with content', () => {
    Help.openHelp('status');
    expect(Help.isOpen()).toBe(true);
    const title = document.getElementById('help-modal-title');
    expect(title.textContent).toBe('Status');
    const body = document.getElementById('help-modal-body');
    expect(body.querySelectorAll('.help-section').length).toBeGreaterThan(0);
    expect(body.textContent.length).toBeGreaterThan(50);
  });

  it('closeHelp hides the modal', () => {
    Help.openHelp('status');
    expect(Help.isOpen()).toBe(true);
    Help.closeHelp();
    expect(Help.isOpen()).toBe(false);
  });

  it('falls back to the status topic for unknown topics', () => {
    Help.openHelp('does-not-exist');
    const title = document.getElementById('help-modal-title');
    expect(title.textContent).toBe('Status');
  });

  it('re-renders in German when the language changes while open', () => {
    Help.openHelp('settings');
    expect(document.getElementById('help-modal-title').textContent).toBe('Settings');
    I18N.setLang('de');
    expect(document.getElementById('help-modal-title').textContent).toBe('Einstellungen');
    expect(document.getElementById('help-modal-body').textContent).toContain('Konfiguration');
  });

  it('formatApiError returns a friendly message for unknown statuses', () => {
    const msg = Help.formatApiError(0, '');
    expect(msg).toMatch(/operation failed/i);
    expect(msg).not.toMatch(/\b0\b/);
  });

  it('formatApiError translates HTTP status codes', () => {
    expect(Help.formatApiError(500, '')).toMatch(/unexpected error/i);
    expect(Help.formatApiError(401, '')).toMatch(/authenticate/i);
    expect(Help.formatApiError(404, '')).toMatch(/does not exist/i);
  });

  it('formatApiError hides raw FastAPI validation details', () => {
    const raw = '[{"loc":["body","config"],"msg":"field required","type":"value_error.missing"}]';
    const msg = Help.formatApiError(422, raw);
    expect(msg).toMatch(/not valid/i);
    expect(msg).not.toContain('value_error.missing');
    expect(msg).not.toContain('loc');
  });

  it('formatApiError translates backend error codes by subsystem', () => {
    const msg = Help.formatApiError(400, 'TIKTOK-0001 connection lost');
    expect(msg).toMatch(/TikTok connection/i);
    const cfg = Help.formatApiError(500, 'CONFIG-0002 invalid yaml');
    expect(cfg).toMatch(/Configuration/i);
  });
});
