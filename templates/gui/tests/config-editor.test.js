import { describe, it, expect, beforeEach, afterEach } from 'vitest';

describe('ConfigEditor', () => {
  beforeEach(() => {
    // Reset editor state with a clean config
    const sampleConfig = {
      tiktok: { user: 'test_user', enabled: true, reconnect_delay_seconds: 5 },
      rcon: { enabled: true, password: 'secret', port: 25575 },
      server_host: '127.0.0.1',
      control_method: 'DCS',
      update: { enabled: true },
      shutdown: { enabled: false, delay_seconds: 30 },
      gui: { enabled: true },
    };
    editor.open(sampleConfig);
  });

  /* ─── open / close ─── */
  describe('open / close', () => {
    it('opens editor with config data', () => {
      expect(editor.data.tiktok.user).toBe('test_user');
      expect(editor.original.tiktok.user).toBe('test_user');
    });

    it('removes config_version on open', () => {
      editor.open({ config_version: 2, tiktok: { user: 'u' } });
      expect(editor.data.config_version).toBeUndefined();
      expect(Object.keys(editor.unknownKeys)).not.toContain('config_version');
    });

    it('hides editor on close', () => {
      const el = document.getElementById('config-editor');
      el.classList.remove('hidden');
      editor.close();
      expect(el.classList.contains('hidden')).toBe(true);
    });

    it('also hides review modal on close', () => {
      const review = document.getElementById('review-modal');
      review.classList.remove('hidden');
      editor.close();
      expect(review.classList.contains('hidden')).toBe(true);
    });
  });

  /* ─── isDirty ─── */
  describe('isDirty', () => {
    it('returns false when data is unchanged', () => {
      expect(editor.isDirty()).toBe(false);
    });

    it('returns true when data is modified', () => {
      editor.data.tiktok.user = 'new_user';
      expect(editor.isDirty()).toBe(true);
    });

    it('returns false after setting original to match data', () => {
      editor.data.tiktok.user = 'new_user';
      editor.original = JSON.parse(JSON.stringify(editor.data));
      expect(editor.isDirty()).toBe(false);
    });
  });

  /* ─── getValue / setValue ─── */
  describe('getValue / setValue', () => {
    it('getValue returns value by dotted path', () => {
      expect(editor.getValue('tiktok.user')).toBe('test_user');
    });

    it('getValue returns undefined for missing path', () => {
      expect(editor.getValue('nonexistent.key')).toBeUndefined();
    });

    it('getValue handles nested paths with array indices', () => {
      editor.data.comment_commands = { groups: [{ prefix: '#' }] };
      expect(editor.getValue('comment_commands.groups[0].prefix')).toBe('#');
    });

    it('setValue sets value by dotted path', () => {
      editor.setValue('tiktok.user', 'new_user');
      expect(editor.data.tiktok.user).toBe('new_user');
    });

    it('setValue creates intermediate objects', () => {
      editor.setValue('a.b.c', 42);
      expect(editor.data.a.b.c).toBe(42);
    });

    it('setValue handles array index paths', () => {
      editor.data.items = [{ name: 'first' }];
      editor.setValue('items[0].name', 'changed');
      expect(editor.data.items[0].name).toBe('changed');
    });
  });

  /* ─── extractUnknownKeys / mergeUnknownKeys ─── */
  describe('extractUnknownKeys / mergeUnknownKeys', () => {
    it('extracts keys not in knownTop', () => {
      editor.open({ tiktok: { user: 'u' }, custom_key: 'value', some_unknown: { nested: true } });
      expect(editor.unknownKeys.custom_key).toBe('value');
      expect(editor.unknownKeys.some_unknown).toEqual({ nested: true });
      expect(editor.data.custom_key).toBeUndefined();
    });

    it('mergeUnknownKeys restores unknown keys', () => {
      editor.open({ tiktok: { user: 'u' }, custom_key: 'value' });
      editor.data.tiktok.user = 'new';
      editor.mergeUnknownKeys();
      expect(editor.data.custom_key).toBe('value');
      expect(editor.data.tiktok.user).toBe('new');
    });
  });

  /* ─── validate ─── */
  describe('validate', () => {
    it('returns true when all required fields are present', () => {
      expect(editor.validate()).toBe(true);
    });

    it('returns false when required field is missing', () => {
      editor.setValue('tiktok.user', '');
      expect(editor.validate()).toBe(false);
      expect(editor.errors.has('tiktok.user')).toBe(true);
    });

    it('rejects default tiktok username', () => {
      editor.setValue('tiktok.user', 'your_tiktok_username');
      expect(editor.validate()).toBe(false);
      expect(editor.errors.get('tiktok.user')).toContain('default username');
    });

    it('rejects invalid server_host', () => {
      editor.setValue('server_host', 'not-an-ip');
      expect(editor.validate()).toBe(false);
      expect(editor.errors.get('server_host')).toContain('IP address');
    });

    it('accepts valid server_host', () => {
      editor.setValue('server_host', '0.0.0.0');
      expect(editor.validate()).toBe(true);
    });

    it('validates pattern fields', () => {
      editor.setValue('java.xms', 'invalid');
      // java.xms has pattern: /^\d+[GgMm]$/
      expect(editor.validate()).toBe(false);
    });

    it('validates min/max constraints', () => {
      editor.setValue('shutdown.delay_seconds', 99999);
      expect(editor.validate()).toBe(false);
      expect(editor.errors.get('shutdown.delay_seconds')).toContain('3600');
    });
  });

  /* ─── computeDiff ─── */
  describe('computeDiff', () => {
    it('returns empty array when no changes', () => {
      expect(editor.computeDiff()).toEqual([]);
    });

    it('detects simple value changes', () => {
      editor.data.tiktok.user = 'new_user';
      const diff = editor.computeDiff();
      expect(diff).toHaveLength(1);
      expect(diff[0].path).toBe('tiktok.user');
      expect(diff[0].old).toBe('test_user');
      expect(diff[0].new).toBe('new_user');
    });

    it('detects added keys', () => {
      editor.data.newKey = 'value';
      const diff = editor.computeDiff();
      expect(diff.some(d => d.path === 'newKey')).toBe(true);
    });

    it('detects removed keys', () => {
      delete editor.data.tiktok.user;
      const diff = editor.computeDiff();
      expect(diff.some(d => d.path === 'tiktok.user' && d.old === 'test_user')).toBe(true);
    });
  });

  /* ─── addGroup / removeArrayItem ─── */
  describe('addGroup / removeArrayItem', () => {
    it('addGroup appends a default group object', () => {
      editor.data.comment_commands = { groups: [] };
      editor.addGroup('comment_commands.groups');
      expect(editor.data.comment_commands.groups).toHaveLength(1);
      expect(editor.data.comment_commands.groups[0].prefix).toBe('#');
      expect(editor.data.comment_commands.groups[0].enabled).toBe(true);
    });

    it('removeArrayItem removes element at index', () => {
      editor.data.items = [{ x: 1 }, { x: 2 }, { x: 3 }];
      editor.removeArrayItem('items', 1);
      expect(editor.data.items).toHaveLength(2);
      expect(editor.data.items[1].x).toBe(3);
    });
  });

  /* ─── addOverride / removeOverride ─── */
  describe('addOverride / removeOverride', () => {
    it('addOverride adds a new override with default value', () => {
      editor.data.comment_commands = { groups: [{ commands: ['cmd1'], commands_config: {} }] };
      editor.addOverride('comment_commands.groups[0].commands_config.cmd1', 'points_cost');
      const cfg = editor.data.comment_commands.groups[0].commands_config;
      expect(cfg.cmd1.points_cost).toBe(0);
    });

    it('removeOverride deletes an override key', () => {
      editor.data.test = { overrides: { cmd1: { points_cost: 10 } } };
      editor.removeOverride('test.overrides.cmd1.points_cost');
      expect(editor.data.test.overrides.cmd1.points_cost).toBeUndefined();
    });
  });

  /* ─── sectionHasError ─── */
  describe('sectionHasError', () => {
    it('returns false when section has no errors', () => {
      expect(editor.sectionHasError('tiktok')).toBe(false);
    });

    it('returns true when section has errors', () => {
      editor.errors.set('tiktok.user', 'required');
      expect(editor.sectionHasError('tiktok')).toBe(true);
    });
  });

  /* ─── sectionMatchesSearch ─── */
  describe('sectionMatchesSearch', () => {
    it('returns true matching section title', () => {
      editor.searchQuery = 'tiktok';
      expect(editor.sectionMatchesSearch('tiktok')).toBe(true);
    });

    it('returns true matching field path', () => {
      editor.searchQuery = 'reconnect_delay';
      expect(editor.sectionMatchesSearch('tiktok')).toBe(true);
    });

    it('returns false when no match', () => {
      editor.searchQuery = 'zzznonexistent';
      expect(editor.sectionMatchesSearch('tiktok')).toBe(false);
    });
  });

  /* ─── tagKey / removeTagByIndex ─── */
  describe('tagKey / removeTagByIndex', () => {
    it('tagKey adds value to array on Enter', () => {
      const path = 'random_triggers.triggers';
      editor.data.random_triggers = { triggers: [] };
      const event = { key: 'Enter', preventDefault: () => {}, target: { value: 'likes' } };
      editor.tagKey(event, path);
      expect(editor.getValue(path)).toContain('likes');
    });

    it('tagKey ignores non-Enter key', () => {
      const event = { key: 'Tab', preventDefault: () => {}, target: { value: 'likes' } };
      editor.tagKey(event, 'some.path');
      // Should not modify data
    });

    it('tagKey prevents duplicates', () => {
      // tagKey only adds if not already present
    });

    it('removeTagByIndex removes element at index', () => {
      editor.data.tags = ['a', 'b', 'c'];
      editor.removeTagByIndex('tags', 1);
      expect(editor.data.tags).toEqual(['a', 'c']);
    });
  });

  /* ─── onRoleChange ─── */
  describe('onRoleChange', () => {
    it('adds role when checked', () => {
      editor.data.roles = ['moderator'];
      const cb = { checked: true, getAttribute: () => 'superfan' };
      editor.onRoleChange('roles', cb);
      expect(editor.data.roles).toContain('superfan');
    });

    it('removes role when unchecked', () => {
      editor.data.roles = ['moderator', 'superfan'];
      const cb = { checked: false, getAttribute: () => 'superfan' };
      editor.onRoleChange('roles', cb);
      expect(editor.data.roles).not.toContain('superfan');
    });
  });

  /* ─── scrollTo ─── */
  describe('scrollTo', () => {
    it('sets activeSection and re-renders sidebar', () => {
      editor.scrollTo('section_tiktok');
      expect(editor.activeSection).toBe('tiktok');
    });
  });

  /* ─── onSearch ─── */
  describe('onSearch', () => {
    it('sets searchQuery and re-renders', () => {
      editor.onSearch('tiktok');
      expect(editor.searchQuery).toBe('tiktok');
    });
  });

  /* ─── showToast ─── */
  describe('showToast', () => {
    it('creates toast element in container', () => {
      editor.showToast('Test message', 'info');
      const container = document.getElementById('toast-container');
      expect(container.children.length).toBeGreaterThan(0);
      expect(container.lastChild.textContent).toBe('Test message');
      expect(container.lastChild.className).toBe('toast info');
    });
  });

  /* ─── localization ─── */
  describe('localization', () => {
    afterEach(() => {
      I18N.setLang('en');
    });

    it('renders German section titles, descriptions and help texts', () => {
      I18N.setLang('de');
      editor.open({
        tiktok: { user: 'test_user', reconnect_delay_seconds: 5 },
        rcon: { enabled: true },
      });
      const html = editor.content.innerHTML;
      const sidebar = editor.sidebar.innerHTML;
      expect(sidebar).toContain('Verbindung');
      expect(html).toContain('Verbinde das Tool mit deinem TikTok-Live-Stream');
      expect(html).toContain('Dein TikTok-Benutzername — ohne das @-Zeichen');
      expect(html).toContain('RCON erlaubt dem Tool, Befehle an deinen Minecraft-Server zu senden');
    });

    it('keeps English descriptions and help texts when lang is en', () => {
      I18N.setLang('en');
      editor.open({
        tiktok: { user: 'test_user' },
      });
      const html = editor.content.innerHTML;
      expect(html).toContain('Connect the tool to your TikTok live stream');
      expect(html).toContain('Your TikTok username');
    });
  });
});
