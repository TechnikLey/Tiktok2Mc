// Language definitions for MCA.
//
// This file is generated from mca-spec.json (which is itself generated from
// the Python implementation: src/core/validator.py and
// src/core/api/services/actions.py).
//
// DO NOT edit language rules here directly — update the Python source,
// regenerate the spec, then re-read:  python tools/generate_mca_spec.py
//
// If the spec file cannot be loaded, fallback values are used so the
// extension remains functional.

const fs = require('fs');
const path = require('path');

// ── Load spec ───────────────────────────────────────────────────────────
let spec = null;
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
    // silently continue to fallback
  }
}

// ── Fallback constants (used only when spec loading fails) ──────────────

const FALLBACK_EVENT_TRIGGERS = ['follow', 'join', 'comment', 'likes', 'like_2', 'share'];

const FALLBACK_PREFIXES = {
  '/': { type: 'vanilla', label: 'Vanilla Minecraft', doc: 'Minecraft command via datapack' },
  '!': { type: 'rcon', label: 'RCON', doc: 'Command sent directly via RCON' },
  '$': { type: 'script', label: 'Script', doc: 'Hook script action' },
  '&': { type: 'shell', label: 'Shell', doc: 'Host shell command' },
  '>>': { type: 'overlay', label: 'Overlay', doc: 'Overlay text: >>Title|Subtitle|Duration' },
};

const FALLBACK_PLACEHOLDERS = [
  { name: '{user}', triggers: ['all'], doc: 'Replaced with the triggering user\'s display name' },
  { name: '{comment}', triggers: ['comment'], doc: 'Replaced with comment text (only on "comment" trigger)' },
];

const FALLBACK_RULES = {
  high_multi_threshold: 50,
  valid_prefix_chars: ['/', '!', '$', '&'],
};

// ── Accessors ───────────────────────────────────────────────────────────

function getEventTriggers() {
  if (spec && spec.event_triggers) return spec.event_triggers;
  return FALLBACK_EVENT_TRIGGERS;
}

function getEventTriggerDocs() {
  if (spec && spec.event_trigger_docs) return spec.event_trigger_docs;
  return FALLBACK_EVENT_TRIGGERS.map(name => ({ name, doc: '' }));
}

function getCommandPrefixes() {
  if (spec && spec.command_prefixes) return spec.command_prefixes;
  return FALLBACK_PREFIXES;
}

function getPlaceholders() {
  if (spec && spec.placeholders) return spec.placeholders;
  return FALLBACK_PLACEHOLDERS;
}

function getRules() {
  if (spec && spec.validation_rules) return spec.validation_rules;
  return FALLBACK_RULES;
}

function getPatterns() {
  if (spec && spec.patterns) return spec.patterns;
  return {};
}

function getSpec() {
  return spec;
}

// ── Compiled regex patterns (from spec or fallback) ─────────────────────

const NAMED_OVERLAY_RE = /^@(\w+)>>/;
const MULTIPLIER_RE = /\s+x(\d+)\s*$/;
const INVALID_MULTIPLIER_RE = /\s+x([^\s]+)\s*$/;
const TRIGGER_NAME_RE = /^[A-Za-z0-9_]+$/;
const QUOTED_TRIGGER_RE = /^'[A-Za-z0-9_ ]+'$/;
const VALID_PREFIX_CHARS = getRules().valid_prefix_chars || FALLBACK_RULES.valid_prefix_chars;

module.exports = {
  getEventTriggers,
  getEventTriggerDocs,
  getCommandPrefixes,
  getPlaceholders,
  getRules,
  getPatterns,
  getSpec,
  // Exposed regex constants for direct use in other modules
  NAMED_OVERLAY_RE,
  MULTIPLIER_RE,
  INVALID_MULTIPLIER_RE,
  TRIGGER_NAME_RE,
  QUOTED_TRIGGER_RE,
  VALID_PREFIX_CHARS,
};
