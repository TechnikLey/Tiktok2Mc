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

describe('ReactionEditor arg collection', () => {
  function argInput(value) {
    const input = document.createElement('input');
    input.type = 'number';
    input.id = 'arg_amount';
    input.value = value;
    document.body.appendChild(input);
    return input;
  }

  function setup(amountArg) {
    reactionEditor.wizardDraft = { event: 'tiktok.gift', plugin: 'win-counter', command: 'remove_win', args: {} };
    reactionEditor.commandCatalog = {
      'win-counter': {
        remove_win: {
          name: 'Remove Win',
          args: { amount: { type: 'number', label: 'How many to remove', default: 1, min: 1, ...amountArg } },
        },
      },
    };
  }

  it('accepts a number when max is null in the schema', () => {
    setup({ max: null });
    const input = argInput('1');
    try {
      const result = reactionEditor._collectArgs();
      expect(result).toBe(true);
      expect(reactionEditor.wizardDraft.args.amount).toBe(1);
    } finally {
      input.remove();
    }
  });

  it('rejects a number above a real max', () => {
    setup({ max: 5 });
    const input = argInput('7');
    try {
      const result = reactionEditor._collectArgs();
      expect(result).toBe(false);
    } finally {
      input.remove();
    }
  });

  it('accepts a number above no max', () => {
    setup({});
    const input = argInput('999');
    try {
      const result = reactionEditor._collectArgs();
      expect(result).toBe(true);
      expect(reactionEditor.wizardDraft.args.amount).toBe(999);
    } finally {
      input.remove();
    }
  });
});

describe('ReactionEditor wizard step 1 categories', () => {
  it('groups plugin events under their declared category', () => {
    reactionEditor.eventCatalog = {
      'tiktok.follow': { name: 'New Follower', desc: 'Follow', category: 'tiktok', icon: '👤' },
      'music.track': { name: 'Track', desc: 'A track', category: 'music', icon: '🎵' },
      'win.milestone': { name: 'Milestone', desc: 'A win', category: 'win', icon: '🏆' },
      'timer.zero': { name: 'Timer Zero', desc: 'Zero', category: 'timer', icon: '⏰' },
    };
    const html = reactionEditor._renderStepEvent();
    expect(html).toContain('TikTok Events');
    expect(html).toContain('>Music</strong>');
    expect(html).toContain('>Win</strong>');
    expect(html).toContain('>Timer</strong>');
    expect(html).not.toContain('Timer Events');
    expect(html).not.toContain('Plugin &amp; Custom Events');
  });

  it('labels plugin categories with the plugin display name', () => {
    reactionEditor.pluginCatalog = {
      timer: { name: 'Timer', icon: '⏱️' },
      'spotify-control': { name: 'Spotify Control', icon: '🎵' },
    };
    expect(reactionEditor._categoryLabel('timer')).toBe('Timer');
    expect(reactionEditor._categoryLabel('spotify-control')).toBe('Spotify Control');
    expect(reactionEditor._categoryLabel('custom')).toBe('Custom Events');
  });
});

describe('ReactionEditor disabled-plugin rendering', () => {
  function render(data, plugins) {
    window.currentPlugins = plugins;
    reactionEditor.data = data;
    reactionEditor.eventCatalog = {
      'tiktok.gift': { name: 'Gift Received', desc: 'Gift', category: 'tiktok', icon: '🎁' },
    };
    reactionEditor.pluginCatalog = {
      timer: { name: 'Timer', icon: '⏱️' },
    };
    reactionEditor.commandCatalog = {
      timer: { add_time: { name: 'Add Time', desc: 'Add time', args: {} } },
    };
    reactionEditor.activeCategory = 'all';
    reactionEditor.searchQuery = '';
    reactionEditor.renderList();
    return document.getElementById('reaction-content').firstElementChild;
  }

  it('greys out the card, disables Test and shows a notice when the plugin is disabled', () => {
    const card = render(
      { 'tiktok.gift': [{ target: 'timer', command: 'add_time', args: { seconds: 30 } }] },
      [{ name: 'timer', enabled: false }]
    );
    expect(card.classList.contains('reaction-card--disabled')).toBe(true);
    expect(card.textContent).toContain('is disabled');
    expect(card.textContent).toContain('will not trigger');
    const testBtn = card.querySelector('.reaction-btn-test');
    expect(testBtn.disabled).toBe(true);
  });

  it('keeps the card active and Test enabled when the plugin is enabled', () => {
    const card = render(
      { 'tiktok.gift': [{ target: 'timer', command: 'add_time', args: { seconds: 30 } }] },
      [{ name: 'timer', enabled: true }]
    );
    expect(card.classList.contains('reaction-card--disabled')).toBe(false);
    expect(card.textContent).not.toContain('is disabled');
    const testBtn = card.querySelector('.reaction-btn-test');
    expect(testBtn.disabled).toBe(false);
  });

  it('keeps the card active when the plugin is unknown', () => {
    const card = render(
      { 'tiktok.gift': [{ target: 'timer', command: 'add_time', args: {} }] },
      []
    );
    expect(card.classList.contains('reaction-card--disabled')).toBe(false);
    expect(card.querySelector('.reaction-btn-test').disabled).toBe(false);
  });
});

describe('ReactionEditor arg chip rendering', () => {
  it('renders no args block when the reaction has none', () => {
    const html = reactionEditor._renderReactionArgs({ args: {} }, { args: {} });
    expect(html).toBe('');
  });

  it('renders each argument as a label/value chip', () => {
    const html = reactionEditor._renderReactionArgs(
      { args: { level: 50, query: 'hello' } },
      { args: {
        level: { type: 'number', label: 'Volume level' },
        query: { type: 'string', label: 'Song name' },
      } }
    );
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    const chips = wrapper.querySelectorAll('.reaction-arg-chip');
    expect(chips.length).toBe(2);
    expect(chips[0].querySelector('.reaction-arg-key').textContent).toBe('Volume level');
    expect(chips[0].querySelector('.reaction-arg-value').textContent).toBe('50');
    expect(chips[1].querySelector('.reaction-arg-key').textContent).toBe('Song name');
    expect(chips[1].querySelector('.reaction-arg-value').textContent).toBe('hello');
    expect(html).not.toContain('Options:');
    expect(html).not.toContain('{');
  });

  it('falls back to the raw key when the schema has no label', () => {
    const html = reactionEditor._renderReactionArgs(
      { args: { amount: 3 } },
      { args: {} }
    );
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    expect(wrapper.querySelector('.reaction-arg-key').textContent).toBe('amount');
    expect(wrapper.querySelector('.reaction-arg-value').textContent).toBe('3');
  });
});
