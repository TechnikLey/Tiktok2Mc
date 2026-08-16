import { describe, it, expect, beforeEach } from 'vitest';

describe('LiveLog preferences', () => {
  beforeEach(() => {
    localStorage.clear();
    I18N.setLang('en');
  });

  it('persists the selected filter level', () => {
    window.liveLog.setFilter('error');
    expect(localStorage.getItem('tiktok2mc_log_filter')).toBe('error');
  });

  it('marks the matching filter button as active', () => {
    window.liveLog.setFilter('debug');
    const active = document.querySelector('#log-filter-buttons .log-filter-btn.active');
    expect(active.getAttribute('data-level')).toBe('debug');
  });

  it('restores the saved filter via _restorePrefs', () => {
    localStorage.setItem('tiktok2mc_log_filter', 'warning');
    window.liveLog._restorePrefs();
    expect(window.liveLog.filter).toBe('warning');
    const active = document.querySelector('#log-filter-buttons .log-filter-btn.active');
    expect(active.getAttribute('data-level')).toBe('warning');
  });

  it('ignores an invalid saved filter level', () => {
    localStorage.setItem('tiktok2mc_log_filter', 'bogus');
    window.liveLog.filter = 'all';
    window.liveLog._restorePrefs();
    expect(window.liveLog.filter).toBe('all');
  });

  it('persists the autoscroll checkbox state', () => {
    const cb = document.getElementById('log-autoscroll');
    cb.checked = false;
    cb.dispatchEvent(new Event('change', { bubbles: true }));
    expect(localStorage.getItem('tiktok2mc_log_autoscroll')).toBe('false');
    cb.checked = true;
    cb.dispatchEvent(new Event('change', { bubbles: true }));
    expect(localStorage.getItem('tiktok2mc_log_autoscroll')).toBe('true');
  });

  it('restores the saved autoscroll state', () => {
    localStorage.setItem('tiktok2mc_log_autoscroll', 'false');
    window.liveLog._restorePrefs();
    expect(document.getElementById('log-autoscroll').checked).toBe(false);
  });
});
