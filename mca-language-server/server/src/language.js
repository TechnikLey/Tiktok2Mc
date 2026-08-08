// Language definitions for MCA.
//
// This file reads mca-spec.json (generated from the Python implementation:
// src/core/validator.py and src/core/api/services/actions.py).
//
// DO NOT edit language rules here directly — update the Python source,
// regenerate the spec, then re-read:  python tools/generate_mca_spec.py
//
// If the spec file cannot be loaded, the extension degrades safely:
// all language features (completions, validation, hover) return empty
// results rather than using potentially stale hardcoded values.

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

function compilePattern(patternStr) {
  try {
    return new RegExp(patternStr);
  } catch (e) {
    return NEVER_MATCH_RE;
  }
}

// ── Compiled regex patterns from spec ────────────────────────────────────

function specPattern(patternName) {
  if (!spec || !spec.patterns || !spec.patterns[patternName]) return NEVER_MATCH_RE;
  return compilePattern(spec.patterns[patternName]);
}

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

function getEventTriggers() {
  if (spec && spec.event_triggers) return spec.event_triggers;
  return [];
}

function getEventTriggerDocs() {
  if (spec && spec.event_trigger_docs) return spec.event_trigger_docs;
  return [];
}

function getCommandPrefixes() {
  if (spec && spec.command_prefixes) return spec.command_prefixes;
  return {};
}

function getPlaceholders() {
  if (spec && spec.placeholders) return spec.placeholders;
  return [];
}

function getRules() {
  if (spec && spec.validation_rules) return spec.validation_rules;
  return {};
}

function getPatterns() {
  if (spec && spec.patterns) return spec.patterns;
  return {};
}

function getCommandStartPatterns() {
  if (spec && spec.command_start_patterns) return spec.command_start_patterns;
  return {};
}

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
