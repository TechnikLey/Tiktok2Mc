# Dashboard controller parts

`templates/gui/app.js` is only the bootstrap. It loads last and calls `init()`.
The controller itself is split into ordered classic scripts under this directory.
`index.html` defines the load order; do not use `defer`, `async`, or
`type="module"`.

## Load order

| File | Responsibility |
|---|---|
| `app-00-core.js` | API base URL, shared state, API-key handling, `fetchJSON`/`postJSON`/`putJSON`, error helpers |
| `app-05-ui-shell.js` | Shutdown countdown, TikTok failure dialog, confirm/prompt dialogs |
| `app-10-live-log.js` | `LiveLog`, `log`, `CrashReports`, `showToast` |
| `app-15-dashboard.js` | Health/status polling, live stats, plugin status, hook widgets |
| `app-20-servers.js` | Server manager, Java setup, MC plugins, server modals, overlay URLs. The server-modal button wiring is at the end of this file. |
| `app-25-revenue.js` | Revenue view |
| `app-30-sessions.js` | Sessions view |
| `app-35-backups.js` | Backups and config-bundle export/import |
| `app-40-plugins.js` | Plugin manager, plugin pages, readme modal |
| `app-45-hooks.js` | Hook manager and builtin-hook list |
| `app-50-hook-config-editor.js` | `HookConfigEditor` |
| `app-55-builtin-config-editor.js` | `BuiltinConfigEditor` and instances |
| `app-60-config-wizard.js` | Config wizard, restart dialog/banner |
| `app-65-config-schema.js` | Config schema metadata, help texts, section labels |
| `app-70-config-editor.js` | `ConfigEditor` and instance |
| `app-75-dom-helpers.js` | `escapeHtml`, `sanitizeMarkdownHtml`, `toTitle` |
| `app-80-plugin-config-editor.js` | `PluginConfigEditor` |
| `app-85-reaction-editor.js` | `ReactionEditor` |
| `app-90-comment-commands-editor.js` | `CommentCommandsEditor` |
| `app-92-editor-lifecycle.js` | Editor instances, dirty state, close guard, save/discard all |
| `app-94-updates.js` | Update checks, apply/notification, tool update. The update-button wiring is at the end of this file. |
| `app-96-console.js` | SSE log stream, console/terminal, diagnostics |
| `app-97-navigation.js` | Sidebar, view switching, theme, language buttons |
| `app-98-event-tester.js` | `EventTester` and instance |

`app.js` at the parent level is the final bootstrap: `init()`,
`hideAppLoading()`, and the `init().finally(hideAppLoading)` call.

## Rules

- Keep the order in `index.html` in sync with the numeric prefixes. `app.js`
  must remain the last script.
- Do not move the wiring blocks at the end of `app-20-servers.js` or
  `app-94-updates.js` above the functions they reference. They rely on
  declarations in the same file and are kept there deliberately.
- Adding or renaming a part requires updating `index.html`; `tests/setup.js`
  loads the parts in production order and `tests/app-parts.test.js` checks the
  file list and ordering.
