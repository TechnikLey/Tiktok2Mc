import { describe, it, expect, beforeEach } from 'vitest';

const SAMPLE_CONFIG = {
  enabled: true,
  spam_protection: {
    min_interval_s: 4,
    max_per_minute: 8,
    max_queue: 15,
    max_len: 120,
    dedupe_identical: false,
  },
  triggers: { gift: true, follow: false, join: true },
  templates: {
    gift_thanks: 'Thanks {user} for {gift}!',
    follow_thanks: 'Thanks for the follow, {user}!',
    join_welcome: 'Welcome!',
  },
  keyword_replies: { discord: 'Join our Discord, {user}!' },
  session: { tt_target_idc: '' },
};

function mockFetch(routes) {
  window.fetch = async (url, opts) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    const handler = routes[path];
    if (!handler) {
      throw new Error('Unexpected fetch: ' + path);
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => handler(opts),
    };
  };
}

describe('ChatbotEditor', () => {
  beforeEach(() => {
    mockFetch({
      '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
      '/chatbot/status': () => ({ status: null }),
    });
    I18N.setLang('en');
  });

  /* ─── open / load ─── */
  describe('open / load', () => {
    it('shows the editor and applies config to the form', async () => {
      await chatbotEditor.open();
      expect(chatbotEditor.el.classList.contains('hidden')).toBe(false);
      expect(document.getElementById('cb-enabled').checked).toBe(true);
      expect(document.getElementById('cb-on-gift').checked).toBe(true);
      expect(document.getElementById('cb-on-follow').checked).toBe(false);
      expect(document.getElementById('cb-on-join').checked).toBe(true);
      expect(document.getElementById('cb-gift-thanks').value).toBe('Thanks {user} for {gift}!');
      expect(document.getElementById('cb-min-interval').value).toBe('4');
      expect(document.getElementById('cb-max-per-minute').value).toBe('8');
      expect(document.getElementById('cb-dedupe').checked).toBe(false);
    });

    it('treats missing trigger keys as defaults (gift/follow on, join off)', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: {} }),
        '/chatbot/status': () => ({ status: null }),
      });
      await chatbotEditor.open();
      expect(document.getElementById('cb-on-gift').checked).toBe(true);
      expect(document.getElementById('cb-on-follow').checked).toBe(true);
      expect(document.getElementById('cb-on-join').checked).toBe(false);
    });

    it('renders keyword rows from config', async () => {
      await chatbotEditor.open();
      const rows = document.querySelectorAll('.chatbot-keyword-row');
      expect(rows.length).toBe(1);
      expect(rows[0].querySelector('.cb-kw').value).toBe('discord');
      expect(rows[0].querySelector('.cb-reply').value).toBe('Join our Discord, {user}!');
    });

    it('is not dirty after a clean load', async () => {
      await chatbotEditor.open();
      expect(chatbotEditor.isDirty()).toBe(false);
      expect(document.getElementById('chatbot-save').disabled).toBe(true);
    });
  });

  /* ─── collect ─── */
  describe('_collect', () => {
    it('round-trips form values into the config structure', async () => {
      await chatbotEditor.open();
      document.getElementById('cb-enabled').checked = false;
      document.getElementById('cb-min-interval').value = '2.5';
      document.getElementById('cb-max-len').value = '99';
      const cfg = chatbotEditor._collect();
      expect(cfg.enabled).toBe(false);
      expect(cfg.spam_protection.min_interval_s).toBe(2.5);
      expect(cfg.spam_protection.max_len).toBe(99);
      expect(cfg.triggers).toEqual({ gift: true, follow: false, join: true });
      expect(cfg.templates.gift_thanks).toBe('Thanks {user} for {gift}!');
      expect(cfg.keyword_replies).toEqual({ discord: 'Join our Discord, {user}!' });
    });

    it('drops keyword rows with empty keyword or reply', async () => {
      await chatbotEditor.open();
      chatbotEditor._keywordRows().push({ keyword: '', reply: 'x' });
      chatbotEditor._keywordRows().push({ keyword: 'hi', reply: '' });
      const cfg = chatbotEditor._collect();
      expect(cfg.keyword_replies).toEqual({ discord: 'Join our Discord, {user}!' });
    });

    it('lowercases and trims keywords', () => {
      chatbotEditor._keywords = [{ keyword: '  DISCORD ', reply: 'yo' }];
      const cfg = chatbotEditor._collect();
      expect(cfg.keyword_replies.discord).toBe('yo');
    });
  });

  /* ─── keywords ─── */
  describe('keyword rows', () => {
    it('removeKeyword drops the row and marks dirty', async () => {
      await chatbotEditor.open();
      chatbotEditor.removeKeyword(0);
      expect(chatbotEditor._keywordRows().length).toBe(0);
      expect(chatbotEditor.isDirty()).toBe(true);
      expect(document.querySelectorAll('.chatbot-keyword-row').length).toBe(0);
    });

    it('shows placeholder text when no keywords exist', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: {} }),
        '/chatbot/status': () => ({ status: null }),
      });
      await chatbotEditor.open();
      expect(document.getElementById('cb-keywords-list').textContent).toContain('No keyword replies');
    });
  });

  /* ─── save ─── */
  describe('save', () => {
    it('PUTs the collected config and clears dirty state', async () => {
      let received = null;
      mockFetch({
        '/chatbot/config': (opts) => {
          if (opts && opts.method === 'PUT') {
            received = JSON.parse(opts.body);
            return { chatbot: SAMPLE_CONFIG, reloaded: true };
          }
          return { chatbot: SAMPLE_CONFIG };
        },
        '/chatbot/status': () => ({ status: null }),
      });
      await chatbotEditor.open();
      document.getElementById('cb-enabled').checked = false;
      chatbotEditor._markDirty();
      await chatbotEditor.save();
      expect(received.chatbot.enabled).toBe(false);
      expect(received.chatbot.spam_protection.max_per_minute).toBe(8);
      expect(chatbotEditor.isDirty()).toBe(false);
      expect(document.getElementById('chatbot-save').disabled).toBe(true);
    });

    it('keeps session.tt_target_idc through a save round-trip', async () => {
      let received = null;
      mockFetch({
        '/chatbot/config': (opts) => {
          if (opts && opts.method === 'PUT') {
            received = JSON.parse(opts.body);
            return { chatbot: SAMPLE_CONFIG, reloaded: true };
          }
          return { chatbot: { ...SAMPLE_CONFIG, session: { tt_target_idc: 'aws' } } };
        },
        '/chatbot/status': () => ({ status: null }),
      });
      await chatbotEditor.open();
      await chatbotEditor.save();
      expect(received.chatbot.session).toEqual({ tt_target_idc: 'aws' });
    });
  });

  /* ─── status rendering ─── */
  describe('_renderStatus', () => {
    it('shows unknown when no status reported', async () => {
      await chatbotEditor.open();
      chatbotEditor._renderStatus(null);
      const pill = document.getElementById('chatbot-status-pill');
      expect(pill.className).toContain('unknown');
    });

    it('shows active when enabled', async () => {
      await chatbotEditor.open();
      chatbotEditor._renderStatus({ enabled: true, sent_count: 3, dropped_count: 1, queue_size: 0 });
      const pill = document.getElementById('chatbot-status-pill');
      expect(pill.className).toContain('online');
      const stats = document.getElementById('chatbot-stats');
      expect(stats.textContent).toContain('3');
      expect(stats.textContent).toContain('Sent');
    });

    it('shows off when disabled', async () => {
      await chatbotEditor.open();
      chatbotEditor._renderStatus({ enabled: false });
      expect(document.getElementById('chatbot-status-pill').className).toContain('offline');
    });

    it('shows auto-disabled with error text', async () => {
      await chatbotEditor.open();
      chatbotEditor._renderStatus({ enabled: true, auto_disabled: true, last_error: 'auth failed' });
      const pill = document.getElementById('chatbot-status-pill');
      expect(pill.className).toContain('error');
      expect(document.getElementById('chatbot-stats').textContent).toContain('auth failed');
    });
  });

  /* ─── close guard ─── */
  describe('close', () => {
    it('hides immediately when not dirty', async () => {
      await chatbotEditor.open();
      chatbotEditor.close();
      expect(chatbotEditor.el.classList.contains('hidden')).toBe(true);
    });
  });
});
