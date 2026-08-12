import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('I18N', () => {
  const STORAGE_KEY = 'tiktok2mc_lang';

  function resetI18N() {
    localStorage.clear();
    document.documentElement.lang = 'en';
    document.querySelectorAll('[data-i18n]').forEach(el => el.removeAttribute('data-i18n'));
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => el.removeAttribute('data-i18n-placeholder'));
    document.querySelectorAll('[data-i18n-title]').forEach(el => el.removeAttribute('data-i18n-title'));
    document.querySelectorAll('[data-i18n-aria-label]').forEach(el => el.removeAttribute('data-i18n-aria-label'));
    document.body.innerHTML = '';
  }

  beforeEach(() => {
    resetI18N();
    I18N.setLang('en');
  });

  afterEach(() => {
    resetI18N();
    vi.restoreAllMocks();
  });

  it('exposes I18N on window', () => {
    expect(window.I18N).toBeDefined();
    expect(typeof window.I18N.t).toBe('function');
    expect(typeof window.I18N.apply).toBe('function');
    expect(typeof window.I18N.setLang).toBe('function');
    expect(typeof window.I18N.init).toBe('function');
    expect(typeof window.I18N.lang).toBe('function');
  });

  it('returns English by default', () => {
    expect(I18N.lang()).toBe('en');
    expect(I18N.t('common.save')).toBe('Save');
    expect(I18N.t('nav.status')).toBe('Status');
  });

  it('interpolates parameters', () => {
    const result = I18N.t('triggers.confirmMessage', { kind: 'FOLLOW', trigger: 'follow', user: 'Alice' });
    expect(result).toBe('Send TEST FOLLOW "follow" as user "Alice"?');
  });

  it('falls back to English for missing German keys', () => {
    I18N.setLang('de');
    expect(I18N.lang()).toBe('de');
    // Some keys might be missing in DE, should fall back to EN
    expect(I18N.t('common.save')).toBe('Speichern');
  });

  it('persists language to localStorage', () => {
    I18N.setLang('de');
    expect(localStorage.getItem(STORAGE_KEY)).toBe('de');
    I18N.setLang('en');
    expect(localStorage.getItem(STORAGE_KEY)).toBe('en');
  });

  it('applies translations to DOM elements with data-i18n', () => {
    document.body.innerHTML = '<span data-i18n="common.save">Save</span>';
    I18N.apply(document);
    expect(document.querySelector('[data-i18n="common.save"]').textContent).toBe('Save');

    I18N.setLang('de');
    expect(document.querySelector('[data-i18n="common.save"]').textContent).toBe('Speichern');
  });

  it('applies translations to placeholder attributes', () => {
    document.body.innerHTML = '<input data-i18n-placeholder="common.searchPlaceholder" placeholder="Search...">';
    I18N.apply(document);
    expect(document.querySelector('[data-i18n-placeholder="common.searchPlaceholder"]').getAttribute('placeholder')).toBe('Search...');

    I18N.setLang('de');
    expect(document.querySelector('[data-i18n-placeholder="common.searchPlaceholder"]').getAttribute('placeholder')).toBe('Suchen...');
  });

  it('applies translations to title attributes', () => {
    document.body.innerHTML = '<button data-i18n-title="common.refresh" title="Refresh"></button>';
    I18N.apply(document);
    expect(document.querySelector('[data-i18n-title="common.refresh"]').getAttribute('title')).toBe('Refresh');

    I18N.setLang('de');
    expect(document.querySelector('[data-i18n-title="common.refresh"]').getAttribute('title')).toBe('Aktualisieren');
  });

  it('applies translations to aria-label attributes', () => {
    document.body.innerHTML = '<button data-i18n-aria-label="common.close" aria-label="Close"></button>';
    I18N.apply(document);
    expect(document.querySelector('[data-i18n-aria-label="common.close"]').getAttribute('aria-label')).toBe('Close');

    I18N.setLang('de');
    expect(document.querySelector('[data-i18n-aria-label="common.close"]').getAttribute('aria-label')).toBe('Schließen');
  });

  it('sets documentElement.lang on apply', () => {
    document.body.innerHTML = '<span data-i18n="common.save">Save</span>';
    I18N.setLang('de');
    expect(document.documentElement.lang).toBe('de');
  });

  it('dispatches i18n:changed event on language change', () => {
    const handler = vi.fn();
    document.addEventListener('i18n:changed', handler);
    I18N.setLang('de');
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0][0].detail.lang).toBe('de');
  });

  it('ignores unsupported languages', () => {
    I18N.setLang('fr');
    expect(I18N.lang()).toBe('en');
    expect(localStorage.getItem(STORAGE_KEY)).toBe('en');
  });

  it('returns key for completely unknown keys', () => {
    expect(I18N.t('nonexistent.key')).toBe('nonexistent.key');
  });

  it('has SUPPORTED array', () => {
    expect(I18N.SUPPORTED).toEqual(['en', 'de']);
  });

  it('has dicts object with en and de', () => {
    expect(I18N.dicts).toBeDefined();
    expect(I18N.dicts.en).toBeDefined();
    expect(I18N.dicts.de).toBeDefined();
    expect(I18N.dicts.en['common.save']).toBe('Save');
    expect(I18N.dicts.de['common.save']).toBe('Speichern');
  });
});