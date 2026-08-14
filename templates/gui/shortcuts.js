/* ─── Global Keyboard Shortcuts ───
 * Ctrl+S   Save changes in the active editor
 * /        Focus the search field of the current view
 * Esc      Close the topmost dialog / overlay
 * ?        Open the shortcut reference (help topic "shortcuts")
 *
 * Shortcuts never fire while the user is typing in an input field, unless the
 * binding is explicitly marked `whenTyping` (Ctrl+S and Esc are the only ones).
 */
const Shortcuts = (() => {
  const _bindings = [];

  /* ── helpers ── */

  function _el(id) {
    return document.getElementById(id);
  }

  function _elHidden(id) {
    const el = _el(id);
    return !el || el.classList.contains('hidden');
  }

  function _isTyping(e) {
    const t = e.target;
    if (!t || !t.tagName) return false;
    const tag = t.tagName.toUpperCase();
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t.isContentEditable;
  }

  function _keyName(e) {
    if (e.key === 'Escape') return 'escape';
    if (e.key === '?') return '?';
    if (e.key === '/') return '/';
    if (e.key.length === 1) return e.key.toLowerCase();
    return e.key.toLowerCase();
  }

  function _comboParts(combo) {
    return combo.split('+').map(p => p.toLowerCase());
  }

  function _matches(e, parts) {
    const wantCtrl = parts.includes('ctrl');
    const wantShift = parts.includes('shift');
    const wantAlt = parts.includes('alt');
    const key = parts[parts.length - 1];
    if (wantCtrl !== (e.ctrlKey || e.metaKey)) return false;
    if (wantShift !== e.shiftKey) return false;
    if (wantAlt !== e.altKey) return false;
    return _keyName(e) === key;
  }

  function _anyModalOpen() {
    return !!document.querySelector('.wizard-overlay:not(.hidden)');
  }

  function _click(id) {
    const el = _el(id);
    if (el) el.click();
  }

  /* ── bindings API ── */

  function bind(combo, run, opts = {}) {
    _bindings.push({
      combo,
      parts: _comboParts(combo),
      run,
      descKey: opts.descKey || '',
      whenTyping: !!opts.whenTyping,
    });
  }

  function list() {
    return _bindings.map(b => ({ combo: b.combo, descKey: b.descKey }));
  }

  /* ── actions ── */

  function saveActiveEditor() {
    if (_anyModalOpen()) return;
    const targets = [
      ['config-editor', () => editor.save()],
      ['plugin-config-editor', () => pluginEditor.save()],
      ['plugins-config-section', () => pluginEditor.save()],
      ['hooks-config-section', () => hookEditor.save()],
      ['reaction-editor', () => reactionEditor.save()],
      ['actions-editor', () => actionsEditor.save()],
    ];
    for (const [id, run] of targets) {
      if (!_elHidden(id)) {
        run();
        return;
      }
    }
  }

  function focusSearch() {
    const editorMap = [
      ['config-editor', 'editor-search'],
      ['plugin-config-editor', 'plugin-editor-search'],
      ['plugins-config-section', 'plugins-config-search'],
      ['hooks-config-section', 'hooks-config-search'],
      ['reaction-editor', 'reaction-search'],
    ];
    for (const [overlay, id] of editorMap) {
      if (!_elHidden(overlay)) {
        const el = _el(id);
        if (el) {
          el.focus();
          if (el.select) el.select();
          return;
        }
      }
    }
    const view = document.querySelector('.view.active');
    if (!view || !view.id) return;
    const viewSearch = {
      'view-log': 'log-search',
      'view-triggers': 'gift-search',
      'view-console': 'console-input',
    };
    const id = viewSearch[view.id];
    if (!id) return;
    const el = _el(id);
    if (el) {
      el.focus();
      if (el.select) el.select();
    }
  }

  /* ── modal closing (Esc) ──
   * Topmost first. Modals that force a decision (unsaved-changes-modal) are
   * intentionally absent so Esc cannot dismiss them.
   */
  const _modalProviders = [
    { name: 'help', isOpen: () => !!window.Help && Help.isOpen(), close: () => Help.closeHelp() },
    { name: 'server-create', isOpen: () => !_elHidden('server-create-modal'), close: () => closeServerCreateModal() },
    { name: 'server-download', isOpen: () => !_elHidden('server-download-modal'), close: () => closeServerDownloadModal() },
    { name: 'server-switch', isOpen: () => !_elHidden('server-switch-modal'), close: () => closeServerSwitchModal() },
    { name: 'server-custom', isOpen: () => !_elHidden('server-custom-modal'), close: () => closeServerCustomModal() },
    { name: 'actions-add', isOpen: () => !_elHidden('actions-add-modal'), close: () => actionsEditor._closeAddModal() },
    { name: 'reaction-delete', isOpen: () => !_elHidden('reaction-delete-modal'), close: () => _click('reaction-delete-cancel') },
    { name: 'reaction-wizard', isOpen: () => !_elHidden('reaction-wizard'), close: () => _click('reaction-wizard-cancel') },
    { name: 'plugin-review', isOpen: () => !_elHidden('plugin-review-modal'), close: () => pluginEditor.hideReview() },
    { name: 'hook-review', isOpen: () => !_elHidden('hook-review-modal'), close: () => hookEditor.hideReview() },
    { name: 'review', isOpen: () => !_elHidden('review-modal'), close: () => editor.hideReview() },
    { name: 'advanced', isOpen: () => !_elHidden('advanced-confirm-dialog'), close: () => _click('advanced-confirm-cancel') },
  ];

  function _closeTopModal() {
    for (const p of _modalProviders) {
      if (p.isOpen()) {
        p.close();
        return;
      }
    }
    const active = document.activeElement;
    if (active && active.blur && active.tagName) active.blur();
  }

  /* ── keydown dispatch ── */

  function _handleKeydown(e) {
    for (const b of _bindings) {
      if (!_matches(e, b.parts)) continue;
      if (!b.whenTyping && _isTyping(e)) continue;
      e.preventDefault();
      b.run(e);
      return;
    }
  }

  /* ── default bindings ── */

  bind('ctrl+s', saveActiveEditor, { whenTyping: true, descKey: 'shortcuts.save' });
  bind('/', focusSearch, { descKey: 'shortcuts.search' });
  bind('escape', _closeTopModal, { whenTyping: true, descKey: 'shortcuts.close' });
  bind('shift+?', () => { if (window.Help) Help.openHelp('shortcuts'); }, { descKey: 'shortcuts.help' });

  function install() {
    document.addEventListener('keydown', _handleKeydown);
  }

  install();

  return {
    install,
    bind,
    list,
    saveActiveEditor,
    focusSearch,
    _closeTopModal,
  };
})();
