import { describe, it, expect, beforeEach, vi } from 'vitest';

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
    const method = (opts && opts.method) || 'GET';
    const handler = routes[path] || routes[`${method} ${path}`];
    if (!handler) {
      throw new Error('Unexpected fetch: ' + method + ' ' + path);
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => handler(opts),
    };
  };
}

function mockSessionRoute(overrides = {}) {
  return () => ({
    configured: false,
    masked_session_id: null,
    tt_target_idc: '',
    updated: null,
    ...overrides,
  });
}

describe('ChatbotEditor', () => {
  beforeEach(() => {
    mockFetch({
      '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
      '/chatbot/status': () => ({ status: null }),
      '/chatbot/session': mockSessionRoute(),
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
        '/chatbot/session': mockSessionRoute(),
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

    it('typing into config inputs marks dirty but session inputs do not', async () => {
      await chatbotEditor.open();
      const template = document.getElementById('cb-gift-thanks');
      template.value = 'changed';
      template.dispatchEvent(new Event('input', { bubbles: true }));
      expect(chatbotEditor.isDirty()).toBe(true);

      chatbotEditor._dirty = false;
      const sessionId = document.getElementById('cb-session-id');
      sessionId.value = 'something';
      sessionId.dispatchEvent(new Event('input', { bubbles: true }));
      expect(chatbotEditor.isDirty()).toBe(false);
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
        '/chatbot/session': mockSessionRoute(),
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
        '/chatbot/session': mockSessionRoute(),
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
        '/chatbot/session': mockSessionRoute(),
      });
      await chatbotEditor.open();
      await chatbotEditor.save();
      expect(received.chatbot.session).toEqual({ tt_target_idc: 'aws' });
    });
  });

  /* ─── TikTok session ─── */
  describe('session', () => {
    it('shows "not signed in" without stored credentials', async () => {
      await chatbotEditor.open();
      const badge = document.getElementById('cb-session-badge');
      expect(badge.classList.contains('signed-in')).toBe(false);
      expect(badge.textContent).toContain('Not signed in');
      expect(document.getElementById('cb-session-id').classList.contains('hidden')).toBe(false);
    });

    it('renders signed-in state with masked id and keeps the input for re-login', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': mockSessionRoute({
          configured: true,
          masked_session_id: 'abcd…wxyz',
          tt_target_idc: 'va',
          updated: 1234567890,
        }),
      });
      await chatbotEditor.open();
      const badge = document.getElementById('cb-session-badge');
      expect(badge.classList.contains('signed-in')).toBe(true);
      expect(badge.textContent).toContain('abcd…wxyz');
      expect(document.getElementById('cb-session-idc').value).toBe('va');
      // The input stays visible so an expired session can be replaced
      // without signing out first, and load() never echoes the secret into it.
      const sessionIdInput = document.getElementById('cb-session-id');
      expect(sessionIdInput.classList.contains('hidden')).toBe(false);
      expect(sessionIdInput.value).not.toContain('abcd');
    });

    it('warns when enabled but not signed in', async () => {
      await chatbotEditor.open();
      const warn = document.getElementById('cb-session-warning');
      expect(warn.classList.contains('hidden')).toBe(false);
      expect(warn.textContent).toContain('no TikTok login');
    });

    it('does not warn when disabled', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: { ...SAMPLE_CONFIG, enabled: false } }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': mockSessionRoute(),
      });
      await chatbotEditor.open();
      expect(document.getElementById('cb-session-warning').classList.contains('hidden')).toBe(true);
    });

    it('PUTs new credentials and refreshes the badge', async () => {
      let received = null;
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': (opts) => {
          if (opts && opts.method === 'PUT') {
            received = JSON.parse(opts.body);
            return { configured: true, masked_session_id: 'abcd…wxyz', tt_target_idc: 'va', updated: 42 };
          }
          return mockSessionRoute()();
        },
      });
      await chatbotEditor.open();
      document.getElementById('cb-session-id').value = '  testsessionid123  ';
      document.getElementById('cb-session-idc').value = 'va';
      await chatbotEditor.saveSession();
      expect(received.session_id).toBe('testsessionid123');
      expect(received.tt_target_idc).toBe('va');
      expect(document.getElementById('cb-session-badge').textContent).toContain('abcd…wxyz');
      // Input is cleared after successful sign-in so the secret never lingers.
      expect(document.getElementById('cb-session-id').value).toBe('');
    });

    it('refuses to send an empty session id', async () => {
      const putSpy = vi.fn();
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': (opts) => {
          if (opts && opts.method === 'PUT') putSpy(opts);
          return mockSessionRoute()();
        },
      });
      await chatbotEditor.open();
      document.getElementById('cb-session-id').value = '   ';
      await chatbotEditor.saveSession();
      expect(putSpy).not.toHaveBeenCalled();
    });

    it('DELETE clears the stored login after confirmation', async () => {
      let deleteCalled = false;
      window.showConfirmDialog = async () => true;
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': (opts) => {
          if (opts && opts.method === 'DELETE') {
            deleteCalled = true;
            return { configured: false, masked_session_id: null, tt_target_idc: '', updated: null };
          }
          return mockSessionRoute({ configured: true, masked_session_id: 'abcd…wxyz' })();
        },
      });
      await chatbotEditor.open();
      expect(document.getElementById('cb-session-badge').classList.contains('signed-in')).toBe(true);
      await chatbotEditor.clearSession();
      expect(deleteCalled).toBe(true);
      expect(document.getElementById('cb-session-badge').classList.contains('signed-in')).toBe(false);
    });

    it('keeps the stored login when confirmation is cancelled', async () => {
      let deleteCalled = false;
      window.showConfirmDialog = async () => false;
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': (opts) => {
          if (opts && opts.method === 'DELETE') deleteCalled = true;
          return mockSessionRoute({ configured: true, masked_session_id: 'abcd…wxyz' })();
        },
      });
      await chatbotEditor.open();
      await chatbotEditor.clearSession();
      expect(deleteCalled).toBe(false);
      expect(document.getElementById('cb-session-badge').classList.contains('signed-in')).toBe(true);
    });

    it('toggles password visibility', async () => {
      await chatbotEditor.open();
      const input = document.getElementById('cb-session-id');
      const field = document.querySelector('#cb-session-card .chatbot-secret-field');
      expect(input.type).toBe('password');
      chatbotEditor.toggleSessionVisibility();
      expect(input.type).toBe('text');
      expect(field.classList.contains('revealed')).toBe(true);
      chatbotEditor.toggleSessionVisibility();
      expect(input.type).toBe('password');
    });

    it('toggles the help steps', async () => {
      await chatbotEditor.open();
      const steps = document.getElementById('cb-session-steps');
      expect(steps.classList.contains('hidden')).toBe(true);
      chatbotEditor.toggleSessionHelp();
      expect(steps.classList.contains('hidden')).toBe(false);
    });
  });

  /* ─── placeholder chips ─── */
  describe('insertPlaceholder', () => {
    it('inserts {gift} at the cursor position of the focused field', async () => {
      await chatbotEditor.open();
      const giftInput = document.getElementById('cb-gift-thanks');
      giftInput.focus();
      giftInput.setSelectionRange(giftInput.value.length, giftInput.value.length);
      const before = giftInput.value;
      chatbotEditor.insertPlaceholder('{gift}');
      expect(giftInput.value.startsWith(before)).toBe(true);
      expect(giftInput.value.endsWith('{gift}')).toBe(true);
      expect(chatbotEditor.isDirty()).toBe(true);
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

    it('shows active with hero title and stat cards', async () => {
      await chatbotEditor.open();
      chatbotEditor._renderStatus({ enabled: true, sent_count: 3, dropped_count: 1, queue_size: 0, has_session: true });
      const pill = document.getElementById('chatbot-status-pill');
      expect(pill.className).toContain('online');
      expect(pill.className).toContain('chatbot-pill');
      const heroDot = document.getElementById('cb-hero-dot');
      expect(heroDot.className).toContain('on');
      const stats = document.getElementById('chatbot-stats');
      expect(stats.querySelectorAll('.chatbot-stat').length).toBe(3);
      expect(stats.textContent).toContain('3');
      expect(stats.textContent).toContain('Sent');
    });

    it('shows off when disabled', async () => {
      await chatbotEditor.open();
      chatbotEditor._renderStatus({ enabled: false, has_session: false });
      expect(document.getElementById('chatbot-status-pill').className).toContain('offline');
      expect(document.getElementById('cb-hero-title').textContent).toContain('idle');
    });

    it('shows auto-disabled with error text and error dot', async () => {
      await chatbotEditor.open();
      chatbotEditor._renderStatus({ enabled: true, auto_disabled: true, last_error: 'auth failed' });
      const pill = document.getElementById('chatbot-status-pill');
      expect(pill.className).toContain('error');
      const errorBox = document.getElementById('chatbot-error');
      expect(errorBox.classList.contains('hidden')).toBe(false);
      expect(errorBox.textContent).toContain('auth failed');
      expect(document.getElementById('cb-hero-dot').className).toContain('error');
    });

    it('hides the error box when there is no error', async () => {
      await chatbotEditor.open();
      chatbotEditor._renderStatus({ enabled: true, last_error: '' });
      expect(document.getElementById('chatbot-error').classList.contains('hidden')).toBe(true);
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
