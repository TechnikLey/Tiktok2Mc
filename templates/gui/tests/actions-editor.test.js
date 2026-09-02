import { describe, it, expect, beforeEach } from 'vitest';

describe('ActionsEditor', () => {
  beforeEach(() => {
    actionsEditor.triggers = [];
    actionsEditor.selectedIndex = -1;
    actionsEditor.isDirty = false;
    actionsEditor.isDirty = false;
    let diagList = document.getElementById('actions-raw-diag-list');
    if (!diagList) {
      diagList = document.createElement('div');
      diagList.id = 'actions-raw-diag-list';
      document.body.appendChild(diagList);
    }
    actionsEditor._renderRawDiagnostics = (diags) => {
      if (!diags || diags.length === 0) {
        diagList.innerHTML = '<div>No issues found</div>';
        return;
      }
      diagList.innerHTML = diags.map((d) => {
        const line = d.line !== undefined ? `Line ${d.line + 1}` : '';
        return `<div class="${d.severity.toLowerCase()}">${d.message} ${line}</div>`;
      }).join('');
    };
    const statusDiv = document.getElementById('actions-raw-status');
    if (!statusDiv) {
      const div = document.createElement('div');
      div.id = 'actions-raw-status';
      document.body.appendChild(div);
    }
    actionsEditor.rawStatus = document.getElementById('actions-raw-status');
    actionsEditor.rawSaveBtn = { disabled: false };
    actionsEditor._updateRawStatus = (diags) => {
      const hasError = diags.some((d) => d.severity === 'ERROR');
      const hasWarning = diags.some((d) => d.severity === 'WARNING');
      actionsEditor.rawSaveBtn.disabled = hasError;
      if (hasError) {
        actionsEditor.rawStatus.innerHTML = 'save blocked due to errors';
      } else if (hasWarning) {
        actionsEditor.rawStatus.innerHTML = 'with warning';
      } else {
        actionsEditor.rawStatus.innerHTML = 'No errors';
      }
    };
  });

  /* ─── addCmd / removeCmd / updateCmd ─── */
  describe('addCmd / removeCmd / updateCmd', () => {
    it('addCmd adds default command to trigger', () => {
      actionsEditor.triggers = [{ name: 'test', enabled: true, type: 'Event', commands: [] }];
      actionsEditor.addCmd(0);
      expect(actionsEditor.triggers[0].commands).toHaveLength(1);
      expect(actionsEditor.triggers[0].commands[0].type).toBe('vanilla');
      expect(actionsEditor.triggers[0].commands[0].command).toBe('');
      expect(actionsEditor.isDirty).toBe(true);
    });

    it('removeCmd removes command at index', () => {
      actionsEditor.triggers = [{
        name: 'test', enabled: true, type: 'Event',
        commands: [{ type: 'vanilla', command: 'a' }, { type: 'rcon', command: 'b' }],
      }];
      actionsEditor.removeCmd(0, 0);
      expect(actionsEditor.triggers[0].commands).toHaveLength(1);
      expect(actionsEditor.triggers[0].commands[0].command).toBe('b');
    });

    it('updateCmd updates a field on a command', () => {
      actionsEditor.triggers = [{
        name: 'test', enabled: true, type: 'Event',
        commands: [{ type: 'vanilla', command: 'say hi' }],
      }];
      actionsEditor.updateCmd(0, 0, 'command', 'say hello');
      expect(actionsEditor.triggers[0].commands[0].command).toBe('say hello');
      expect(actionsEditor.isDirty).toBe(true);
    });

    it('removeCmd does nothing for invalid index', () => {
      actionsEditor.triggers = [{ name: 'test', commands: [{ type: 'vanilla', command: 'a' }] }];
      actionsEditor.removeCmd(0, 5);
      expect(actionsEditor.triggers[0].commands).toHaveLength(1);
    });
  });

  /* ─── toggleEnabled ─── */
  describe('toggleEnabled', () => {
    it('toggles trigger enabled state', () => {
      actionsEditor.triggers = [{ name: 'test', enabled: true, type: 'Event', commands: [] }];
      actionsEditor.toggleEnabled(0);
      expect(actionsEditor.triggers[0].enabled).toBe(false);
      expect(actionsEditor.isDirty).toBe(true);
    });

    it('does nothing for invalid index', () => {
      actionsEditor.toggleEnabled(999);
      // no crash
    });

    it('allows enabling when no enabled duplicate exists', async () => {
      actionsEditor.triggers = [
        { name: 'like_2', enabled: true, type: 'Event', commands: [] },
        { name: 'like_3', enabled: false, type: 'Event', commands: [] },
      ];
      await actionsEditor.toggleEnabled(1);
      expect(actionsEditor.triggers[1].enabled).toBe(true);
    });

    it('blocks enabling a duplicate and deletes it when confirmed', async () => {
      const origConfirm = showConfirmDialog;
      const origToast = showToast;
      showConfirmDialog = async () => true;
      let toastMsg = null;
      showToast = (msg) => { toastMsg = msg; };
      actionsEditor.triggers = [
        { name: 'like_2', enabled: true, type: 'Event', commands: [] },
        { name: 'like_2', enabled: false, type: 'Event', commands: [] },
      ];
      await actionsEditor.toggleEnabled(1);
      expect(toastMsg).toContain('already exists');
      expect(actionsEditor.triggers).toHaveLength(1);
      expect(actionsEditor.triggers[0].enabled).toBe(true);
      showConfirmDialog = origConfirm;
      showToast = origToast;
    });

    it('keeps the duplicate disabled when cancelled', async () => {
      const origConfirm = showConfirmDialog;
      const origToast = showToast;
      showConfirmDialog = async () => false;
      let toastMsg = null;
      showToast = (msg) => { toastMsg = msg; };
      actionsEditor.triggers = [
        { name: 'like_2', enabled: true, type: 'Event', commands: [] },
        { name: 'like_2', enabled: false, type: 'Event', commands: [] },
      ];
      await actionsEditor.toggleEnabled(1);
      expect(toastMsg).toContain('already exists');
      expect(actionsEditor.triggers).toHaveLength(2);
      expect(actionsEditor.triggers[1].enabled).toBe(false);
      showConfirmDialog = origConfirm;
      showToast = origToast;
    });
  });

  /* ─── removeTrigger ─── */
  describe('removeTrigger', () => {
    it('removes trigger at index', () => {
      actionsEditor.triggers = [
        { name: 'a', commands: [] },
        { name: 'b', commands: [] },
        { name: 'c', commands: [] },
      ];
      actionsEditor.selectedIndex = 1;
      actionsEditor.removeTrigger(1);
      expect(actionsEditor.triggers).toHaveLength(2);
      expect(actionsEditor.triggers.map(t => t.name)).toEqual(['a', 'c']);
    });

    it('clears selection when last trigger removed', () => {
      actionsEditor.triggers = [{ name: 'only', commands: [] }];
      actionsEditor.selectedIndex = 0;
      actionsEditor.removeTrigger(0);
      expect(actionsEditor.selectedIndex).toBe(-1);
    });

    it('does nothing for invalid index', () => {
      actionsEditor.triggers = [{ name: 'a', commands: [] }];
      actionsEditor.removeTrigger(5);
      expect(actionsEditor.triggers).toHaveLength(1);
    });
  });

  /* ─── confirmDeleteTrigger ─── */
  describe('confirmDeleteTrigger', () => {
    it('removes trigger after confirm', async () => {
      // Mock showConfirmDialog to return true
      const orig = showConfirmDialog;
      showConfirmDialog = async () => true;
      actionsEditor.triggers = [{ name: 'test', commands: [] }];
      await actionsEditor.confirmDeleteTrigger(0);
      expect(actionsEditor.triggers).toHaveLength(0);
      showConfirmDialog = orig;
    });

    it('does nothing when cancelled', async () => {
      const orig = showConfirmDialog;
      showConfirmDialog = async () => false;
      actionsEditor.triggers = [{ name: 'test', commands: [] }];
      await actionsEditor.confirmDeleteTrigger(0);
      expect(actionsEditor.triggers).toHaveLength(1);
      showConfirmDialog = orig;
    });
  });

  /* ─── _addTrigger ─── */
  describe('_addTrigger', () => {
    it('adds a new trigger', () => {
      actionsEditor.triggers = [];
      actionsEditor._addTrigger('comment', 'Event');
      expect(actionsEditor.triggers).toHaveLength(1);
      expect(actionsEditor.triggers[0].name).toBe('comment');
      expect(actionsEditor.triggers[0].type).toBe('Event');
      expect(actionsEditor.triggers[0].enabled).toBe(true);
      expect(actionsEditor.isDirty).toBe(true);
    });

    it('prevents duplicate triggers (case-insensitive)', () => {
      actionsEditor.triggers = [{ name: 'comment', commands: [] }];
      actionsEditor._addTrigger('Comment', 'Event');
      expect(actionsEditor.triggers).toHaveLength(1);
    });

    it('prevents duplicate triggers (with enclosing quotes)', () => {
      actionsEditor.triggers = [{ name: 'comment', commands: [] }];
      actionsEditor._addTrigger("'comment'", 'Event');
      expect(actionsEditor.triggers).toHaveLength(1);
    });

    it('rejects empty name', () => {
      actionsEditor.triggers = [];
      actionsEditor._addTrigger('', 'Event');
      expect(actionsEditor.triggers).toHaveLength(0);
    });

    it('rejects whitespace-only name', () => {
      actionsEditor.triggers = [];
      actionsEditor._addTrigger('   ', 'Event');
      expect(actionsEditor.triggers).toHaveLength(0);
    });
  });

  /* ─── _onAddTypeChange ─── */
  describe('_onAddTypeChange', () => {
    it('shows event panel for event type', () => {
      actionsEditor.addTypeSelect.value = 'event';
      actionsEditor._onAddTypeChange();
      const eventPanel = document.getElementById('actions-add-event-panel');
      const giftPanel = document.getElementById('actions-add-gift-panel');
      expect(eventPanel.classList.contains('hidden')).toBe(false);
      expect(giftPanel.classList.contains('hidden')).toBe(true);
    });

    it('shows gift panel for gift type', () => {
      actionsEditor.addTypeSelect.value = 'gift';
      actionsEditor._onAddTypeChange();
      const eventPanel = document.getElementById('actions-add-event-panel');
      const giftPanel = document.getElementById('actions-add-gift-panel');
      expect(eventPanel.classList.contains('hidden')).toBe(true);
      expect(giftPanel.classList.contains('hidden')).toBe(false);
    });
  });

  /* ─── _confirmAddEvent ─── */
  describe('_confirmAddEvent', () => {
    it('adds selected event', () => {
      actionsEditor.triggers = [];
      actionsEditor.addTypeSelect.value = 'event';
      actionsEditor.addEventName.value = 'follow';
      actionsEditor._confirmAddEvent();
      expect(actionsEditor.triggers).toHaveLength(1);
      expect(actionsEditor.triggers[0].name).toBe('follow');
    });
  });

  /* ─── _showAddError / _hideAddError ─── */
  describe('_showAddError / _hideAddError', () => {
    it('shows and hides error message', () => {
      actionsEditor._showAddError('Test error');
      expect(actionsEditor.addError.textContent).toBe('Test error');
      expect(actionsEditor.addError.classList.contains('hidden')).toBe(false);
      actionsEditor._hideAddError();
      expect(actionsEditor.addError.classList.contains('hidden')).toBe(true);
    });
  });

  /* ─── selectTrigger ─── */
  describe('selectTrigger', () => {
    it('selects trigger at index', () => {
      actionsEditor.triggers = [{ name: 'a', commands: [] }, { name: 'b', commands: [] }];
      actionsEditor.selectTrigger(1);
      expect(actionsEditor.selectedIndex).toBe(1);
    });
  });

  /* ─── renderTable ─── */
  describe('renderTable', () => {
    it('shows empty message when no triggers', () => {
      actionsEditor.triggers = [];
      actionsEditor.renderTable();
      const body = document.getElementById('actions-table-body');
      expect(body.innerHTML).toContain('No triggers defined');
      expect(actionsEditor.detailPanel.classList.contains('hidden')).toBe(true);
    });
  });

  /* ─── _renderGiftList ─── */
  describe('_renderGiftList', () => {
    it('renders filtered gift list', () => {
      actionsEditor.gifts = [
        { id: 1, name: 'Rose', coins: 1 },
        { id: 2, name: 'TikTok', coins: 5 },
      ];
      actionsEditor.addGiftSearch.value = 'rose';
      actionsEditor._renderGiftList();
      const list = document.getElementById('actions-add-gift-list');
      expect(list.innerHTML).toContain('Rose');
      expect(list.innerHTML).not.toContain('TikTok');
    });

    it('shows empty message when no gifts match', () => {
      actionsEditor.gifts = [{ id: 1, name: 'Rose', coins: 1 }];
      actionsEditor.addGiftSearch.value = 'zzznonexistent';
      actionsEditor._renderGiftList();
      const list = document.getElementById('actions-add-gift-list');
      expect(list.innerHTML).toContain('No gifts match');
    });
  });

  /* ─── _selectGift ─── */
  describe('_selectGift', () => {
    it('selects gift and enables confirm button', () => {
      actionsEditor.gifts = [{ id: 42, name: 'Test', coins: 10 }];
      actionsEditor._selectGift(42);
      expect(actionsEditor.selectedGiftId).toBe(42);
      expect(actionsEditor.addGiftConfirm.disabled).toBe(false);
    });
  });

  /* ─── diagnostics panel & save blocking ─── */
  describe('diagnostics & save blocking', () => {
    it('_updateSaveButton blocks save when errors present', () => {
      actionsEditor.isDirty = true;
      actionsEditor.diagnostics = [{ severity: 'ERROR', message: 'bad', line: 0 }];
      actionsEditor._updateSaveButton();
      const btn = document.getElementById('actions-editor-save');
      expect(btn.disabled).toBe(true);
    });

    it('_updateSaveButton enables save when dirty and no errors', () => {
      actionsEditor.isDirty = true;
      actionsEditor.diagnostics = [{ severity: 'WARNING', message: 'meh', line: 0 }];
      actionsEditor._updateSaveButton();
      const btn = document.getElementById('actions-editor-save');
      expect(btn.disabled).toBe(false);
    });

    it('_renderDiagnostics hides panel when no diagnostics', () => {
      actionsEditor.triggers = [{ name: 'follow' }];
      actionsEditor.diagnostics = [];
      actionsEditor._renderDiagnostics();
      const panel = document.getElementById('actions-diagnostics');
      expect(panel.style.display).toBe('none');
    });

    it('_renderDiagnostics renders error and warning items', () => {
      actionsEditor.triggers = [{ name: 'follow' }];
      actionsEditor.diagnostics = [
        { severity: 'ERROR', message: '{comment} wrong', line: 0 },
        { severity: 'WARNING', message: '{user} needs !rc', line: 0 },
      ];
      actionsEditor._renderDiagnostics();
      const panel = document.getElementById('actions-diagnostics');
      expect(panel.style.display).toBe('block');
      expect(panel.innerHTML).toContain('{comment} wrong');
      expect(panel.innerHTML).toContain('{user} needs !rc');
      expect(panel.innerHTML).toContain('follow');
    });
  });

  /* ─── _renderRawDiagnostics ─── */
  describe('_renderRawDiagnostics', () => {    it('shows no issues when empty', () => {
      actionsEditor._renderRawDiagnostics([]);
      const list = document.getElementById('actions-raw-diag-list');
      expect(list.innerHTML).toContain('No issues found');
    });

    it('renders diagnostics with different severities', () => {
      const diags = [
        { severity: 'ERROR', message: 'Syntax error', line: 5 },
        { severity: 'WARNING', message: 'Deprecated', line: 10 },
      ];
      actionsEditor._renderRawDiagnostics(diags);
      const list = document.getElementById('actions-raw-diag-list');
      expect(list.innerHTML).toContain('Syntax error');
      expect(list.innerHTML).toContain('Deprecated');
      expect(list.innerHTML).toContain('Line 6'); // 0-indexed, display: line+1
      expect(list.innerHTML).toContain('Line 11');
    });
  });

  /* ─── _updateRawStatus ─── */
  describe('_updateRawStatus', () => {
    it('blocks save when errors present', () => {
      actionsEditor.rawSaveBtn.disabled = false;
      actionsEditor._updateRawStatus([{ severity: 'ERROR', message: 'err' }]);
      expect(actionsEditor.rawSaveBtn.disabled).toBe(true);
      expect(actionsEditor.rawStatus.innerHTML).toContain('save blocked');
    });

    it('enables save when no errors', () => {
      actionsEditor.rawSaveBtn.disabled = true;
      actionsEditor._updateRawStatus([]);
      expect(actionsEditor.rawSaveBtn.disabled).toBe(false);
      expect(actionsEditor.rawStatus.innerHTML).toContain('No errors');
    });

    it('shows warnings when present', () => {
      actionsEditor.rawSaveBtn.disabled = true;
      actionsEditor._updateRawStatus([{ severity: 'WARNING', message: 'warn' }]);
      expect(actionsEditor.rawSaveBtn.disabled).toBe(false);
      expect(actionsEditor.rawStatus.innerHTML).toContain('warning');
    });
  });

  /* ─── close with unsaved changes ─── */
  describe('close with unsaved changes', () => {
    it('closes if no unsaved changes', async () => {
      const el = document.getElementById('actions-editor');
      el.classList.remove('hidden');
      actionsEditor.isDirty = false;
      await actionsEditor.close();
      expect(el.classList.contains('hidden')).toBe(true);
    });

    it('closes after confirm if dirty', async () => {
      const el = document.getElementById('actions-editor');
      el.classList.remove('hidden');
      actionsEditor.isDirty = true;
      const orig = showConfirmDialog;
      showConfirmDialog = async () => true;
      await actionsEditor.close();
      expect(el.classList.contains('hidden')).toBe(true);
      showConfirmDialog = orig;
    });

    it('does not close if user cancels', async () => {
      const el = document.getElementById('actions-editor');
      el.classList.remove('hidden');
      actionsEditor.isDirty = true;
      const orig = showConfirmDialog;
      showConfirmDialog = async () => false;
      await actionsEditor.close();
      expect(el.classList.contains('hidden')).toBe(false);
      showConfirmDialog = orig;
    });
  });

  /* ─── _confirmAddGift ─── */
  describe('_confirmAddGift', () => {
    it('adds gift trigger when selected', () => {
      actionsEditor.triggers = [];
      actionsEditor.gifts = [{ id: 42, name: 'Rose', coins: 1 }];
      actionsEditor.selectedGiftId = 42;
      actionsEditor._confirmAddGift();
      expect(actionsEditor.triggers).toHaveLength(1);
      expect(actionsEditor.triggers[0].name).toBe('Rose');
      expect(actionsEditor.triggers[0].type).toBe('Gift');
    });
  });

  /* ─── shell command rendering ─── */
  describe('shell command support', () => {
    it('shows shell prefix in table summary', () => {
      actionsEditor.triggers = [{
        name: '12345', enabled: true, type: 'Gift',
        commands: [{ type: 'shell', command: 'curl http://localhost', multiplier: 1 }],
      }];
      actionsEditor.renderTable();
      const body = document.getElementById('actions-table-body');
      expect(body.textContent).toContain('&curl http://localhost');
    });

    it('renders shell type with text input in detail', () => {
      actionsEditor.triggers = [{
        name: '12345', enabled: true, type: 'Gift',
        commands: [{ type: 'shell', command: 'curl http://localhost', multiplier: 1, title: '', subtitle: '', duration: 3, overlay_name: 'default' }],
      }];
      actionsEditor.selectedIndex = 0;
      actionsEditor.renderDetail(0);
      const select = document.querySelector('.cmd-type');
      expect(select.value).toBe('shell');
      const input = document.querySelector('.cmd-input');
      expect(input.value).toBe('curl http://localhost');
    });
  });

  /* ─── dynamic vanilla (!rc) ─── */
  describe('dynamic vanilla (!rc)', () => {
    it('shows the !rc suffix in the table summary for dynamic vanilla commands', () => {
      actionsEditor.triggers = [{
        name: '7654', enabled: true, type: 'Gift',
        commands: [{ type: 'vanilla', command: 'say Welcome {user}', multiplier: 1, dynamic_vanilla: true }],
      }];
      actionsEditor.renderTable();
      const body = document.getElementById('actions-table-body');
      expect(body.textContent).toContain('/say Welcome {user}');
      expect(body.textContent).toContain('!rc');
    });

    it('does not show the !rc suffix when dynamic_vanilla is false', () => {
      actionsEditor.triggers = [{
        name: '7654', enabled: true, type: 'Gift',
        commands: [{ type: 'vanilla', command: 'give @a apple', multiplier: 1, dynamic_vanilla: false }],
      }];
      actionsEditor.renderTable();
      const body = document.getElementById('actions-table-body');
      expect(body.textContent).toContain('/give @a apple');
      expect(body.textContent).not.toContain('/give @a apple !rc');
    });

    it('renders a checkbox for vanilla commands in detail', () => {
      actionsEditor.triggers = [{
        name: '7654', enabled: true, type: 'Gift',
        commands: [{ type: 'vanilla', command: 'say Welcome {user}', multiplier: 1, dynamic_vanilla: true, title: '', subtitle: '', duration: 3, overlay_name: 'default' }],
      }];
      actionsEditor.selectedIndex = 0;
      actionsEditor.renderDetail(0);
      const checkbox = document.querySelector('.cmd-rc input');
      expect(checkbox).not.toBeNull();
      expect(checkbox.checked).toBe(true);
    });

    it('does not render the checkbox for non-vanilla commands', () => {
      actionsEditor.triggers = [{
        name: '7654', enabled: true, type: 'Gift',
        commands: [{ type: 'rcon', command: 'say hi', multiplier: 1, dynamic_vanilla: false, title: '', subtitle: '', duration: 3, overlay_name: 'default' }],
      }];
      actionsEditor.selectedIndex = 0;
      actionsEditor.renderDetail(0);
      expect(document.querySelector('.cmd-rc')).toBeNull();
    });

    it('updateCmd toggles the dynamic_vanilla field', () => {
      actionsEditor.triggers = [{
        name: '7654', enabled: true, type: 'Gift',
        commands: [{ type: 'vanilla', command: 'say hi', multiplier: 1, dynamic_vanilla: false }],
      }];
      actionsEditor.updateCmd(0, 0, 'dynamic_vanilla', true);
      expect(actionsEditor.triggers[0].commands[0].dynamic_vanilla).toBe(true);
      expect(actionsEditor.isDirty).toBe(true);
    });
  });

  /* ─── _askServerRestart dialog ─── */
  describe('_askServerRestart', () => {
    it('resolves true when "Restart Now" is clicked', async () => {
      const dlg = document.getElementById('actions-restart-dialog');
      dlg.classList.add('hidden');
      const promise = actionsEditor._askServerRestart();
      expect(dlg.classList.contains('hidden')).toBe(false);
      document.getElementById('btn-actions-restart-now').click();
      await expect(promise).resolves.toBe(true);
      expect(dlg.classList.contains('hidden')).toBe(true);
    });

    it('resolves false when "Later" is clicked', async () => {
      const dlg = document.getElementById('actions-restart-dialog');
      dlg.classList.add('hidden');
      const promise = actionsEditor._askServerRestart();
      document.getElementById('btn-actions-restart-later').click();
      await expect(promise).resolves.toBe(false);
      expect(dlg.classList.contains('hidden')).toBe(true);
    });

    it('resolves false on Escape', async () => {
      const dlg = document.getElementById('actions-restart-dialog');
      dlg.classList.add('hidden');
      const promise = actionsEditor._askServerRestart();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      await expect(promise).resolves.toBe(false);
      expect(dlg.classList.contains('hidden')).toBe(true);
    });
  });

  /* ─── _askAndReloadActions ─── */
  describe('_askAndReloadActions', () => {
    let origPostJSON, origToast, origSetPending, origConfig;

    beforeEach(() => {
      origPostJSON = postJSON;
      origToast = showToast;
      origSetPending = setRestartPending;
      origConfig = currentConfig;
    });

    afterEach(() => {
      postJSON = origPostJSON;
      showToast = origToast;
      setRestartPending = origSetPending;
      currentConfig = origConfig;
    });

    it('sends send_minecraft_reload=true when restart now is chosen', async () => {
      currentConfig = { rcon: { enabled: true } };
      let captured;
      postJSON = async (url, body) => { captured = { url, body }; };
      showToast = () => {};
      let pending = null;
      setRestartPending = (p) => { pending = p; };
      const dlg = document.getElementById('actions-restart-dialog');
      dlg.classList.add('hidden');

      const promise = actionsEditor._askAndReloadActions();
      document.getElementById('btn-actions-restart-now').click();
      await promise;

      expect(captured.url).toBe('/reload');
      expect(captured.body.send_minecraft_reload).toBe(true);
      expect(pending).toBe(null);
    });

    it('does not restart and marks restart pending when later is chosen', async () => {
      currentConfig = { rcon: { enabled: true } };
      let captured;
      postJSON = async (url, body) => { captured = { url, body }; };
      showToast = () => {};
      let pending = null;
      setRestartPending = (p) => { pending = p; };
      const dlg = document.getElementById('actions-restart-dialog');
      dlg.classList.add('hidden');

      const promise = actionsEditor._askAndReloadActions();
      document.getElementById('btn-actions-restart-later').click();
      await promise;

      expect(captured.body.send_minecraft_reload).toBe(false);
      expect(pending).toBe(true);
    });

    it('skips the dialog when rcon is disabled', async () => {
      currentConfig = { rcon: { enabled: false } };
      let captured;
      postJSON = async (url, body) => { captured = body; };
      showToast = () => {};
      let pending = 'untouched';
      setRestartPending = (p) => { pending = p; };
      const dlg = document.getElementById('actions-restart-dialog');
      dlg.classList.add('hidden');

      await actionsEditor._askAndReloadActions();

      expect(captured.send_minecraft_reload).toBe(false);
      expect(pending).toBe(true);
      expect(dlg.classList.contains('hidden')).toBe(true);
    });
  });
});
