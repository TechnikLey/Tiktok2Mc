import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const MODAL_IDS = [
  'wizard', 'help-modal', 'confirm-dialog', 'server-create-modal', 'server-download-modal',
  'server-switch-modal', 'server-custom-modal', 'actions-add-modal',
  'reaction-delete-modal', 'reaction-wizard', 'plugin-review-modal',
  'hook-review-modal', 'review-modal', 'advanced-confirm-dialog',
  'unsaved-changes-modal', 'shutdown-overlay',
];

function resetAll() {
  for (const id of MODAL_IDS) {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  }
  I18N.setLang('en');
}

function fire(key, init = {}) {
  document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...init }));
}

function fireOn(el, key, init = {}) {
  el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...init }));
}

describe('Shortcuts', () => {
  beforeEach(() => {
    resetAll();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    resetAll();
    vi.restoreAllMocks();
  });

  it('exposes the Shortcuts API', () => {
    expect(window.Shortcuts).toBeDefined();
    expect(typeof Shortcuts.install).toBe('function');
    expect(typeof Shortcuts.bind).toBe('function');
    expect(typeof Shortcuts.list).toBe('function');
  });

  it('registers the default bindings', () => {
    const combos = Shortcuts.list().map(b => b.combo);
    expect(combos).toContain('ctrl+s');
    expect(combos).toContain('/');
    expect(combos).toContain('escape');
    expect(combos).toContain('shift+?');
  });

  it('finds a default list() with descriptions', () => {
    const entries = Shortcuts.list();
    for (const entry of entries) {
      expect(entry.combo).toBeTruthy();
      expect(entry.descKey).toBeTruthy();
    }
  });

  it('finds "?" opens the shortcuts help topic', () => {
    fire('?', { shiftKey: true });
    expect(Help.isOpen()).toBe(true);
    expect(document.getElementById('help-modal-title').textContent).toBe('Keyboard Shortcuts');
  });

  it('does not open help while typing "?" in an input', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();
    fireOn(input, '?', { shiftKey: true });
    expect(Help.isOpen()).toBe(false);
    input.remove();
  });

  it('focuses the search field of the active view on "/"', () => {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-log').classList.add('active');
    fire('/');
    expect(document.activeElement.id).toBe('log-search');
  });

  it('focuses the config editor search when the editor is open', () => {
    const editorEl = document.getElementById('config-editor');
    editorEl.classList.remove('hidden');
    fire('/');
    expect(document.activeElement.id).toBe('editor-search');
    editorEl.classList.add('hidden');
  });

  it('does not treat "/" as a shortcut while typing', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-log').classList.add('active');
    fireOn(input, '/');
    expect(document.activeElement).toBe(input);
    input.remove();
  });

  it('saves the active editor on Ctrl+S', () => {
    document.getElementById('config-editor').classList.remove('hidden');
    const spy = vi.spyOn(window.editor, 'save').mockImplementation(() => {});
    fire('s', { ctrlKey: true });
    expect(spy).toHaveBeenCalledTimes(1);
    document.getElementById('config-editor').classList.add('hidden');
  });

  it('saves the actions editor on Ctrl+S', () => {
    document.getElementById('actions-editor').classList.remove('hidden');
    const spy = vi.spyOn(window.actionsEditor, 'save').mockImplementation(() => {});
    fire('s', { ctrlKey: true });
    expect(spy).toHaveBeenCalledTimes(1);
    document.getElementById('actions-editor').classList.add('hidden');
  });

  it('saves via Ctrl+S even while typing in an input', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();
    document.getElementById('config-editor').classList.remove('hidden');
    const spy = vi.spyOn(window.editor, 'save').mockImplementation(() => {});
    fireOn(input, 's', { ctrlKey: true });
    expect(spy).toHaveBeenCalledTimes(1);
    input.remove();
    document.getElementById('config-editor').classList.add('hidden');
  });

  it('skips Ctrl+S while a modal is open', () => {
    document.getElementById('config-editor').classList.remove('hidden');
    document.getElementById('confirm-dialog').classList.remove('hidden');
    const spy = vi.spyOn(window.editor, 'save').mockImplementation(() => {});
    fire('s', { ctrlKey: true });
    expect(spy).not.toHaveBeenCalled();
    document.getElementById('confirm-dialog').classList.add('hidden');
    document.getElementById('config-editor').classList.add('hidden');
  });

  it('closes the help modal on Esc', () => {
    Help.openHelp('status');
    expect(Help.isOpen()).toBe(true);
    fire('Escape');
    expect(Help.isOpen()).toBe(false);
  });

  it('closes the topmost server modal on Esc', () => {
    document.getElementById('server-create-modal').classList.remove('hidden');
    fire('Escape');
    expect(document.getElementById('server-create-modal').classList.contains('hidden')).toBe(true);
  });

  it('closes a review modal on Esc', () => {
    document.getElementById('review-modal').classList.remove('hidden');
    fire('Escape');
    expect(document.getElementById('review-modal').classList.contains('hidden')).toBe(true);
  });

  it('cancels the confirm dialog on Esc', async () => {
    const p = showConfirmDialog('Title', 'Message');
    let resolved = null;
    p.then(value => { resolved = value; });
    fire('Escape');
    await Promise.resolve();
    expect(resolved).toBe(false);
  });

  it('cancels the confirm dialog again after a later Esc', async () => {
    const p = showConfirmDialog('Title', 'Message');
    let resolved = null;
    p.then(value => { resolved = value; });
    fire('Escape');
    await Promise.resolve();
    expect(resolved).toBe(false);
    // The dialog listener must have been removed: a second show+Esc still works
    const p2 = showConfirmDialog('Title', 'Message');
    let resolved2 = null;
    p2.then(value => { resolved2 = value; });
    fire('Escape');
    await Promise.resolve();
    expect(resolved2).toBe(false);
  });

  it('does not close the unsaved-changes guard modal on Esc', () => {
    document.getElementById('unsaved-changes-modal').classList.remove('hidden');
    fire('Escape');
    expect(document.getElementById('unsaved-changes-modal').classList.contains('hidden')).toBe(false);
  });

  it('ignores unrelated key presses', () => {
    const spy = vi.spyOn(window.editor, 'save').mockImplementation(() => {});
    fire('a', { ctrlKey: false });
    fire('s', { ctrlKey: false });
    expect(spy).not.toHaveBeenCalled();
  });
});
