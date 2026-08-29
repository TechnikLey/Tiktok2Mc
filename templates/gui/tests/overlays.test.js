import { describe, it, expect, beforeEach } from 'vitest';

let lastFetch;

describe('Overlay preview & test', () => {
  beforeEach(() => {
    I18N.setLang('en');
    currentConfig = { overlay: { overlays: [{ name: 'alerts' }] } };
    currentPlugins = [];
    document.getElementById('toast-container').innerHTML = '';
    globalThis.fetch = async (url, opts) => {
      lastFetch = { url, opts };
      return { ok: true, status: 200, statusText: 'OK', json: async () => ({}) };
    };
  });

  it('renders a preview card for every built-in overlay', () => {
    renderOverlayUrls();
    const items = document.querySelectorAll('#overlay-urls .overlay-item');
    expect(items.length).toBe(2);
    expect([...items].map(i => i.dataset.overlay)).toEqual(['default', 'alerts']);
    const previews = document.querySelectorAll('.overlay-preview');
    expect(previews.length).toBe(2);
    expect(previews[0].src).toContain('/api/v1/overlay?overlay=default&chroma=0');
    expect(previews[1].src).toContain('/api/v1/overlay?overlay=alerts&chroma=0');
  });

  it('adds a Test button only to built-in overlays', () => {
    renderOverlayUrls();
    const items = document.querySelectorAll('#overlay-urls .overlay-item');
    expect(items[0].querySelector('.btn-test')).not.toBeNull();
    expect(items[1].querySelector('.btn-test')).not.toBeNull();
    expect(document.querySelector('.btn-test').textContent).toBe('Test');
    expect(document.querySelector('[data-overlay="default"] .btn-test').getAttribute('onclick'))
      .toContain("testOverlay('default', this)");
  });

  it('encodes overlay names with special characters in the onclick handler', () => {
    currentConfig = { overlay: { overlays: [{ name: 'my overlay' }] } };
    renderOverlayUrls();
    const btn = document.querySelector('[data-overlay="my overlay"] .btn-test');
    expect(btn.getAttribute('onclick')).toContain("testOverlay('my%20overlay', this)");
  });

  it('renders plugin overlay previews without a Test button', () => {
    currentPlugins = [{ name: 'demoplugin', display_name: 'Demo Plugin', enabled: true, port: 8123 }];
    renderOverlayUrls();
    const items = document.querySelectorAll('#overlay-urls .overlay-item');
    expect(items.length).toBe(3); // default + alerts + demoplugin
    const pluginItem = items[2];
    expect(pluginItem.dataset.overlay).toBe('demoplugin');
    expect(pluginItem.querySelector('.btn-test')).toBeNull();
    expect(pluginItem.querySelector('.overlay-preview').src).toContain('http://localhost:8123/');
  });

  it('ignores disabled plugins without a port', () => {
    currentPlugins = [
      { name: 'off', display_name: 'Off', enabled: false, port: 8123 },
      { name: 'noport', display_name: 'No Port', enabled: true, port: 0 },
    ];
    renderOverlayUrls();
    const items = document.querySelectorAll('#overlay-urls .overlay-item');
    expect(items.length).toBe(2); // default + alerts only
  });

  it('uses i18n labels in German', () => {
    I18N.setLang('de');
    renderOverlayUrls();
    expect(document.querySelector('.btn-test').textContent).toBe('Testen');
    const sectionTitles = document.querySelectorAll('.overlay-section-title');
    expect(sectionTitles[0].textContent).toBe('Eingebautes Overlay');
  });

  it('posts a sample message to /overlay/display when Test is clicked', async () => {
    renderOverlayUrls();
    const btn = document.querySelector('[data-overlay="default"] .btn-test');
    await testOverlay('default', btn);
    expect(lastFetch.url).toContain('/api/v1/overlay/display');
    expect(lastFetch.opts.method).toBe('POST');
    const body = JSON.parse(lastFetch.opts.body);
    expect(body.overlay_name).toBe('default');
    expect(body.title).toBe('Test Message');
    expect(body.subtitle).toBe('This is a sample overlay message.');
    expect(body.duration).toBe(3);
    const toast = document.querySelector('#toast-container .toast');
    expect(toast.textContent).toContain('Test message sent to overlay "default".');
    expect(btn.disabled).toBe(false);
    expect(btn.textContent).toBe('Test');
  });

  it('re-enables the Test button and shows an error toast on failure', async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ detail: 'Overlay not found' }),
    });
    renderOverlayUrls();
    const btn = document.querySelector('[data-overlay="default"] .btn-test');
    await testOverlay('default', btn);
    expect(btn.disabled).toBe(false);
    expect(btn.textContent).toBe('Test');
    const toast = document.querySelector('#toast-container .toast');
    expect(toast.className).toContain('error');
  });

  it('sends the test to a named overlay', async () => {
    renderOverlayUrls();
    const btn = document.querySelector('[data-overlay="alerts"] .btn-test');
    await testOverlay('alerts', btn);
    const body = JSON.parse(lastFetch.opts.body);
    expect(body.overlay_name).toBe('alerts');
  });
});
