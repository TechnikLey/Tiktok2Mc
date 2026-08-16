import { describe, it, expect, beforeEach, afterEach } from 'vitest';

const MODAL_IDS = [
  'wizard', 'help-modal', 'confirm-dialog', 'server-create-modal', 'server-download-modal',
  'server-switch-modal', 'server-custom-modal', 'actions-add-modal',
  'reaction-delete-modal', 'reaction-wizard', 'plugin-review-modal',
  'hook-review-modal', 'review-modal', 'advanced-confirm-dialog',
  'unsaved-changes-modal', 'shutdown-overlay',
];

function resetAll() {
  for (const id of MODAL_IDS) {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  }
  document.querySelectorAll('.editor-overlay').forEach(el => el.classList.add('hidden'));
}

function flush() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

function fire(key, init = {}) {
  const ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init });
  document.dispatchEvent(ev);
  return ev;
}

describe('ModalFocus (accessibility.js)', () => {
  beforeEach(() => {
    resetAll();
    I18N.setLang('en');
  });

  afterEach(() => {
    resetAll();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
  });

  it('exposes the ModalFocus API', () => {
    expect(window.ModalFocus).toBeDefined();
    expect(typeof ModalFocus.install).toBe('function');
  });

  it('marks an opened wizard overlay as a labelled dialog and focuses its first control', async () => {
    const modal = document.getElementById('help-modal');
    modal.classList.remove('hidden');
    await flush();
    expect(modal.getAttribute('role')).toBe('dialog');
    expect(modal.getAttribute('aria-modal')).toBe('true');
    expect(modal.getAttribute('aria-labelledby')).toBe('help-modal-title');
    expect(document.activeElement.id).toBe('help-modal-close');
  });

  it('generates an aria-labelledby id when the heading has none', async () => {
    const modal = document.getElementById('confirm-dialog');
    const heading = modal.querySelector('h2');
    heading.removeAttribute('id');
    modal.classList.remove('hidden');
    await flush();
    const labelId = modal.getAttribute('aria-labelledby');
    expect(labelId).toBeTruthy();
    expect(heading.id).toBe(labelId);
  });

  it('marks opened editor overlays as dialogs too', async () => {
    const overlay = document.getElementById('config-editor');
    overlay.classList.remove('hidden');
    await flush();
    expect(overlay.getAttribute('role')).toBe('dialog');
    expect(overlay.getAttribute('aria-modal')).toBe('true');
  });

  it('restores focus to the trigger when the modal closes', async () => {
    const trigger = document.querySelector('.theme-toggle');
    trigger.focus();
    const modal = document.getElementById('help-modal');
    modal.classList.remove('hidden');
    await flush();
    expect(document.activeElement).not.toBe(trigger);
    modal.classList.add('hidden');
    await flush();
    expect(document.activeElement).toBe(trigger);
  });

  it('does not restore focus to a detached trigger', async () => {
    const trigger = document.createElement('button');
    trigger.id = 'a11y-trigger';
    document.body.appendChild(trigger);
    trigger.focus();
    const modal = document.getElementById('help-modal');
    modal.classList.remove('hidden');
    await flush();
    expect(document.activeElement).not.toBe(trigger);
    trigger.remove();
    modal.classList.add('hidden');
    await flush();
    expect(document.activeElement).not.toBe(trigger);
  });

  it('traps Tab inside the topmost open modal (last wraps to first)', async () => {
    const modal = document.getElementById('actions-add-modal');
    modal.classList.remove('hidden');
    await flush();
    expect(document.activeElement.id).toBe('actions-add-type');
    document.getElementById('actions-add-event-confirm').focus();
    const ev = fire('Tab');
    await flush();
    expect(document.activeElement.id).toBe('actions-add-type');
    expect(ev.defaultPrevented).toBe(true);
  });

  it('traps Shift+Tab inside the modal (first wraps to last)', async () => {
    const modal = document.getElementById('actions-add-modal');
    modal.classList.remove('hidden');
    await flush();
    document.getElementById('actions-add-type').focus();
    const ev = fire('Tab', { shiftKey: true });
    await flush();
    expect(document.activeElement.id).toBe('actions-add-event-confirm');
    expect(ev.defaultPrevented).toBe(true);
  });

  it('leaves Tab alone when no modal is open', async () => {
    const btn = document.querySelector('.theme-toggle');
    btn.focus();
    const ev = fire('Tab');
    expect(ev.defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(btn);
  });

  it('skips focusables hidden inside a collapsible panel', async () => {
    const modal = document.getElementById('actions-add-modal');
    document.getElementById('actions-add-gift-panel').classList.remove('hidden');
    modal.classList.remove('hidden');
    await flush();
    // The first focusable must still be the type select (gift inputs come later)
    expect(document.activeElement.id).toBe('actions-add-type');
  });
});

describe('Toasts', () => {
  beforeEach(() => {
    document.getElementById('toast-container').innerHTML = '';
  });

  afterEach(() => {
    document.getElementById('toast-container').innerHTML = '';
  });

  it('announces info/success toasts as status', () => {
    showToast('hello');
    const toast = document.querySelector('#toast-container .toast');
    expect(toast.getAttribute('role')).toBe('status');
  });

  it('announces error/warning toasts as alerts', () => {
    showToast('oops', 'error');
    let toast = document.querySelector('#toast-container .toast');
    expect(toast.getAttribute('role')).toBe('alert');
    toast.remove();
    showToast('careful', 'warning');
    toast = document.querySelector('#toast-container .toast');
    expect(toast.getAttribute('role')).toBe('alert');
  });
});

describe('Keyboard-accessible sidebar', () => {
  beforeEach(() => {
    resetAll();
    I18N.setLang('en');
  });

  afterEach(() => {
    resetAll();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
  });

  it('renders the main nav items as buttons', () => {
    const items = document.querySelectorAll('.sidebar-nav .nav-item');
    expect(items.length).toBeGreaterThan(0);
    items.forEach(item => expect(item.tagName).toBe('BUTTON'));
  });

  it('labels the icon-only controls with aria-labels', () => {
    const toggles = [
      '.sidebar-toggle',
      '.sidebar-hide-btn',
      '.sidebar-reveal',
      '.theme-toggle',
      '.mobile-menu-btn',
    ];
    for (const sel of toggles) {
      const el = document.querySelector(sel);
      if (!el) continue;
      expect(el.getAttribute('aria-label')).toBeTruthy();
    }
  });
});

describe('Mobile drawer sidebar', () => {
  beforeEach(() => {
    resetAll();
    I18N.setLang('en');
    document.querySelector('.sidebar')?.classList.remove('mobile-open');
    document.getElementById('sidebar-backdrop')?.classList.remove('open');
    document.querySelector('.mobile-menu-btn')?.setAttribute('aria-expanded', 'false');
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 375 });
  });

  afterEach(() => {
    resetAll();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
  });

  it('opens the drawer and updates the backdrop + button state', () => {
    toggleMobileSidebar();
    const sidebar = document.querySelector('.sidebar');
    expect(sidebar.classList.contains('mobile-open')).toBe(true);
    expect(document.getElementById('sidebar-backdrop').classList.contains('open')).toBe(true);
    expect(document.querySelector('.mobile-menu-btn').getAttribute('aria-expanded')).toBe('true');
  });

  it('closes the drawer on Esc', () => {
    toggleMobileSidebar();
    expect(document.querySelector('.sidebar').classList.contains('mobile-open')).toBe(true);
    fire('Escape');
    expect(document.querySelector('.sidebar').classList.contains('mobile-open')).toBe(false);
    expect(document.getElementById('sidebar-backdrop').classList.contains('open')).toBe(false);
    expect(document.querySelector('.mobile-menu-btn').getAttribute('aria-expanded')).toBe('false');
  });

  it('closes the drawer when the window grows past the mobile breakpoint', () => {
    toggleMobileSidebar();
    expect(document.querySelector('.sidebar').classList.contains('mobile-open')).toBe(true);
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 });
    window.dispatchEvent(new Event('resize'));
    expect(document.querySelector('.sidebar').classList.contains('mobile-open')).toBe(false);
  });
});
