/**
 * @file Core API access and shared state for the TikTok2MC dashboard.
 *
 * First part of the split dashboard controller (`js/app-*.js`, loaded in order
 * by index.html). Defines the API base URL, global config/plugin/hook state and
 * the fetchJSON/postJSON/putJSON helpers used by every later app part.
 */
const API = '/api/v1';
let currentConfig = {};
let currentPlugins = [];
let currentHooks = [];
let wizardStep = 0;
let wizardData = {};

/* ─── API key (LAN dashboard access) ───
 * When the server is exposed beyond localhost (server_host: 0.0.0.0) with
 * an api_key configured, requests from other devices need it.  Provide it
 * by opening the dashboard as /gui/?key=YOUR_KEY; it is remembered in
 * localStorage and attached to every request (and the SSE stream).
 */
let _apiKey = (typeof localStorage !== 'undefined' && localStorage.getItem('tiktok2mc_api_key')) || '';
const _urlKey = new URLSearchParams(window.location.search).get('key');
if (_urlKey) {
  _apiKey = _urlKey;
  try { localStorage.setItem('tiktok2mc_api_key', _apiKey); } catch (_) {}
  const cleanUrl = window.location.href.replace(/([?&])key=[^&]*/, '$1').replace(/[?&]$/, '');
  window.history.replaceState({}, document.title, cleanUrl);
}
/** Return a copy of `headers` with the dashboard `X-API-Key` header when a key is configured. */
function _withApiKey(headers) {
  if (!_apiKey) return headers;
  return Object.assign({}, headers, { 'X-API-Key': _apiKey });
}

/* ─── API helpers ─── */
/**
 * Extract a human-readable error detail from a failed response.
 *
 * Prefers the JSON `detail` field and falls back to at most 500 characters of raw body text.
 */
async function _parseErrorDetail(res) {
  try {
    const data = await res.json();
    if (data && data.detail) {
      return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    }
  } catch (_) { /* not JSON */ }
  try {
    const text = await res.text();
    if (text) return text.slice(0, 500);
  } catch (_) { /* body already consumed */ }
  return '';
}
/**
 * Throw a localized error for a non-OK response.
 *
 * Shows a missing-key toast on 401 and delegates message formatting to `Help.formatApiError` when available.
 */
async function _throwResError(res) {
  const detail = await _parseErrorDetail(res);
  if (res.status === 401) {
    showToast(I18N.t('dialog.missingKey'), 'error');
  }
  const friendly = typeof Help !== 'undefined'
    ? Help.formatApiError(res.status, detail)
    : res.status + ' ' + res.statusText + (detail ? ': ' + detail : '');
  throw new Error(friendly);
}
/** GET `path` below `/api/v1` and return the decoded JSON body, throwing on HTTP errors. */
async function fetchJSON(path) {
  const res = await fetch(API + path, { headers: _withApiKey({}) });
  if (!res.ok) await _throwResError(res);
  return res.json();
}
/** POST `body` as JSON to `path` below `/api/v1` and return the decoded JSON response. */
async function postJSON(path, body) {
  const res = await fetch(API + path, {
    method: 'POST',
    headers: _withApiKey({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body)
  });
  if (!res.ok) await _throwResError(res);
  return res.json();
}
/** PUT `body` as JSON to `path` below `/api/v1` and return the decoded JSON response. */
async function putJSON(path, body) {
  const res = await fetch(API + path, {
    method: 'PUT',
    headers: _withApiKey({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body)
  });
  if (!res.ok) await _throwResError(res);
  return res.json();
}

