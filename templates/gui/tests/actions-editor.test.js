import { describe, it, expect, beforeEach } from 'vitest';

describe('ActionsEditor', () => {
  beforeEach(() => {
    actionsEditor.triggers = [];
    actionsEditor.selectedIndex = -1;
    actionsEditor.isDirty = false;
    actionsEditor.isDirty = false;
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

  /* ─── _renderRawDiagnostics ─── */
  describe('_renderRawDiagnostics', () => {
    it('shows no issues when empty', () => {
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
});
