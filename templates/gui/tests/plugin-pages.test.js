import { describe, it, expect, beforeEach } from 'vitest';

/* ─── Plugin dashboard pages (manifest dashboard_ui) ─── */
describe('renderPluginPagesNav', () => {
  beforeEach(() => {
    currentPlugins = [];
    renderPluginPagesNav();
  });

  const plugin = (over = {}) => ({
    name: 'death-counter',
    display_name: 'Death Counter',
    enabled: true,
    dashboard_ui: true,
    ...over,
  });

  it('creates a nav item and view for plugins with dashboard_ui', () => {
    currentPlugins = [plugin()];
    renderPluginPagesNav();

    const navItem = document.querySelector('.nav-item[data-view="plugindash-death-counter"]');
    expect(navItem).not.toBeNull();
    expect(navItem.getAttribute('data-plugin-page')).toBe('1');
    expect(navItem.textContent).toContain('Death Counter');

    const view = document.getElementById('view-plugindash-death-counter');
    expect(view).not.toBeNull();
    expect(view.classList.contains('view')).toBe(true);
    const frame = view.querySelector('iframe.plugin-page-frame');
    expect(frame).not.toBeNull();
    expect(frame.dataset.src).toContain('/api/v1/plugins/death-counter/dashboard');
  });

  it('skips disabled plugins and plugins without dashboard_ui', () => {
    currentPlugins = [
      plugin({ enabled: false }),
      plugin({ name: 'timer', display_name: 'Timer', dashboard_ui: false }),
    ];
    renderPluginPagesNav();

    expect(document.querySelector('.nav-item[data-view="plugindash-death-counter"]')).toBeNull();
    expect(document.querySelector('.nav-item[data-view="plugindash-timer"]')).toBeNull();
  });

  it('removes stale entries on re-render', () => {
    currentPlugins = [plugin()];
    renderPluginPagesNav();
    expect(document.querySelectorAll('.nav-item[data-plugin-page]').length).toBe(1);

    currentPlugins = [];
    renderPluginPagesNav();
    expect(document.querySelectorAll('.nav-item[data-plugin-page]').length).toBe(0);
    expect(document.querySelectorAll('.view[data-plugin-page]').length).toBe(0);
    expect(document.getElementById('view-plugindash-death-counter')).toBeNull();
  });

  it('keeps DOM untouched when the page set is unchanged', () => {
    currentPlugins = [plugin()];
    renderPluginPagesNav();
    const view = document.getElementById('view-plugindash-death-counter');
    const navItem = document.querySelector('.nav-item[data-view="plugindash-death-counter"]');
    view.classList.add('active');
    navItem.classList.add('active');

    renderPluginPagesNav(); // periodic loadPlugins() poll with same data

    expect(document.getElementById('view-plugindash-death-counter')).toBe(view);
    expect(view.classList.contains('active')).toBe(true);
    expect(navItem.classList.contains('active')).toBe(true);
  });

  it('restores the active tab after a real rebuild', () => {
    currentPlugins = [plugin()];
    renderPluginPagesNav();
    openPluginDashboard('death-counter');

    currentPlugins = [
      plugin(),
      { name: 'timer', display_name: 'Timer', enabled: true, dashboard_ui: true },
    ];
    renderPluginPagesNav();

    expect(
      document.querySelector('.nav-item[data-view="plugindash-death-counter"]').classList.contains('active')
    ).toBe(true);
    expect(document.getElementById('view-plugindash-death-counter').classList.contains('active')).toBe(true);
    expect(frameSrcOf('view-plugindash-death-counter')).toContain('/api/v1/plugins/death-counter/dashboard');
  });

  function frameSrcOf(viewId) {
    return document.querySelector(`#${viewId} iframe`).src;
  }
});

describe('openPluginDashboard', () => {
  beforeEach(() => {
    currentPlugins = [
      { name: 'death-counter', display_name: 'Death Counter', enabled: true, dashboard_ui: true },
    ];
    document.querySelectorAll('.view.active').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item.active').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item[data-plugin-page]').forEach(el => el.remove());
    document.querySelectorAll('.view[data-plugin-page]').forEach(el => el.remove());
    renderPluginPagesNav();
  });

  it('lazy-loads the iframe src and activates the view + nav item', () => {
    const frame = document.querySelector('#view-plugindash-death-counter iframe');
    expect(frame.src).toBe('');

    openPluginDashboard('death-counter');

    expect(frame.src).toContain('/api/v1/plugins/death-counter/dashboard');
    expect(document.getElementById('view-plugindash-death-counter').classList.contains('active')).toBe(true);
    expect(
      document.querySelector('.nav-item[data-view="plugindash-death-counter"]').classList.contains('active')
    ).toBe(true);
  });

  it('does nothing for unknown plugin pages', () => {
    expect(() => openPluginDashboard('nope')).not.toThrow();
    expect(document.querySelector('.view.active[data-plugin-page]')).toBeNull();
  });
});
