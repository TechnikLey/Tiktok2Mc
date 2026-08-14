import js from "@eslint/js";
import globals from "globals";
import { defineConfig } from "eslint/config";

// Cross-file globals shared between the classic <script> files (app.js and
// actions-editor.js are loaded into one page via <script> tags) and by the
// vitest tests (which evaluate both files into the jsdom global scope).
const appGlobals = {
  pywebview: "writable",
  ActionsEditor: "writable",
  I18N: "writable",
  Help: "writable",
  Shortcuts: "writable",
  fetchJSON: "writable",
  postJSON: "writable",
  putJSON: "writable",
  showToast: "writable",
  showConfirmDialog: "writable",
  escapeHtml: "writable",
  currentConfig: "writable",
  editor: "writable",
  pluginEditor: "writable",
  hookEditor: "writable",
  reactionEditor: "writable",
  actionsEditor: "writable",
  closeServerCreateModal: "writable",
  closeServerDownloadModal: "writable",
  closeServerSwitchModal: "writable",
  closeServerCustomModal: "writable",
};

export default defineConfig([
  {
    files: ["**/*.{js,mjs,cjs}"],
    plugins: { js },
    extends: ["js/recommended"],
    languageOptions: { globals: globals.browser },
    rules: { "no-empty": ["error", { allowEmptyCatch: true }] },
  },
  {
    // ESM files: the config itself, the vitest config, and vitest tests.
    files: ["eslint.config.js", "vitest.config.js", "tests/**/*.js"],
    languageOptions: { sourceType: "module" },
  },
  {
    // Vitest tests: they reference app.js/actions-editor.js globals set up in
    // tests/setup.js. Those references are validated at runtime (a typo'd
    // global throws ReferenceError), so static no-undef does not apply.
    files: ["tests/**/*.js"],
    rules: {
      "no-undef": "off",
    },
  },
  {
    // Classic browser scripts. Top-level bindings are global by design (used
    // from inline HTML handlers and other scripts), so unused-var and
    // redeclaration analysis cannot apply here. Cross-file globals are
    // declared explicitly above. Empty catch blocks swallow errors on purpose.
    files: ["app.js", "actions-editor.js", "help.js", "shortcuts.js"],
    languageOptions: {
      sourceType: "script",
      globals: { ...globals.browser, ...appGlobals },
    },
    rules: {
      "no-unused-vars": "off",
      "no-redeclare": "off",
      "no-empty": ["error", { allowEmptyCatch: true }],
    },
  },
]);
