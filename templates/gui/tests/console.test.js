import { describe, it, expect, beforeEach, beforeAll } from 'vitest';

function flush() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

function keyOn(input, key) {
  const ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  input.dispatchEvent(ev);
  return ev;
}

describe('Console terminal', () => {
  let input;
  const HISTORY_KEY = 'tiktok2mc_console_history';

  beforeAll(() => {
    document.dispatchEvent(new Event('DOMContentLoaded'));
  });

  beforeEach(() => {
    localStorage.clear();
    I18N.setLang('en');
    input = document.getElementById('console-input');
    input.value = '';
    input.selectionStart = input.selectionEnd = 0;
    window.consoleTerminal._history.length = 0;
    window.consoleTerminal._historyIdx = -1;
    window.consoleTerminal._resetTabState();
  });

  describe('Tab autocomplete', () => {
    it('completes a unique command', () => {
      input.value = 'sum';
      input.selectionStart = input.selectionEnd = 3;
      keyOn(input, 'Tab');
      expect(input.value).toBe('summon');
    });

    it('cycles through matching commands on repeated Tab', () => {
      input.value = 'ga';
      input.selectionStart = input.selectionEnd = 2;
      keyOn(input, 'Tab');
      expect(input.value).toBe('gamemode');
      keyOn(input, 'Tab');
      expect(input.value).toBe('gamerule');
      keyOn(input, 'Tab');
      expect(input.value).toBe('gamemode');
    });

    it('leaves the value untouched when nothing matches', () => {
      input.value = 'zzz';
      input.selectionStart = input.selectionEnd = 3;
      keyOn(input, 'Tab');
      expect(input.value).toBe('zzz');
    });

    it('does nothing on an empty input', () => {
      keyOn(input, 'Tab');
      expect(input.value).toBe('');
    });

    it('preserves text after the cursor', () => {
      input.value = 'ga helo';
      input.selectionStart = 2;
      keyOn(input, 'Tab');
      expect(input.value).toBe('gamemode helo');
    });

    it('restarts the cycle after typing changes the prefix', () => {
      input.value = 'ga';
      input.selectionStart = input.selectionEnd = 2;
      keyOn(input, 'Tab');
      expect(input.value).toBe('gamemode');
      input.value = 'e';
      input.selectionStart = input.selectionEnd = 1;
      keyOn(input, 'Tab');
      expect(input.value).toBe('effect');
    });
  });

  describe('History', () => {
    it('runs the command on Enter and persists it to localStorage', async () => {
      let sent = null;
      window.fetch = async (url, opts) => {
        if (url.includes('/rcon/command')) {
          sent = JSON.parse(opts.body).command;
          return { ok: true, status: 200, statusText: 'OK', json: async () => ({ response: 'ok' }) };
        }
        return { ok: true, status: 200, statusText: 'OK', json: async () => ({}) };
      };
      input.value = 'say hello';
      keyOn(input, 'Enter');
      await flush();
      expect(sent).toBe('say hello');
      expect(input.value).toBe('');
      expect(window.consoleTerminal._history).toContain('say hello');
      expect(JSON.parse(localStorage.getItem(HISTORY_KEY))).toContain('say hello');
    });

    it('does not store blank commands', () => {
      input.value = '   ';
      keyOn(input, 'Enter');
      expect(window.consoleTerminal._history.length).toBe(0);
    });

    it('navigates the history with ArrowUp/ArrowDown', () => {
      const term = window.consoleTerminal;
      term._history.push('cmd1', 'cmd2');
      term._historyIdx = term._history.length;
      keyOn(input, 'ArrowUp');
      expect(input.value).toBe('cmd2');
      keyOn(input, 'ArrowUp');
      expect(input.value).toBe('cmd1');
      keyOn(input, 'ArrowDown');
      expect(input.value).toBe('cmd2');
      keyOn(input, 'ArrowDown');
      expect(input.value).toBe('');
    });

    it('caps persisted history at 50 entries', () => {
      const term = window.consoleTerminal;
      for (let i = 0; i < 60; i++) term._history.push('cmd' + i);
      term._saveHistory();
      const saved = JSON.parse(localStorage.getItem(HISTORY_KEY));
      expect(saved.length).toBe(50);
      expect(saved[saved.length - 1]).toBe('cmd59');
    });

    it('survives an empty/corrupt localStorage payload', () => {
      localStorage.setItem(HISTORY_KEY, 'not-json');
      const term = window.consoleTerminal;
      term._saveHistory();
      const saved = JSON.parse(localStorage.getItem(HISTORY_KEY));
      expect(Array.isArray(saved)).toBe(true);
    });
  });

  describe('Server console output gating', () => {
    beforeEach(() => {
      window.consoleTerminal._connected = false;
    });

    function emitConsoleLine(line) {
      const { _sseSource } = window;
      if (!_sseSource) return;
      _sseSource.onmessage({
        data: JSON.stringify({ type: 'server.console', data: { line, instance_id: 'default' } }),
      });
    }

    it('does not show server lines when RCON is not connected', () => {
      document.getElementById('console-output').innerHTML = '';
      window.consoleTerminal._connected = false;
      emitConsoleLine('Delayed TNT config got updated');
      expect(document.getElementById('console-output').textContent).not.toContain('Delayed TNT config got updated');
    });

    it('shows server lines when RCON is connected', () => {
      document.getElementById('console-output').innerHTML = '';
      window.consoleTerminal._connected = true;
      emitConsoleLine('Hello from server');
      expect(document.getElementById('console-output').textContent).toContain('Hello from server');
    });
  });

  describe('Disabled RCON command API', () => {
    it('shows a settings hint when the API answers with MC-0012', async () => {
      const prevFetch = window.fetch;
      window.fetch = async () => ({
        ok: false,
        status: 403,
        json: async () => ({ detail: 'MC-0012 Direct RCON command endpoint disabled.' }),
      });
      try {
        await consoleTerminal.sendCommand('say hi');
      } finally {
        window.fetch = prevFetch;
      }
      const output = document.getElementById('console-output').textContent;
      expect(output).toContain('Direct RCON commands are disabled');
    });
  });
});
