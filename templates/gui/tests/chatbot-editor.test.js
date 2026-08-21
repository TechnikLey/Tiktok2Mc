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
  replies: [
    { on: 'gift', match: '', message: 'Thanks {user} for {gift}!' },
    { on: 'keyword', match: 'discord', message: 'Join our Discord, {user}!' },
  ],
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
    localStorage.clear();
    // Most tests exercise the editor itself; opt in to skip the beta modal.
    localStorage.setItem('tiktok2mc_chatbot_beta_ack', '1');
    // Reset visibility: the editor DOM leaks between tests within this file.
    document.getElementById('chatbot-editor')?.classList.add('hidden');
    document.getElementById('chatbot-beta-modal')?.classList.add('hidden');
    I18N.setLang('en');
  });

  /* ─── open / load ─── */
  describe('open / load', () => {
    it('shows the editor and applies config to the form', async () => {
      await chatbotEditor.open();
      expect(chatbotEditor.el.classList.contains('hidden')).toBe(false);
      expect(document.getElementById('cb-enabled').checked).toBe(true);
      expect(document.getElementById('cb-min-interval').value).toBe('4');
      expect(document.getElementById('cb-max-per-minute').value).toBe('8');
      expect(document.getElementById('cb-dedupe').checked).toBe(false);
      const rows = document.querySelectorAll('.chatbot-reply-row');
      expect(rows.length).toBe(2);
      expect(rows[0].querySelector('.cb-reply-msg').value).toBe('Thanks {user} for {gift}!');
    });

    it('shows default spam values when the config has none', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: {} }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': mockSessionRoute(),
      });
      await chatbotEditor.open();
      expect(document.getElementById('cb-min-interval').value).toBe('7');
      expect(document.getElementById('cb-max-per-minute').value).toBe('8');
    });

    it('renders reply rules from config with event selects', async () => {
      await chatbotEditor.open();
      const rows = document.querySelectorAll('.chatbot-reply-row');
      expect(rows.length).toBe(2);
      expect(rows[0].querySelector('.cb-reply-on').value).toBe('gift');
      expect(rows[1].querySelector('.cb-reply-on').value).toBe('keyword');
      expect(rows[1].querySelector('.cb-reply-match').value).toBe('discord');
    });

    it('is not dirty after a clean load', async () => {
      await chatbotEditor.open();
      expect(chatbotEditor.isDirty()).toBe(false);
      expect(document.getElementById('chatbot-save').disabled).toBe(true);
    });

    it('typing into config inputs marks dirty but session inputs do not', async () => {
      await chatbotEditor.open();
      const msg = document.querySelector('.chatbot-reply-row .cb-reply-msg');
      msg.value = 'changed';
      msg.dispatchEvent(new Event('input', { bubbles: true }));
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
      expect(cfg.replies).toEqual(SAMPLE_CONFIG.replies);
    });

    it('drops rule rows without a message but keeps match-only rows out too', async () => {
      await chatbotEditor.open();
      chatbotEditor._rules.push({ on: 'join', match: '', message: '' });
      chatbotEditor._rules.push({ on: 'follow', match: '', message: 'welcome' });
      const cfg = chatbotEditor._collect();
      expect(cfg.replies).toEqual([
        { on: 'gift', match: '', message: 'Thanks {user} for {gift}!' },
        { on: 'keyword', match: 'discord', message: 'Join our Discord, {user}!' },
        { on: 'follow', match: '', message: 'welcome' },
      ]);
    });

    it('trims match and message values', () => {
      chatbotEditor._rules = [{ on: 'keyword', match: '  discord  ', message: '  yo  ' }];
      const cfg = chatbotEditor._collect();
      expect(cfg.replies[0].match).toBe('discord');
      expect(cfg.replies[0].message).toBe('yo');
    });
  });

  /* ─── reply rules ─── */
  describe('reply rules', () => {
    it('removeRule drops the row and marks dirty', async () => {
      await chatbotEditor.open();
      chatbotEditor.removeRule(0);
      expect(chatbotEditor._rules.length).toBe(1);
      expect(chatbotEditor.isDirty()).toBe(true);
      expect(document.querySelectorAll('.chatbot-reply-row').length).toBe(1);
    });

    it('addRule appends an empty gift row and marks dirty', async () => {
      await chatbotEditor.open();
      chatbotEditor.addRule();
      expect(chatbotEditor._rules.length).toBe(3);
      expect(chatbotEditor._rules[2]).toEqual({ on: 'gift', match: '', message: '' });
      expect(chatbotEditor.isDirty()).toBe(true);
    });

    it('shows placeholder text when no rules exist', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: {} }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': mockSessionRoute(),
      });
      await chatbotEditor.open();
      expect(document.getElementById('cb-replies-list').textContent).toContain('No replies configured');
    });

    it('hides the match input for follow/join rules via data-on attribute', async () => {
      await chatbotEditor.open();
      const row = document.querySelectorAll('.chatbot-reply-row')[1];
      const select = row.querySelector('.cb-reply-on');
      select.value = 'join';
      select.dispatchEvent(new Event('change', { bubbles: true }));
      expect(row.dataset.on).toBe('join');
      expect(chatbotEditor._rules[1].on).toBe('join');
      select.value = 'keyword';
      select.dispatchEvent(new Event('change', { bubbles: true }));
      expect(row.dataset.on).toBe('keyword');
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

    it('disables sign-out when not signed in', async () => {
      await chatbotEditor.open();
      const removeBtn = document.getElementById('cb-session-remove');
      expect(removeBtn.disabled).toBe(true);
      expect(removeBtn.title).toContain('Not signed in');
    });

    it('enables sign-out when a login is stored', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': mockSessionRoute({ configured: true, masked_session_id: 'abcd…wxyz' }),
      });
      await chatbotEditor.open();
      expect(document.getElementById('cb-session-remove').disabled).toBe(false);
    });
  });

  /* ─── master toggle ─── */
  describe('master toggle', () => {
    it('shows "Enable Bot" when off and "Disable Bot" when on', async () => {
      await chatbotEditor.open();
      const title = document.getElementById('cb-master-title');
      const enabled = document.getElementById('cb-enabled');
      expect(enabled.checked).toBe(true);
      expect(title.textContent).toBe('Disable Bot');
      enabled.checked = false;
      enabled.dispatchEvent(new Event('change', { bubbles: true }));
      expect(title.textContent).toBe('Enable Bot');
    });
  });

  /* ─── webview login ─── */
  describe('webview login', () => {
    function mockWebviewApi(states) {
      const queue = [...states];
      window.pywebview = {
        api: {
          open_tiktok_login: vi.fn(async () => 'started'),
          get_tiktok_login_state: vi.fn(async () => {
            const next = queue.length > 1 ? queue.shift() : queue[0];
            return typeof next === 'string'
              ? { state: next, masked_session_id: 'abcd…wxyz' }
              : next;
          }),
        },
      };
      return window.pywebview.api;
    }

    it('hides the webview button when the bridge lacks open_tiktok_login', async () => {
      await chatbotEditor.open();
      expect(document.getElementById('cb-session-webview').classList.contains('hidden')).toBe(true);
    });

    it('shows the webview button when the desktop app provides the API', async () => {
      mockWebviewApi(['waiting']);
      await chatbotEditor.open();
      expect(document.getElementById('cb-session-webview').classList.contains('hidden')).toBe(false);
    });

    it('stores credentials and refreshes the badge on success', async () => {
      let sessionConfigured = false;
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': () => ({
          configured: sessionConfigured,
          masked_session_id: sessionConfigured ? 'abcd…wxyz' : null,
          tt_target_idc: '',
          updated: sessionConfigured ? 42 : null,
        }),
      });
      const api = mockWebviewApi(['waiting']);
      // The Python side stores the cookie before reporting success.
      api.get_tiktok_login_state = vi.fn(async () => {
        if (!sessionConfigured) {
          sessionConfigured = true;
          return { state: 'waiting' };
        }
        return { state: 'success', masked_session_id: 'abcd…wxyz' };
      });
      await chatbotEditor.open();
      chatbotEditor._loginPollIntervalMs = 0;

      await chatbotEditor.webviewLogin();

      expect(api.open_tiktok_login).toHaveBeenCalledTimes(1);
      expect(api.get_tiktok_login_state).toHaveBeenCalled();
      // loadSession() ran again and picked up the new state
      expect(chatbotEditor._sessionInfo.configured).toBe(true);
      expect(document.getElementById('cb-session-badge').textContent).toContain('abcd…wxyz');
      expect(document.getElementById('cb-session-webview').disabled).toBe(false);
    });

    it('disables the button while waiting and restores it afterwards', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': mockSessionRoute(),
      });
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      window.pywebview = {
        api: {
          open_tiktok_login: async () => 'started',
          get_tiktok_login_state: async () => {
            await gate;
            return { state: 'cancelled' };
          },
        },
      };
      await chatbotEditor.open();
      chatbotEditor._loginPollIntervalMs = 0;

      const promise = chatbotEditor.webviewLogin();
      await Promise.resolve();
      const btn = document.getElementById('cb-session-webview');
      expect(btn.disabled).toBe(true);
      expect(btn.textContent).toBe('Waiting for login…');

      release();
      await promise;
      expect(btn.disabled).toBe(false);
      expect(btn.textContent).toBe('Sign in with TikTok');
    });

    it('does not poll when the login window is already running', async () => {
      const api = mockWebviewApi(['waiting']);
      api.open_tiktok_login = vi.fn(async () => 'already_running');
      await chatbotEditor.open();
      chatbotEditor._loginPollIntervalMs = 0;

      await chatbotEditor.webviewLogin();

      expect(api.get_tiktok_login_state).not.toHaveBeenCalled();
      expect(document.getElementById('cb-session-webview').disabled).toBe(false);
    });

    it('stops polling silently when the state call fails', async () => {
      window.pywebview = {
        api: {
          open_tiktok_login: async () => 'started',
          get_tiktok_login_state: async () => { throw new Error('bridge gone'); },
        },
      };
      await chatbotEditor.open();
      chatbotEditor._loginPollIntervalMs = 0;

      await chatbotEditor.webviewLogin();

      expect(document.getElementById('cb-session-webview').disabled).toBe(false);
    });
  });

  /* ─── placeholder chips ─── */
  describe('insertPlaceholder', () => {
    it('inserts {gift} at the cursor position of the focused rule message', async () => {
      await chatbotEditor.open();
      const msg = document.querySelectorAll('.chatbot-reply-row .cb-reply-msg')[0];
      msg.focus();
      msg.setSelectionRange(msg.value.length, msg.value.length);
      const before = msg.value;
      chatbotEditor.insertPlaceholder('{gift}');
      expect(msg.value.startsWith(before)).toBe(true);
      expect(msg.value.endsWith('{gift}')).toBe(true);
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
      expect(document.getElementById('cb-hero-title').textContent).toContain('disabled');
      expect(document.getElementById('cb-hero-sub').textContent).toContain('Enable the bot');
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

  /* ─── beta consent gate ─── */
  describe('beta consent gate', () => {
    it('shows the beta modal instead of the editor on first open', async () => {
      localStorage.removeItem('tiktok2mc_chatbot_beta_ack');
      await chatbotEditor.open();
      const modal = document.getElementById('chatbot-beta-modal');
      expect(modal.classList.contains('hidden')).toBe(false);
      expect(chatbotEditor.el.classList.contains('hidden')).toBe(true);
    });

    it('acceptBeta stores the ack and opens the editor', async () => {
      localStorage.removeItem('tiktok2mc_chatbot_beta_ack');
      await chatbotEditor.open();
      chatbotEditor.acceptBeta();
      expect(localStorage.getItem('tiktok2mc_chatbot_beta_ack')).toBe('1');
      expect(document.getElementById('chatbot-beta-modal').classList.contains('hidden')).toBe(true);
      expect(chatbotEditor.el.classList.contains('hidden')).toBe(false);
    });

    it('declineBeta closes the modal without storing an ack', async () => {
      localStorage.removeItem('tiktok2mc_chatbot_beta_ack');
      await chatbotEditor.open();
      chatbotEditor.declineBeta();
      expect(localStorage.getItem('tiktok2mc_chatbot_beta_ack')).toBeNull();
      expect(document.getElementById('chatbot-beta-modal').classList.contains('hidden')).toBe(true);
      expect(chatbotEditor.el.classList.contains('hidden')).toBe(true);
    });

    it('does not show the modal again once acked', async () => {
      await chatbotEditor.open();
      expect(document.getElementById('chatbot-beta-modal').classList.contains('hidden')).toBe(true);
    });
  });

  /* ─── enable/disable feedback ─── */
  describe('toggle save feedback', () => {
    it('shows the immediate-apply toast when the enabled state changes', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        'PUT /chatbot/config': () => ({ reloaded: true }),
        '/chatbot/status': () => ({ status: { enabled: true } }),
        '/chatbot/session': mockSessionRoute(),
      });
      await chatbotEditor.open();
      document.getElementById('cb-enabled').checked = false;
      await chatbotEditor.save();
      const toasts = [...document.querySelectorAll('#toast-container .toast')].map(t => t.textContent);
      expect(toasts.some(t => t.includes('applies immediately'))).toBe(true);
    });

    it('warns about a missing bridge when toggling without status', async () => {
      mockFetch({
        '/chatbot/config': () => ({ chatbot: SAMPLE_CONFIG }),
        'PUT /chatbot/config': () => ({ reloaded: true }),
        '/chatbot/status': () => ({ status: null }),
        '/chatbot/session': mockSessionRoute(),
      });
      await chatbotEditor.open();
      document.getElementById('cb-enabled').checked = false;
      await chatbotEditor.save();
      const toasts = [...document.querySelectorAll('#toast-container .toast')].map(t => t.textContent);
      expect(toasts.some(t => t.includes('bridge is not running'))).toBe(true);
    });
  });
});
