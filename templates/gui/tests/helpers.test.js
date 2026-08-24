import { describe, it, expect } from 'vitest';

/* ─── escapeHtml ─── */
describe('escapeHtml', () => {
  it('escapes HTML special characters', () => {
    expect(escapeHtml('<script>alert("xss")</script>')).toBe('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;');
  });
  it('escapes quotes for attribute contexts', () => {
    expect(escapeHtml('a"b\'c')).toBe('a&quot;b&#39;c');
  });
  it('escapes ampersands', () => {
    expect(escapeHtml('a&b')).toBe('a&amp;b');
  });
  it('returns empty string for empty input', () => {
    expect(escapeHtml('')).toBe('');
  });
  it('passes through safe strings unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world');
  });
  it('handles numbers', () => {
    expect(escapeHtml(123)).toBe('123');
  });
});

/* ─── toTitle ─── */
describe('toTitle', () => {
  it('converts snake_case to Title Case', () => {
    expect(toTitle('hello_world')).toBe('Hello World');
  });
  it('handles single word', () => {
    expect(toTitle('hello')).toBe('Hello');
  });
  it('handles empty string', () => {
    expect(toTitle('')).toBe('');
  });
  it('handles nested keys', () => {
    expect(toTitle('tiktok_user')).toBe('Tiktok User');
  });
  it('handles already spaced string', () => {
    expect(toTitle('hello world')).toBe('Hello World');
  });
});

/* ─── formatUptime ─── */
describe('formatUptime', () => {
  it('formats seconds only', () => {
    expect(formatUptime(45)).toBe('45s');
  });
  it('formats minutes and seconds', () => {
    expect(formatUptime(125)).toBe('2m 5s');
  });
  it('formats hours, minutes, seconds', () => {
    expect(formatUptime(3661)).toBe('1h 1m 1s');
  });
  it('handles zero', () => {
    expect(formatUptime(0)).toBe('0s');
  });
  it('rounds down partial seconds', () => {
    expect(formatUptime(1.7)).toBe('1s');
  });
});

/* ─── getPluginStatus ─── */
describe('getPluginStatus', () => {
  it('returns enabled status when plugin is enabled', () => {
    const result = getPluginStatus({ name: 'test', enabled: true });
    expect(result).toEqual({ label: 'Enabled', cls: 'status-enabled' });
  });
  it('returns disabled status when plugin is disabled', () => {
    const result = getPluginStatus({ name: 'test', enabled: false });
    expect(result).toEqual({ label: 'Disabled', cls: 'status-disabled' });
  });
  it('handles missing enabled field as disabled', () => {
    const result = getPluginStatus({ name: 'test' });
    expect(result).toEqual({ label: 'Disabled', cls: 'status-disabled' });
  });
});

/* ─── isFirstRun ─── */
describe('isFirstRun', () => {
  it('returns true when tiktok user is placeholder', () => {
    expect(isFirstRun({ tiktok: { user: 'your_tiktok_username' }, rcon: { password: 'abc' } })).toBe(true);
  });
  it('returns true when rcon password is missing', () => {
    expect(isFirstRun({ tiktok: { user: 'realuser' }, rcon: { password: '' } })).toBe(true);
  });
  it('returns true when rcon section is missing', () => {
    expect(isFirstRun({ tiktok: { user: 'realuser' } })).toBe(true);
  });
  it('returns false when configured', () => {
    expect(isFirstRun({ tiktok: { user: 'realuser' }, rcon: { password: 'secret' } })).toBe(false);
  });
  it('handles empty config', () => {
    expect(isFirstRun({})).toBe(true);
  });
});

/* ─── validatePassword ─── */
describe('validatePassword', () => {
  it('rejects password shorter than 8 chars', () => {
    const issues = validatePassword('Ab1!');
    expect(issues).toContain('At least 8 characters');
  });
  it('requires uppercase letter', () => {
    const issues = validatePassword('abcdef1!');
    expect(issues).toContain('One uppercase letter (A-Z)');
  });
  it('requires lowercase letter', () => {
    const issues = validatePassword('ABCDEF1!');
    expect(issues).toContain('One lowercase letter (a-z)');
  });
  it('requires number', () => {
    const issues = validatePassword('Abcdefg!');
    expect(issues).toContain('One number (0-9)');
  });
  it('requires special character', () => {
    const issues = validatePassword('Abcdef1g');
    expect(issues).toContain('One special character (!@#$ etc.)');
  });
  it('returns empty for strong password', () => {
    const issues = validatePassword('Abcdef1!');
    expect(issues).toEqual([]);
  });
});

/* ─── getPasswordStrength ─── */
describe('getPasswordStrength', () => {
  it('returns weak for short password', () => {
    expect(getPasswordStrength('a')).toBe('weak');
  });
  it('returns weak for low score', () => {
    expect(getPasswordStrength('abc')).toBe('weak');
  });
  it('returns medium for moderate score', () => {
    expect(getPasswordStrength('Abcdef1!')).toBe('strong');
  });
  it('returns strong for high score', () => {
    expect(getPasswordStrength('Abcdef1!xyz')).toBe('strong');
  });
});

/* ─── isAnyEditorDirty ─── */
describe('isAnyEditorDirty', () => {
  it('returns false when no editor is dirty', () => {
    editor.original = JSON.parse(JSON.stringify(editor.data));
    pluginEditor.original = JSON.parse(JSON.stringify(pluginEditor.config));
    actionsEditor.isDirty = false;
    expect(isAnyEditorDirty()).toBe(false);
  });
  it('returns true when config editor is dirty', () => {
    editor.data = { someKey: 'changed' };
    editor.original = { someKey: 'original' };
    actionsEditor.isDirty = false;
    pluginEditor.original = JSON.parse(JSON.stringify(pluginEditor.config));
    expect(isAnyEditorDirty()).toBe(true);
  });
  it('returns true when plugin editor is dirty', () => {
    editor.original = JSON.parse(JSON.stringify(editor.data));
    pluginEditor.config = { someKey: 'changed' };
    pluginEditor.original = { someKey: 'original' };
    actionsEditor.isDirty = false;
    expect(isAnyEditorDirty()).toBe(true);
  });
  it('returns true when actions editor is dirty', () => {
    editor.original = JSON.parse(JSON.stringify(editor.data));
    pluginEditor.original = JSON.parse(JSON.stringify(pluginEditor.config));
    actionsEditor.isDirty = true;
    expect(isAnyEditorDirty()).toBe(true);
  });
});

/* ─── unsaved changes guard on navigation ─── */
describe('unsaved changes guard on navigation', () => {
  function resetDirty() {
    editor.original = JSON.parse(JSON.stringify(editor.data));
    pluginEditor.original = JSON.parse(JSON.stringify(pluginEditor.config));
    actionsEditor.isDirty = false;
    reactionEditor._dirty = false;
    _pendingNavigation = null;
    document.getElementById('unsaved-changes-modal').classList.add('hidden');
    switchViewNow('status');
  }

  it('navigates immediately when no editor is dirty', () => {
    resetDirty();
    switchView('plugins');
    expect(document.getElementById('view-plugins').classList.contains('active')).toBe(true);
    expect(document.getElementById('unsaved-changes-modal').classList.contains('hidden')).toBe(true);
  });

  it('shows the unsaved modal and defers navigation when dirty', () => {
    resetDirty();
    actionsEditor.isDirty = true;
    switchView('plugins');
    expect(document.getElementById('unsaved-changes-modal').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('view-plugins').classList.contains('active')).toBe(false);
  });

  it('discard navigates and clears dirty state', () => {
    resetDirty();
    actionsEditor.isDirty = true;
    switchView('plugins');
    document.getElementById('btn-unsaved-exit-no-save').click();
    expect(document.getElementById('unsaved-changes-modal').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('view-plugins').classList.contains('active')).toBe(true);
    expect(actionsEditor.isDirty).toBe(false);
  });

  it('cancel aborts the navigation', () => {
    resetDirty();
    editor.data = { someKey: 'changed' };
    editor.original = { someKey: 'original' };
    switchView('plugins');
    document.getElementById('btn-unsaved-cancel').click();
    expect(document.getElementById('view-plugins').classList.contains('active')).toBe(false);
    expect(editor.isDirty()).toBe(true);
  });
});

/* ─── switchToEditorNow: restore state when an editor aborts opening ─── */
describe('switchToEditorNow aborted open restore', () => {
  function resetNav() {
    _pendingNavigation = null;
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector('.nav-item[data-view="status"]').classList.add('active');
  }

  it('restores the previous nav item when the editor aborts (resolves false)', async () => {
    resetNav();
    switchToEditorNow('chatbot', () => Promise.resolve(false));
    await new Promise(r => setTimeout(r, 0));
    expect(document.querySelector('.nav-item[data-view="chatbot"]').classList.contains('active')).toBe(false);
    expect(document.querySelector('.nav-item[data-view="status"]').classList.contains('active')).toBe(true);
  });

  it('re-opens a previously open editor overlay when the new editor aborts', async () => {
    _pendingNavigation = null;
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const cfgOverlay = document.getElementById('config-editor');
    const settingsNav = document.querySelector('.nav-item[data-view="settings"]');
    cfgOverlay.classList.add('hidden');
    cfgOverlay.classList.remove('hidden');
    settingsNav.classList.add('active');
    try {
      switchToEditorNow('chatbot', () => Promise.resolve(false));
      await new Promise(r => setTimeout(r, 0));
      expect(cfgOverlay.classList.contains('hidden')).toBe(false);
      expect(settingsNav.classList.contains('active')).toBe(true);
      expect(document.querySelector('.nav-item[data-view="chatbot"]').classList.contains('active')).toBe(false);
    } finally {
      cfgOverlay.classList.add('hidden');
      settingsNav.classList.remove('active');
    }
  });

  it('keeps the target nav item active when the editor opens normally', async () => {
    resetNav();
    const actionsEditorEl = document.getElementById('actions-editor');
    try {
      switchToEditorNow('actions', () => {});
      await new Promise(r => setTimeout(r, 0));
      expect(document.querySelector('.nav-item[data-view="actions"]').classList.contains('active')).toBe(true);
      expect(document.querySelector('.nav-item[data-view="status"]').classList.contains('active')).toBe(false);
    } finally {
      actionsEditorEl.classList.add('hidden');
    }
  });
});

/* ─── getMeta ─── */
describe('getMeta', () => {
  it('returns field metadata for known paths', () => {
    const meta = getMeta('tiktok.user');
    expect(meta.type).toBe('text');
    expect(meta.required).toBe(true);
    expect(meta.basic).toBe(true);
  });
  it('returns field metadata for array-index paths', () => {
    const meta = getMeta('comment_commands.groups[0].prefix');
    expect(meta).toBeTruthy();
  });
  it('returns defaults for unknown paths', () => {
    const meta = getMeta('some.unknown.path');
    expect(meta).toEqual({ basic: false, type: 'text' });
  });
});

/* ─── getHelp ─── */
describe('getHelp', () => {
  it('returns help text for known paths', () => {
    const help = getHelp('tiktok.user');
    expect(help).toContain('TikTok username');
  });
  it('handles array-index paths', () => {
    const help = getHelp('overlay.overlays[0].name');
    expect(typeof help).toBe('string');
    expect(help).toBe('');
  });
  it('returns empty for unknown paths', () => {
    expect(getHelp('some.unknown.path')).toBe('');
  });
});
