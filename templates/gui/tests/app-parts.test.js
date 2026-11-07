import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const GUI_DIR = join(__dirname, '..');

/** Return all `<script>` tags from index.html in document order. */
function scriptTags() {
  const html = readFileSync(join(GUI_DIR, 'index.html'), 'utf-8');
  return Array.from(html.matchAll(/<script\b[^>]*>/gi), (match) => match[0]);
}

/** Extract the `src` attribute from a script tag, if present. */
function srcOf(tag) {
  const match = tag.match(/\bsrc\s*=\s*["']([^"']+)["']/i);
  return match ? match[1].replace(/\?.*$/, '') : null;
}

describe('split app.js scripts', () => {
  const tags = scriptTags();
  const appTags = tags.filter((tag) => {
    const src = srcOf(tag);
    return src === './app.js' || /^\.\/js\/app-[^/]+\.js$/.test(src || '');
  });
  const appParts = appTags
    .map((tag) => srcOf(tag).replace(/^\.\/js\//, '').replace(/^\.\//, ''))
    .filter((src) => src !== 'app.js');
  const partFiles = readdirSync(join(GUI_DIR, 'js'))
    .filter((name) => name.endsWith('.js'))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

  it('references every part exactly once, in numeric order, with app.js last', () => {
    expect(appParts).toEqual(partFiles);
    expect(new Set(appParts).size).toBe(appParts.length);
    expect(appParts.every((name) => /^app-\d{2}-[a-z0-9-]+\.js$/.test(name))).toBe(true);

    const srcs = appTags.map(srcOf);
    expect(srcs.filter((src) => src === './app.js')).toHaveLength(1);
    expect(srcs[srcs.length - 1]).toBe('./app.js');
  });

  it('loads the parts as classic, cache-busted scripts', () => {
    for (const tag of appTags) {
      expect(tag).not.toMatch(/\bdefer\b/i);
      expect(tag).not.toMatch(/\basync\b/i);
      expect(tag).not.toMatch(/\btype\s*=\s*["']module["']/i);
      expect(tag).toMatch(/\?v=\d+/);
    }
  });

  it('keeps every part non-empty and newline-terminated', () => {
    for (const name of partFiles) {
      const content = readFileSync(join(GUI_DIR, 'js', name), 'utf-8');
      expect(content.length).toBeGreaterThan(0);
      expect(content.endsWith('\n')).toBe(true);
    }
  });
});
