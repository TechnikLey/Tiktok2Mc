/**
 * @file Bootstrap entry point for the TikTok2MC dashboard.
 *
 * Loaded last by index.html after all `js/app-*.js` parts. Defines the startup
 * sequence and hides the loading indicator once initialization completes.
 */
/* ─── Init ─── */
/** Initialize the dashboard: theme, language, navigation, data loaders, SSE, updates and the first-run wizard. */
async function init() {
  _initTheme();
  _syncLangButtons();
  _initEditorVisibilityObserver();
  _initSidebarReveal();
  _initMobileSidebar();
  await loadHealth();
  await loadStatus();
  await loadConfig();
  await loadPlugins();
  // One-time hook discovery at startup, then periodic refresh is just the list
  await postJSON('/hooks/discover', {}).catch(() => {});
  await loadHooks();
  await loadServerManager();
  await reactionEditor.load();
  updateRestartBanner();
  connectLogStream();
  checkAllUpdates();
  if (isFirstRun(currentConfig)) showWizard();
  else hideWizard();
  if (!window.__TEST__) {
    _healthIntervalId = setInterval(loadHealth, 10000);
    _statusIntervalId = setInterval(loadStatus, 10000);
    _pluginsIntervalId = setInterval(loadPlugins, 5000);
    _hooksIntervalId = setInterval(loadHooks, 10000);
    _uptimeIntervalId = setInterval(() => {
      const activeView = document.querySelector('.view.active');
      if (activeView && activeView.id === 'view-status') {
        _updateUptimeDisplay();
      }
      if (activeView && (activeView.id === 'view-status' || activeView.id === 'view-servers')) {
        _updateServerUptimeDisplay();
      }
      _updateTiktokStatusDisplay();
    }, 1000);
    if (typeof pywebview !== 'undefined' && pywebview.api) {
      _closePollIntervalId = setInterval(_pollCloseRequest, 200);
    }
  }
}
/** Hide the full-screen application loading indicator. */
function hideAppLoading() {
  document.getElementById('app-loading')?.classList.add('app-loading--hidden');
}
init().finally(hideAppLoading);
