// Test that the shared spec (mca-spec.json) can be loaded and contains expected keys.

const assert = require('assert');
const path = require('path');
const fs = require('fs');

function test(name, fn) {
  try {
    fn();
    console.log(`  PASS  ${name}`);
  } catch (err) {
    console.error(`  FAIL  ${name}`);
    console.error(`        ${err.message}`);
    process.exitCode = 1;
  }
}

// Load spec via the language module
const lang = require('../src/language');

test('spec file exists and is loadable', () => {
  const spec = lang.getSpec();
  assert.ok(spec !== null, 'spec should be loaded');
});

test('spec has version', () => {
  const spec = lang.getSpec();
  assert.ok(spec.version);
});

test('spec has event_triggers', () => {
  const triggers = lang.getEventTriggers();
  assert.ok(Array.isArray(triggers));
  assert.ok(triggers.includes('follow'));
  assert.ok(triggers.includes('comment'));
  assert.ok(triggers.includes('likes'));
});

test('spec has command_prefixes', () => {
  const prefixes = lang.getCommandPrefixes();
  assert.ok(prefixes['/']);
  assert.ok(prefixes['!']);
  assert.ok(prefixes['$']);
  assert.ok(prefixes['&']);
  assert.ok(prefixes['>>']);
});

test('spec has placeholders', () => {
  const placeholders = lang.getPlaceholders();
  assert.ok(Array.isArray(placeholders));
  const names = placeholders.map(p => p.name);
  assert.ok(names.includes('{user}'));
  assert.ok(names.includes('{comment}'));
});

test('spec has validation_rules', () => {
  const rules = lang.getRules();
  assert.ok(rules.high_multi_threshold > 0);
});

test('spec has command_start_patterns', () => {
  const patterns = lang.getCommandStartPatterns();
  assert.ok(Array.isArray(patterns.single_char));
  assert.ok(patterns.single_char.includes('/'));
  assert.ok(Array.isArray(patterns.multi_char));
  assert.ok(typeof patterns.description === 'string');
});

test('spec has diagnostic_codes', () => {
  const spec = lang.getSpec();
  assert.ok(Array.isArray(spec.diagnostic_codes));
  const codes = spec.diagnostic_codes.map(d => d.code);
  assert.ok(codes.includes('missing_colon'));
  assert.ok(codes.includes('duplicate_trigger'));
  assert.ok(codes.includes('invalid_prefix'));
  assert.ok(codes.includes('high_multi'));
  assert.ok(codes.includes('comment_placeholder_wrong_trigger'));
});

test('spec has patterns', () => {
  const patterns = lang.getPatterns();
  assert.ok(patterns.trailing_semicolon !== undefined);
  assert.ok(patterns.overlay_prefix !== undefined);
  assert.ok(patterns.multiplier !== undefined);
});

test('spec has event_trigger_docs', () => {
  const docs = lang.getEventTriggerDocs();
  assert.ok(Array.isArray(docs));
  assert.ok(docs.length >= 6);
});

console.log('\nSpec tests complete.\n');
