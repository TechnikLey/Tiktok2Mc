import { describe, it, expect, beforeEach } from 'vitest';

describe('Status density toggle', () => {
  beforeEach(() => {
    localStorage.clear();
    I18N.setLang('en');
  });

  it('switches to compact mode and persists it', () => {
    window.setStatusDensity('compact');
    expect(document.getElementById('view-status').classList.contains('density-compact')).toBe(true);
    expect(localStorage.getItem('tiktok2mc_status_density')).toBe('compact');
    const active = document.querySelector('.density-btn.active');
    expect(active.getAttribute('data-density')).toBe('compact');
  });

  it('switches back to spacious mode', () => {
    window.setStatusDensity('compact');
    window.setStatusDensity('spacious');
    expect(document.getElementById('view-status').classList.contains('density-compact')).toBe(false);
    expect(localStorage.getItem('tiktok2mc_status_density')).toBe('spacious');
  });

  it('initializes from localStorage', () => {
    localStorage.setItem('tiktok2mc_status_density', 'compact');
    window._initStatusDensity();
    expect(document.getElementById('view-status').classList.contains('density-compact')).toBe(true);
    const active = document.querySelector('.density-btn.active');
    expect(active.getAttribute('data-density')).toBe('compact');
  });

  it('falls back to spacious for invalid values', () => {
    localStorage.setItem('tiktok2mc_status_density', 'bogus');
    window._initStatusDensity();
    expect(document.getElementById('view-status').classList.contains('density-compact')).toBe(false);
  });
});
