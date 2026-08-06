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
