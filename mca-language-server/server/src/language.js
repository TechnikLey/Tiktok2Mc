/**
 * @file Language definitions for MCA files.
 *
 * Reads `mca-spec.json`, which is generated from the Python implementation
 * (`src/core/validator.py` and `src/core/api/services/actions.py`).
 *
 * Do not edit the language rules here directly: update the Python source,
 * regenerate the spec, then re-read it with `python tools/generate_mca_spec.py`.
 *
 * If the spec cannot be loaded, the extension degrades safely: all language
 * features (completions, validation, hover) return empty results instead of
 * using potentially stale hardcoded values.
 */

const fs = require('fs');
const path = require('path');

// ── Spec loader ──────────────────────────────────────────────────────────
let spec = null;
let specLoadFailed = false;

const specPaths = [
  path.join(__dirname, '..', '..', 'mca-spec.json'),    // development layout
  path.join(__dirname, '..', 'mca-spec.json'),           // alternate layout
];

for (const p of specPaths) {
  try {
    if (fs.existsSync(p)) {
      const raw = fs.readFileSync(p, 'utf-8');
      spec = JSON.parse(raw);
      break;
    }
  } catch (e) {
    // continue to next path
  }
}

if (!spec) {
  specLoadFailed = true;
  console.warn('[mca-language-server] mca-spec.json not found. Language features disabled.');
}

// ── Pattern compiler (safe from bad spec data) ───────────────────────────

const NEVER_MATCH_RE = /(?!)/;

/**
 * Compile a regular-expression string from the spec.
 *
 * Invalid patterns are replaced with a never-matching regex so a corrupt
 * `mca-spec.json` cannot break the language server.
 *
 * @param {string} patternStr Regular-expression source from the spec.
 * @returns {RegExp} Compiled expression, or a never-matching expression.
 */
function compilePattern(patternStr) {
  try {
    return new RegExp(patternStr);
  } catch (e) {
    return NEVER_MATCH_RE;
  }
}

// ── Compiled regex patterns from spec ────────────────────────────────────

/**
 * Return a compiled spec pattern by name.
 *
 * @param {string} patternName Key in `spec.patterns`.
 * @returns {RegExp} Compiled pattern, or a never-matching expression when the
 *   spec is unavailable or the key does not exist.
 */
function specPattern(patternName) {
  if (!spec || !spec.patterns || !spec.patterns[patternName]) return NEVER_MATCH_RE;
  return compilePattern(spec.patterns[patternName]);
}

/**
 * Return a raw validation rule from the spec.
 *
 * @param {string} ruleName Key in `spec.validation_rules`.
 * @returns {*} The rule value (string, number or object), or `null` when the
 *   spec is unavailable or the rule is absent.
 */
function specRule(ruleName) {
  if (!spec || !spec.validation_rules || spec.validation_rules[ruleName] == null) return null;
  return spec.validation_rules[ruleName];
}

const NAMED_OVERLAY_RE = specPattern('overlay_prefix');
const MULTIPLIER_RE = specPattern('multiplier');
const INVALID_MULTIPLIER_RE = specPattern('invalid_multiplier');
const DYNAMIC_VANILLA_RE = specPattern('dynamic_vanilla');

const _unquotedTrigger = specRule('valid_unquoted_trigger');
const _quotedTrigger = specRule('valid_quoted_trigger');
const TRIGGER_NAME_RE = _unquotedTrigger ? compilePattern(_unquotedTrigger) : NEVER_MATCH_RE;
const QUOTED_TRIGGER_RE = _quotedTrigger ? compilePattern(_quotedTrigger) : NEVER_MATCH_RE;

const VALID_PREFIX_CHARS = (spec && spec.command_start_patterns && spec.command_start_patterns.single_char)
  ? spec.command_start_patterns.single_char
  : [];

// ── Accessors ────────────────────────────────────────────────────────────

/**
 * Return the known event trigger names.
 *
 * @returns {string[]} Event trigger names, or an empty array without a spec.
 */
function getEventTriggers() {
  if (spec && spec.event_triggers) return spec.event_triggers;
  return [];
}

/**
 * Return the documentation entries for event triggers.
 *
 * @returns {Array<{name: string, doc: string}>} Trigger documentation, or an
 *   empty array without a spec.
 */
function getEventTriggerDocs() {
  if (spec && spec.event_trigger_docs) return spec.event_trigger_docs;
  return [];
}

/**
 * Return the supported command prefixes and their metadata.
 *
 * @returns {Record<string, {label: string, doc: string}>} Prefix metadata, or
 *   an empty object without a spec.
 */
function getCommandPrefixes() {
  if (spec && spec.command_prefixes) return spec.command_prefixes;
  return {};
}

/**
 * Return the placeholders that may appear in commands.
 *
 * @returns {Array<{name: string, doc: string}>} Placeholder definitions, or an
 *   empty array without a spec.
 */
function getPlaceholders() {
  if (spec && spec.placeholders) return spec.placeholders;
  return [];
}

/**
 * Return the raw validation rules.
 *
 * @returns {Record<string, *>} Validation rules, or an empty object without a
 *   spec.
 */
function getRules() {
  if (spec && spec.validation_rules) return spec.validation_rules;
  return {};
}

/**
 * Return the raw regular-expression patterns.
 *
 * @returns {Record<string, string>} Pattern sources, or an empty object
 *   without a spec.
 */
function getPatterns() {
  if (spec && spec.patterns) return spec.patterns;
  return {};
}

/**
 * Return the command-start pattern definitions.
 *
 * @returns {Record<string, *>} Command-start patterns, or an empty object
 *   without a spec.
 */
function getCommandStartPatterns() {
  if (spec && spec.command_start_patterns) return spec.command_start_patterns;
  return {};
}

/**
 * Return the parsed spec document.
 *
 * @returns {object|null} The parsed `mca-spec.json`, or `null` when loading
 *   failed.
 */
function getSpec() {
  return spec;
}

module.exports = {
  getEventTriggers,
  getEventTriggerDocs,
  getCommandPrefixes,
  getPlaceholders,
  getRules,
  getPatterns,
  getCommandStartPatterns,
  getSpec,
  // Exported regex constants for use in other modules
  NAMED_OVERLAY_RE,
  MULTIPLIER_RE,
  INVALID_MULTIPLIER_RE,
  DYNAMIC_VANILLA_RE,
  TRIGGER_NAME_RE,
  QUOTED_TRIGGER_RE,
  VALID_PREFIX_CHARS,
};
