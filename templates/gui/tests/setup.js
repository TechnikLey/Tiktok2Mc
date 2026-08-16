import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// --- DOM setup from index.html ---
const html = readFileSync(join(__dirname, '..', 'index.html'), 'utf-8');
document.documentElement.innerHTML = html;

// --- Global browser mocks (JSDOM doesn't provide these) ---
window.fetch = async () => ({
  ok: true,
  status: 200,
  statusText: 'OK',
  json: async () => ({}),
});

window.EventSource = class {
  constructor(url) { this.url = url; this.onmessage = null; this.onerror = null; }
  close() {}
};

window.IntersectionObserver = class {
  constructor(callback) { this.callback = callback; }
  observe() {}
  disconnect() {}
  unobserve() {}
};

Object.defineProperty(window.navigator, 'clipboard', {
  value: { writeText: async () => {} },
  configurable: true,
});

// JSDOM doesn't implement scrollIntoView
Element.prototype.scrollIntoView = () => {};

window.pywebview = {
  api: {
    close_requested: async () => false,
    reset_close_request: async () => {},
    approve_close: async () => {},
  },
};

// --- Transform top-level declarations to window.* assignments ---
// Only affects declarations at brace depth 0 (not inside functions/blocks)

function toGlobalScope(code) {
  const lines = code.split('\n');
  const result = [];
  let depth = 0;

  for (const line of lines) {
    // Transform declarations only at top-level (before processing this line's braces)
    if (depth === 0) {
      // class X { ... }  ->  window.X = class X { ... }
      if (/^class\s+(\w+)/.test(line)) {
        result.push(line.replace(/^(class\s+)(\w+)/, 'window.$2 = $1$2'));
        depth += (line.match(/{/g) || []).length;
        depth -= (line.match(/}/g) || []).length;
        continue;
      }
      // async function name(...)  ->  keep as-is for hoisting, + window.name = name
      if (/^async\s+function\s+(\w+)/.test(line)) {
        result.push(line);
        const m = line.match(/^async\s+function\s+(\w+)/);
        result.push(`window.${m[1]} = ${m[1]};`);
        depth += (line.match(/{/g) || []).length;
        depth -= (line.match(/}/g) || []).length;
        continue;
      }
      // function name(...)  ->  keep as-is for hoisting, + window.name = name
      if (/^function\s+(\w+)/.test(line)) {
        result.push(line);
        const m = line.match(/^function\s+(\w+)/);
        result.push(`window.${m[1]} = ${m[1]};`);
        depth += (line.match(/{/g) || []).length;
        depth -= (line.match(/}/g) || []).length;
        continue;
      }
      // const|let name = ...  ->  window.name = ...
      if (/^(const|let)\s+(\w+)\s*=/.test(line)) {
        result.push(line.replace(/^(const|let)\s+(\w+)\s*=/, 'window.$2 ='));
        depth += (line.match(/{/g) || []).length;
        depth -= (line.match(/}/g) || []).length;
        continue;
      }
    }

    depth += (line.match(/{/g) || []).length;
    depth -= (line.match(/}/g) || []).length;
    result.push(line);
  }

  return result.join('\n');
}

// Load and transform JS files
const i18nJs = readFileSync(join(__dirname, '..', 'i18n.js'), 'utf-8');
const helpJs = readFileSync(join(__dirname, '..', 'help.js'), 'utf-8');
const shortcutsJs = readFileSync(join(__dirname, '..', 'shortcuts.js'), 'utf-8');
const accessibilityJs = readFileSync(join(__dirname, '..', 'accessibility.js'), 'utf-8');
const actionsEditorJs = readFileSync(join(__dirname, '..', 'actions-editor.js'), 'utf-8');
const appJs = readFileSync(join(__dirname, '..', 'app.js'), 'utf-8');

// Evaluate in global scope (i18n first: help.js/app.js/actions-editor.js use I18N;
// help.js second: app.js uses Help; shortcuts.js third: binds global shortcuts)
(0, eval)(toGlobalScope(i18nJs));
(0, eval)(toGlobalScope(helpJs));
(0, eval)(toGlobalScope(shortcutsJs));
(0, eval)(toGlobalScope(accessibilityJs));
(0, eval)(toGlobalScope(actionsEditorJs));
(0, eval)(toGlobalScope(appJs));
