import { describe, it, expect, beforeEach } from 'vitest';

describe('ReactionEditor catalog', () => {
  beforeEach(() => {
    reactionEditor.eventCatalog = {};
    reactionEditor.pluginCatalog = {};
    reactionEditor.commandCatalog = {};
    reactionEditor.templates = [];
  });

  it('loadCatalog merges server events, plugins, commands and templates', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({
        events: {
          'demo.thing': { name: 'Thing', desc: 'A thing happened', category: 'custom', icon: '✨' },
        },
        plugins: {
          demo: { name: 'Demo', desc: 'Demo plugin', icon: '⚡' },
        },
        commands: {
          demo: { do: { name: 'Do Thing', desc: 'Do it', args: {} } },
        },
        templates: [
          { event: 'demo.thing', plugin: 'demo', command: 'do', args: {}, title: 'T', desc: 'D' },
        ],
      }),
    });
    await reactionEditor.loadCatalog();
    expect(reactionEditor.eventCatalog['demo.thing'].name).toBe('Thing');
    expect(reactionEditor.pluginCatalog['demo'].icon).toBe('⚡');
    expect(reactionEditor.commandCatalog['demo']['do'].name).toBe('Do Thing');
    expect(reactionEditor.templates[0].command).toBe('do');
  });

  it('loadCatalog preserves existing entries when the server omits them', async () => {
    reactionEditor.eventCatalog['keep.me'] = { name: 'Keep', category: 'custom' };
    reactionEditor.pluginCatalog['keep'] = { name: 'Keep', icon: '🔌' };
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ events: {}, plugins: {}, commands: {}, templates: [] }),
    });
    await reactionEditor.loadCatalog();
    expect(reactionEditor.eventCatalog['keep.me']).toBeDefined();
    expect(reactionEditor.pluginCatalog['keep']).toBeDefined();
  });

  it('loadCatalog survives a failed fetch', async () => {
    globalThis.fetch = async () => {
      throw new Error('network down');
    };
    await expect(reactionEditor.loadCatalog()).resolves.toBeUndefined();
  });
});
