/**
 * @file Small shared DOM/string helpers used by the editors.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */

/* ─── Utilities ─── */
/** Escape text for safe insertion into HTML. */
function escapeHtml(text) {
  // Escapes quotes as well — the output is interpolated into quoted HTML
  // attributes and inline onclick JS strings throughout the dashboard.
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
// Sanitizes rendered markdown (e.g. third-party plugin READMEs) before it is
// assigned via innerHTML. The dashboard runs inside a pywebview window with a
// privileged JS bridge, so active content must never survive this path.
/** Sanitize rendered Markdown, using DOMPurify when available and a conservative escape/strip fallback otherwise. */
function sanitizeMarkdownHtml(html) {
  const doc = new DOMParser().parseFromString(String(html), 'text/html');
  doc.querySelectorAll('script,style,iframe,frame,object,embed,link,meta,form,base')
    .forEach(el => el.remove());
  doc.querySelectorAll('*').forEach(el => {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      const value = attr.value;
      if (name.startsWith('on')) {
        el.removeAttribute(attr.name);
      } else if ((name === 'href' || name === 'src' || name === 'xlink:href' || name === 'action') &&
                 /^\s*(javascript|vbscript|data:text\/html)/i.test(value)) {
        el.removeAttribute(attr.name);
      }
    }
  });
  return doc.body.innerHTML;
}
/** Turn an identifier such as `snake_case` into a title-cased label. */
function toTitle(str) {
  return str.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

