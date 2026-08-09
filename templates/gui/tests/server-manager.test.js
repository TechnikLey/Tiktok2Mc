import { describe, it, expect, beforeEach } from 'vitest';

function renderServerCard(inst) {
  return window.renderServerCard(inst);
}

function parseCard(html) {
  const wrapper = document.createElement('div');
  wrapper.innerHTML = html;
  return wrapper.firstElementChild;
}

describe('renderServerCard', () => {
  beforeEach(() => {
    window._serverManagerCache = {
      instances: [],
      installed: [],
      safe_versions: ['1.21.11'],
    };
  });

  it('renders a normal card with version for an installed instance', () => {
    const card = parseCard(renderServerCard({
      id: 'default', name: 'Default Server', version: '1.21.11',
      port: 25565, status: 'stopped', path: 'server/default', hasJar: true,
    }));
    expect(card.getAttribute('data-instance-not-installed')).toBeNull();
    expect(card.textContent).toContain('1.21.11');
    expect(card.textContent).not.toContain('server.jar missing');
    const startBtn = card.querySelector('.btn--success');
    expect(startBtn.disabled).toBe(false);
  });

  it('shows a not-installed state when server.jar is missing', () => {
    const card = parseCard(renderServerCard({
      id: 'default', name: 'Default Server', version: '1.21.11',
      port: 25565, status: 'stopped', path: 'server/default', hasJar: false,
    }));
    expect(card.getAttribute('data-instance-not-installed')).toBe('1');
    expect(card.textContent).not.toContain('1.21.11');
    expect(card.textContent).toContain('Not installed');
    expect(card.textContent).toContain('MISSING');
    expect(card.textContent).toContain('server.jar missing');
    const startBtn = card.querySelector('.btn--success');
    expect(startBtn.disabled).toBe(true);
  });
});

describe('openServerSwitchModal', () => {
  beforeEach(() => {
    window._serverManagerCache = {
      instances: [],
      installed: [
        { version: '1.21.11', type: 'safe', path: 'versions/1.21.11' },
        { version: '1.20.4', type: 'unsafe', path: 'versions/1.20.4' },
      ],
      safe_versions: ['1.21.11'],
      current_version: '1.21.11',
    };
  });

  function switchList() {
    return document.getElementById('server-switch-list');
  }

  it('marks the current version as active and not clickable', () => {
    openServerSwitchModal();
    const list = switchList();
    const cards = list.querySelectorAll('.version-card');
    expect(cards.length).toBe(2);

    const current = list.querySelector('.version-card--active');
    expect(current).not.toBeNull();
    expect(current.textContent).toContain('CURRENT');
    expect(current.textContent).toContain('Active version');
    expect(current.getAttribute('onclick')).toBeNull();

    const switchable = Array.from(cards).filter(c => !c.classList.contains('version-card--active'));
    expect(switchable.length).toBe(1);
    expect(switchable[0].getAttribute('onclick')).toContain('serverManagerPromptSwitch');
    expect(switchable[0].textContent).toContain('Click to switch');
  });

  it('renders all cards clickable when no current version is known', () => {
    window._serverManagerCache.current_version = null;
    openServerSwitchModal();
    const cards = switchList().querySelectorAll('.version-card');
    expect(cards.length).toBe(2);
    expect(switchList().querySelector('.version-card--active')).toBeNull();
    Array.from(cards).forEach(c => {
      expect(c.getAttribute('onclick')).toContain('serverManagerPromptSwitch');
    });
  });
});

describe('renderJavaStatusBanner', () => {
  function bannerEl() {
    return document.getElementById('java-status-banner');
  }

  it('hides the banner when Java is available', () => {
    renderJavaStatusBanner({ ok: true });
    expect(bannerEl().classList.contains('hidden')).toBe(true);
    expect(bannerEl().innerHTML).toBe('');
  });

  it('shows a warning with an install button when Java is missing and installable', () => {
    renderJavaStatusBanner({
      ok: false,
      reason: 'No Java installation was found.',
      minJavaVersion: 17,
      hints: ['sudo apt install -y openjdk-21-jre-headless'],
      autoInstallable: true,
      install: { message: '', done: false, ok: false },
    });
    expect(bannerEl().classList.contains('hidden')).toBe(false);
    expect(bannerEl().textContent).toContain('Java runtime missing');
    expect(bannerEl().textContent).toContain('sudo apt install -y openjdk-21-jre-headless');
    expect(bannerEl().querySelector('#java-install-btn')).not.toBeNull();
  });

  it('omits the install button when auto-install is not supported', () => {
    renderJavaStatusBanner({
      ok: false,
      reason: 'No Java installation was found.',
      minJavaVersion: 17,
      hints: [],
      autoInstallable: false,
      install: { message: '', done: false, ok: false },
    });
    expect(bannerEl().classList.contains('hidden')).toBe(false);
    expect(bannerEl().querySelector('#java-install-btn')).toBeNull();
  });
});
