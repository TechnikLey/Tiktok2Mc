import { describe, it, expect, beforeEach } from 'vitest';

describe('PluginConfigEditor', () => {
  beforeEach(() => {
    pluginEditor.pluginName = null;
    pluginEditor.displayName = null;
    pluginEditor.config = {};
    pluginEditor.schema = null;
    pluginEditor.original = {};
    pluginEditor.errors.clear();
    pluginEditor.searchQuery = '';
    pluginEditor.hasSchema = false;
  });

  /* ─── isDirty / close ─── */
  describe('isDirty / close', () => {
    it('returns false when config equals original', () => {
      pluginEditor.config = { a: 1 };
      pluginEditor.original = { a: 1 };
      expect(pluginEditor.isDirty()).toBe(false);
    });

    it('returns true when config differs', () => {
      pluginEditor.config = { a: 2 };
      pluginEditor.original = { a: 1 };
      expect(pluginEditor.isDirty()).toBe(true);
    });

    it('close hides editor and review modal', () => {
      const el = document.getElementById('plugin-config-editor');
      el.classList.remove('hidden');
      const review = document.getElementById('plugin-review-modal');
      review.classList.remove('hidden');
      pluginEditor.close();
      expect(el.classList.contains('hidden')).toBe(true);
      expect(review.classList.contains('hidden')).toBe(true);
    });
  });

  /* ─── getConfigValue / setConfigValue ─── */
  describe('getConfigValue / setConfigValue', () => {
    it('getConfigValue returns value by dotted path', () => {
      pluginEditor.config = { server: { port: 25565 } };
      expect(pluginEditor.getConfigValue('server.port')).toBe(25565);
    });

    it('getConfigValue returns undefined for missing path', () => {
      expect(pluginEditor.getConfigValue('missing.key')).toBeUndefined();
    });

    it('setConfigValue sets value by dotted path', () => {
      pluginEditor.setConfigValue('server.port', 25566);
      expect(pluginEditor.config.server.port).toBe(25566);
    });

    it('setConfigValue creates intermediate objects', () => {
      pluginEditor.setConfigValue('a.b.c', 42);
      expect(pluginEditor.config.a.b.c).toBe(42);
    });
  });

  /* ─── validate ─── */
  describe('validate', () => {
    it('returns true for empty config without schema', () => {
      pluginEditor.hasSchema = false;
      expect(pluginEditor.validate()).toBe(true);
    });

    it('validates required fields', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.schema = {
        fields: [
          { key: 'api_key', type: 'string', required: true },
        ],
      };
      expect(pluginEditor.validate()).toBe(false);
      expect(pluginEditor.errors.has('api_key')).toBe(true);
    });

    it('validates integer type', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { count: 'not-a-number' };
      pluginEditor.schema = {
        fields: [{ key: 'count', type: 'integer' }],
      };
      expect(pluginEditor.validate()).toBe(false);
      expect(pluginEditor.errors.has('count')).toBe(true);
    });

    it('validates number type', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { price: 'abc' };
      pluginEditor.schema = {
        fields: [{ key: 'price', type: 'number' }],
      };
      expect(pluginEditor.validate()).toBe(false);
      expect(pluginEditor.errors.has('price')).toBe(true);
    });

    it('validates color format', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { color: 'not-a-hex' };
      pluginEditor.schema = {
        fields: [{ key: 'color', type: 'color' }],
      };
      expect(pluginEditor.validate()).toBe(false);
      expect(pluginEditor.errors.has('color')).toBe(true);
    });

    it('accepts valid hex color', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { color: '#ff0000' };
      pluginEditor.schema = {
        fields: [{ key: 'color', type: 'color' }],
      };
      expect(pluginEditor.validate()).toBe(true);
    });

    it('validates select options', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { mode: 'invalid' };
      pluginEditor.schema = {
        fields: [{ key: 'mode', type: 'select', options: ['a', 'b'] }],
      };
      expect(pluginEditor.validate()).toBe(false);
    });

    it('validates integer min/max', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { port: 99999 };
      pluginEditor.schema = {
        fields: [{ key: 'port', type: 'integer', min: 1, max: 65535 }],
      };
      expect(pluginEditor.validate()).toBe(false);
      expect(pluginEditor.errors.has('port')).toBe(true);
    });

    it('validates array item subfields', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { items: [{ name: '' }] };
      pluginEditor.schema = {
        fields: [{
          key: 'items', type: 'array', item_schema: {
            type: 'object', fields: [{ key: 'name', type: 'string', required: true }],
          },
        }],
      };
      expect(pluginEditor.validate()).toBe(false);
    });

    it('validates object subfields', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { settings: { host: '' } };
      pluginEditor.schema = {
        fields: [{
          key: 'settings', type: 'object', item_schema: {
            fields: [{ key: 'host', type: 'string', required: true }],
          },
        }],
      };
      expect(pluginEditor.validate()).toBe(false);
    });

    it('passes valid configuration', () => {
      pluginEditor.hasSchema = true;
      pluginEditor.config = { name: 'test', port: 25565, color: '#00ff00' };
      pluginEditor.schema = {
        fields: [
          { key: 'name', type: 'string' },
          { key: 'port', type: 'integer', min: 1, max: 65535 },
          { key: 'color', type: 'color' },
        ],
      };
      expect(pluginEditor.validate()).toBe(true);
    });
  });

  /* ─── computeDiff ─── */
  describe('computeDiff', () => {
    it('returns empty for unchanged config', () => {
      pluginEditor.config = { a: 1 };
      pluginEditor.original = { a: 1 };
      expect(pluginEditor.computeDiff()).toEqual([]);
    });

    it('detects changed values', () => {
      pluginEditor.config = { a: 2 };
      pluginEditor.original = { a: 1 };
      const diff = pluginEditor.computeDiff();
      expect(diff).toHaveLength(1);
      expect(diff[0].path).toBe('a');
      expect(diff[0].new).toBe(2);
    });
  });

  /* ─── groupByCategory ─── */
  describe('groupByCategory', () => {
    it('groups fields by category', () => {
      pluginEditor.schema = {
        fields: [
          { key: 'host', category: 'Server' },
          { key: 'port', category: 'Server' },
          { key: 'color', category: 'Appearance' },
        ],
      };
      const cats = pluginEditor.groupByCategory();
      expect(Object.keys(cats)).toEqual(['Server', 'Appearance']);
      expect(cats.Server).toHaveLength(2);
      expect(cats.Appearance).toHaveLength(1);
    });

    it('defaults to General category', () => {
      pluginEditor.schema = {
        fields: [{ key: 'name' }],
      };
      const cats = pluginEditor.groupByCategory();
      expect(cats.General).toBeDefined();
      expect(cats.General).toHaveLength(1);
    });

    it('returns empty for no schema', () => {
      expect(pluginEditor.groupByCategory()).toEqual({});
    });
  });

  /* ─── findFieldByPath ─── */
  describe('findFieldByPath', () => {
    it('finds field by key', () => {
      pluginEditor.schema = { fields: [{ key: 'host', type: 'string' }] };
      const f = pluginEditor.findFieldByPath('host');
      expect(f).toBeDefined();
      expect(f.type).toBe('string');
    });

    it('returns null for unknown path', () => {
      expect(pluginEditor.findFieldByPath('unknown')).toBeNull();
    });
  });

  /* ─── addArrayObjectItem / removeArrayItem ─── */
  describe('addArrayObjectItem / removeArrayItem', () => {
    it('addArrayObjectItem appends default row', () => {
      pluginEditor.schema = {
        fields: [{
          key: 'items', type: 'array', item_schema: {
            type: 'object', fields: [
              { key: 'name', type: 'string', default: 'new' },
              { key: 'count', type: 'integer', default: 0 },
            ],
          },
        }],
      };
      pluginEditor.config = { items: [] };
      pluginEditor.addArrayObjectItem('items');
      expect(pluginEditor.config.items).toHaveLength(1);
      expect(pluginEditor.config.items[0].name).toBe('new');
      expect(pluginEditor.config.items[0].count).toBe(0);
    });

    it('removeArrayItem removes element at index', () => {
      pluginEditor.config = { items: [{ x: 1 }, { x: 2 }] };
      pluginEditor.removeArrayItem('items', 0);
      expect(pluginEditor.config.items).toHaveLength(1);
      expect(pluginEditor.config.items[0].x).toBe(2);
    });
  });

  /* ─── tagKey / removeTagByIndex ─── */
  describe('tagKey / removeTagByIndex', () => {
    it('tagKey adds value on Enter', () => {
      pluginEditor.config = { tags: [] };
      const e = { key: 'Enter', preventDefault: () => {}, target: { value: 'newtag' } };
      pluginEditor.tagKey(e, 'tags');
      expect(pluginEditor.config.tags).toContain('newtag');
    });

    it('tagKey ignores duplicate', () => {
      pluginEditor.config = { tags: ['existing'] };
      const e = { key: 'Enter', preventDefault: () => {}, target: { value: 'existing' } };
      pluginEditor.tagKey(e, 'tags');
      expect(pluginEditor.config.tags).toEqual(['existing']);
    });

    it('removeTagByIndex removes element by index', () => {
      pluginEditor.config = { tags: ['a', 'b', 'c'] };
      pluginEditor.removeTagByIndex('tags', 1);
      expect(pluginEditor.config.tags).toEqual(['a', 'c']);
    });
  });

  /* ─── parseRawJson ─── */
  describe('parseRawJson', () => {
    it('parses valid JSON', () => {
      document.getElementById('plugin-raw-json').value = '{"key": "value"}';
      pluginEditor.parseRawJson();
      expect(pluginEditor.config.key).toBe('value');
    });

    it('does not modify config on invalid JSON', () => {
      document.getElementById('plugin-raw-json').value = '{invalid}';
      pluginEditor.config = { original: true };
      pluginEditor.parseRawJson();
      expect(pluginEditor.config.original).toBe(true);
    });
  });

  /* ─── fieldHasError ─── */
  describe('fieldHasError', () => {
    it('returns false when no errors', () => {
      expect(pluginEditor.fieldHasError('any.path')).toBe(false);
    });

    it('returns true when field has error', () => {
      pluginEditor.errors.set('host', 'required');
      expect(pluginEditor.fieldHasError('host')).toBe(true);
    });

    it('returns true for nested path under error', () => {
      pluginEditor.errors.set('items[0].name', 'required');
      expect(pluginEditor.fieldHasError('items[0]')).toBe(true);
    });
  });

  /* ─── validateField ─── */
  describe('validateField', () => {
    it('requires field when required and empty', () => {
      const err = pluginEditor.validateField({ key: 'x', type: 'string', required: true }, '');
      expect(err).toBe('This field is required.');
    });

    it('requires array field when empty array', () => {
      const err = pluginEditor.validateField({ key: 'x', type: 'array', required: true }, []);
      expect(err).toBe('This field is required.');
    });

    it('passes optional empty field', () => {
      const err = pluginEditor.validateField({ key: 'x', type: 'string' }, '');
      expect(err).toBeNull();
    });

    it('passes null for optional field', () => {
      const err = pluginEditor.validateField({ key: 'x', type: 'string' }, null);
      expect(err).toBeNull();
    });

    it('validates integer', () => {
      const err = pluginEditor.validateField({ key: 'x', type: 'integer' }, 42);
      expect(err).toBeNull();
    });

    it('rejects non-integer for integer type', () => {
      const err = pluginEditor.validateField({ key: 'x', type: 'integer' }, 42.5);
      expect(err).toBe('Must be an integer.');
    });
  });

  /* ─── search helpers ─── */
  describe('onSearch / categoryMatchesSearch / fieldMatchesSearch', () => {
    it('onSearch sets searchQuery and re-renders', () => {
      pluginEditor.onSearch('test');
      expect(pluginEditor.searchQuery).toBe('test');
    });

    it('categoryMatchesSearch returns true on category match', () => {
      pluginEditor.searchQuery = 'server';
      expect(pluginEditor.categoryMatchesSearch('Server', [{ key: 'port' }])).toBe(true);
    });

    it('categoryMatchesSearch returns true on field match', () => {
      pluginEditor.searchQuery = 'port';
      expect(pluginEditor.categoryMatchesSearch('Server', [{ key: 'port', label: 'Port' }])).toBe(true);
    });

    it('fieldMatchesSearch matches label', () => {
      pluginEditor.searchQuery = 'api key';
      expect(pluginEditor.fieldMatchesSearch({ label: 'API Key' })).toBe(true);
    });

    it('fieldMatchesSearch matches key', () => {
      pluginEditor.searchQuery = 'host';
      expect(pluginEditor.fieldMatchesSearch({ key: 'server_host' })).toBe(true);
    });

    it('fieldMatchesSearch matches help text', () => {
      pluginEditor.searchQuery = 'color';
      expect(pluginEditor.fieldMatchesSearch({ help: 'Hex color code' })).toBe(true);
    });
  });
});
