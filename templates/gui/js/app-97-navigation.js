/**
 * @file Sidebar/navigation, view switching, theme and language controls.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */
/* ─── Sidebar ─── */
let _sidebarMode = 0;
const SIDEBAR_MODES = ['full', 'icons', 'hide'];
/** Apply a sidebar display mode and persist it. */
function _setSidebarMode(mode) {
  _sidebarMode = mode;
  const sidebar = document.querySelector('.sidebar');
  sidebar.classList.remove('full', 'icons', 'hide');
  sidebar.classList.add(SIDEBAR_MODES[_sidebarMode]);
  document.querySelector('.app-layout').classList.toggle('sidebar-hidden', _sidebarMode === 2);
}
/** Cycle through the sidebar display modes. */
function cycleSidebar() {
  // Toggle between full (0) and icons (1)
  _setSidebarMode(_sidebarMode === 0 ? 1 : 0);
}
/** Hide the sidebar completely. */
function hideSidebar() {
  _setSidebarMode(2);
}
/** Install the edge-reveal behaviour for a hidden sidebar. */
function _initSidebarReveal() {
  const reveal = document.querySelector('.sidebar-reveal');
  reveal?.addEventListener('click', () => {
    if (_sidebarMode === 2) _setSidebarMode(0);
  });
  document.querySelector('.app-layout')?.addEventListener('click', (e) => {
    if (_sidebarMode === 2 && e.clientX < 18) {
      _setSidebarMode(0);
    }
  });
}

/* ─── Mobile sidebar (off-canvas drawer) ─── */
/** Return whether the viewport is in the mobile breakpoint. */
function _isMobileWidth() {
  return window.innerWidth <= 768;
}

/** Toggle the mobile off-canvas sidebar. */
function toggleMobileSidebar() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  const open = sidebar.classList.toggle('mobile-open');
  document.getElementById('sidebar-backdrop')?.classList.toggle('open', open);
  document.querySelector('.mobile-menu-btn')?.setAttribute('aria-expanded', String(open));
  if (open) {
    const first = sidebar.querySelector('a[href], button, input, select, textarea, [tabindex]');
    if (first) first.focus();
  }
}

/** Close the mobile off-canvas sidebar. */
function closeMobileSidebar() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar || !sidebar.classList.contains('mobile-open')) return;
  sidebar.classList.remove('mobile-open');
  document.getElementById('sidebar-backdrop')?.classList.remove('open');
  document.querySelector('.mobile-menu-btn')?.setAttribute('aria-expanded', 'false');
}

/** Wire the mobile sidebar backdrop and accessibility state. */
function _initMobileSidebar() {
  document.getElementById('sidebar-backdrop')?.addEventListener('click', closeMobileSidebar);
  window.addEventListener('resize', () => {
    if (!_isMobileWidth()) closeMobileSidebar();
  });
}

/* ─── Editor helpers (show/hide editors within app-layout) ─── */
/** Hide every editor overlay and return to the dashboard. */
function _hideAllEditors() {
  document.querySelectorAll('.editor-overlay').forEach(el => el.classList.add('hidden'));
}

/** Synchronize dashboard visibility with the currently open editor. */
function _syncDashboardVisibility() {
  const anyOpen = document.querySelector('.editor-overlay:not(.hidden)');
  document.getElementById('dashboard').classList.toggle('dashboard-hidden', !!anyOpen);
  // Deactivate editor nav items when no editor is open
  if (!anyOpen) {
    document.querySelectorAll('.nav-item[data-view="actions"], .nav-item[data-view="reactions"], .nav-item[data-view="settings"], .nav-item[data-view="commands"], .nav-item[data-view="chatbot"]').forEach(el => el.classList.remove('active'));
  }
}

/** Install the observer that keeps dashboard visibility in sync with editor overlays. */
function _initEditorVisibilityObserver() {
  const observer = new MutationObserver(_syncDashboardVisibility);
  document.querySelectorAll('.editor-overlay').forEach(el => {
    observer.observe(el, { attributes: true, attributeFilter: ['class'] });
  });
  _syncDashboardVisibility();
}

/* ─── Sidebar Navigation ─── */
/** Run a navigation action only after resolving unsaved editor changes. */
function _switchWithUnsavedGuard(action) {
  if (isAnyEditorDirty()) {
    _pendingNavigation = action;
    document.getElementById('btn-unsaved-save-exit').textContent = I18N.t('dialog.saveChanges');
    document.getElementById('btn-unsaved-exit-no-save').textContent = I18N.t('dialog.discardChanges');
    document.getElementById('unsaved-changes-modal').classList.remove('hidden');
  } else {
    action();
  }
}

/** Switch the main view after checking for unsaved changes. */
function switchView(viewId) {
  _switchWithUnsavedGuard(() => switchViewNow(viewId));
}

/** Switch the main view immediately, loading view-specific data on demand. */
function switchViewNow(viewId) {
  _hideAllEditors();
  closeMobileSidebar();
  // Close inline plugin config if open
  const pluginInline = document.getElementById('plugins-config-section');
  if (pluginInline && !pluginInline.classList.contains('hidden')) {
    pluginInline.classList.add('hidden');
    document.getElementById('plugin-list-section')?.classList.remove('hidden');
    pluginEditor._detachInputListeners();
    document.getElementById('plugin-review-modal')?.classList.add('hidden');
  }
  // Close inline builtin config if open
  const builtinInline = document.getElementById('builtins-config-section');
  if (builtinInline && !builtinInline.classList.contains('hidden')) {
    builtinInline.classList.add('hidden');
    document.getElementById('builtin-list-section')?.classList.remove('hidden');
    builtinEditor._detachInputListeners();
  }
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
  document.querySelector(`.nav-item[data-view="${viewId}"]`)?.classList.add('active');
  document.getElementById('view-' + viewId)?.classList.add('active');
  if (viewId === 'plugins') {
    renderPluginManager();
  }
  if (viewId === 'hooks') {
    renderHookManager();
  }
  if (viewId === 'builtins') {
    renderBuiltinManager();
  }
  if (viewId === 'overlays') {
    renderOverlayUrls();
  }
  if (viewId === 'servers') {
    loadServerManager();
    startServerLifecyclePolling();
  } else {
    stopServerLifecyclePolling();
  }
  if (viewId === 'log') {
    crashReports.load();
    requestAnimationFrame(() => liveLog._scrollToBottom());
  }
  if (viewId === 'diagnostics') {
    diagnosticsView.load();
  }
  if (viewId === 'revenue') {
    loadRevenueView();
  }
  if (viewId === 'sessions') {
    loadSessions();
  }
  if (viewId === 'backups') {
    loadBackups();
  }
}

/* For nav items that open an editor (Actions/Reactions/Settings) */
/** Open an editor behind the shared unsaved-changes guard. */
function switchToEditor(viewId, openFn) {
  _switchWithUnsavedGuard(() => switchToEditorNow(viewId, openFn));
}

/** Open an editor immediately and restore navigation if it declines to open. */
function switchToEditorNow(viewId, openFn) {
  const prevNav = document.querySelector('.nav-item.active');
  const prevOverlay = document.querySelector('.editor-overlay:not(.hidden)');
  _hideAllEditors();
  closeMobileSidebar();
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const navItem = document.querySelector(`.nav-item[data-view="${viewId}"]`);
  navItem?.classList.add('active');
  let aborted = false;
  // An editor's open() may abort by resolving `false` (e.g. the chatbot beta
  // consent gate). Restore the previous nav item / editor instead of leaving
  // the target nav highlighted above the old dashboard view.
  Promise.resolve(openFn()).then(result => {
    if (result !== false) return;
    aborted = true;
    navItem?.classList.remove('active');
    if (prevNav && prevNav.isConnected) prevNav.classList.add('active');
    if (prevOverlay && prevOverlay.isConnected) prevOverlay.classList.remove('hidden');
  });
  // Re-assert active class after editor opens to handle race condition
  // where MutationObserver might clear it before editor overlay is visible
  setTimeout(() => {
    if (!aborted) navItem?.classList.add('active');
  }, 0);
}

/* ─── Theme Toggle ─── */
/** Apply the persisted theme, defaulting to dark. */
function _initTheme() {
  const saved = localStorage.getItem('theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'dark'); // default to dark for this app
  document.documentElement.setAttribute('data-theme', theme);
  _updateThemeLabel(theme);
}

/** Toggle between the dark and light themes. */
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  _updateThemeLabel(next);
  _retargetPluginFrames(next);
}

/** Update the theme toggle label for the active theme. */
function _updateThemeLabel(theme) {
  const label = document.getElementById('theme-label');
  if (!label) return;
  label.textContent = I18N.t(theme === 'dark' ? 'nav.themeLight' : 'nav.themeDark');
}

/* ─── Language Switcher ─── */
/** Synchronize the language switcher with the active language. */
function _syncLangButtons() {
  const lang = I18N.lang();
  document.querySelectorAll('.lang-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });
}

document.addEventListener('i18n:changed', () => {
  _syncLangButtons();
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  _updateThemeLabel(theme);
  const cfgEditor = document.getElementById('config-editor');
  if (cfgEditor && !cfgEditor.classList.contains('hidden') && typeof editor !== 'undefined') {
    editor.render();
  }
  loadStatus();
  if (typeof reactionEditor !== 'undefined') {
    reactionEditor.renderSidebar();
    reactionEditor.renderList();
  }
  if (document.getElementById('view-revenue')?.classList.contains('active')) {
    renderRevenueView();
  }
  if (document.getElementById('view-sessions')?.classList.contains('active')) {
    renderSessionsView();
  }
});
