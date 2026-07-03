const assert = require('assert');
const { validateDocument } = require('../src/validator');

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

// Helper: find diagnostics by code
function findByCode(diags, code) {
  return diags.filter(d => d.code === code);
}
function countByCode(diags, code) {
  return findByCode(diags, code).length;
}

// ── Colon tests ────────────────────────────────────────────────────────

test('missing_colon - ERROR', () => {
  const diags = validateDocument('no colon here');
  assert.strictEqual(countByCode(diags, 'missing_colon'), 1);
});

test('space_after_colon - WARNING', () => {
  const diags = validateDocument('test: /say hi');
  assert.strictEqual(countByCode(diags, 'space_after_colon'), 1);
});

test('no_content_after_colon - ERROR', () => {
  const diags = validateDocument('test:');
  assert.strictEqual(countByCode(diags, 'no_content_after_colon'), 1);
});

test('trailing_colons - ERROR', () => {
  const diags = validateDocument('test:/say:');
  assert.strictEqual(countByCode(diags, 'trailing_colons'), 1);
});

test('trailing_semicolon - INFO', () => {
  const diags = validateDocument('test:/say;');
  assert.strictEqual(countByCode(diags, 'trailing_semicolon'), 1);
});

// ── Bracket tests ──────────────────────────────────────────────────────

test('balanced_square_brackets - no error', () => {
  const diags = validateDocument('test:/say [test]');
  assert.strictEqual(countByCode(diags, 'unbalanced_square'), 0);
  assert.strictEqual(countByCode(diags, 'unmatched_close_square'), 0);
});

test('unmatched_close_square - ERROR', () => {
  const diags = validateDocument('test:/say ]');
  assert.strictEqual(countByCode(diags, 'unmatched_close_square'), 1);
});

test('unbalanced_open_square - ERROR', () => {
  const diags = validateDocument('test:/say [test');
  assert.strictEqual(countByCode(diags, 'unbalanced_square'), 1);
});

test('balanced_curly_brackets - no error', () => {
  const diags = validateDocument('test:/say {nbt}');
  assert.strictEqual(countByCode(diags, 'unbalanced_curly'), 0);
  assert.strictEqual(countByCode(diags, 'unmatched_close_curly'), 0);
});

test('unmatched_close_curly - ERROR', () => {
  const diags = validateDocument('test:/say }');
  assert.strictEqual(countByCode(diags, 'unmatched_close_curly'), 1);
});

test('unbalanced_open_curly - ERROR', () => {
  const diags = validateDocument('test:/say {nbt');
  assert.strictEqual(countByCode(diags, 'unbalanced_curly'), 1);
});

test('brackets_inside_double_quotes', () => {
  const diags = validateDocument('test:/say "hello [world]"');
  assert.strictEqual(countByCode(diags, 'unbalanced_square'), 0);
});

test('brackets_inside_single_quotes', () => {
  const diags = validateDocument("test:/say 'hello [world]'");
  assert.strictEqual(countByCode(diags, 'unbalanced_square'), 0);
});

test('escaped_quotes_inside_brackets', () => {
  const diags = validateDocument("test:/say [it\\'s ok]");
  assert.strictEqual(countByCode(diags, 'unbalanced_square'), 0);
});

// ── Trigger name tests ─────────────────────────────────────────────────

test('valid trigger name', () => {
  const diags = validateDocument('like:/say Thanks!');
  assert.strictEqual(countByCode(diags, 'invalid_trigger_name'), 0);
});

test('valid quoted trigger name', () => {
  const diags = validateDocument("'my trigger':/say hi");
  assert.strictEqual(countByCode(diags, 'invalid_trigger_name'), 0);
});

test('invalid trigger name (special chars)', () => {
  const diags = validateDocument('bad-trigger!:x');
  assert.strictEqual(countByCode(diags, 'invalid_trigger_name'), 1);
});

test('invalid quoted trigger name', () => {
  const diags = validateDocument("'bad-trigger!':x");
  assert.strictEqual(countByCode(diags, 'invalid_trigger_name'), 1);
});

test('duplicate_trigger', () => {
  const diags = validateDocument('dup:/a\ndup:/b');
  assert.strictEqual(countByCode(diags, 'duplicate_trigger'), 1);
});

// ── Command prefix tests ───────────────────────────────────────────────

test('valid slash prefix', () => {
  const diags = validateDocument('test:/say hi');
  assert.strictEqual(countByCode(diags, 'invalid_prefix'), 0);
});

test('valid dollar prefix', () => {
  const diags = validateDocument('test:$script');
  assert.strictEqual(countByCode(diags, 'invalid_prefix'), 0);
});

test('valid bang prefix', () => {
  const diags = validateDocument('test:!rcon cmd');
  assert.strictEqual(countByCode(diags, 'invalid_prefix'), 0);
});

test('valid overlay arrow', () => {
  const diags = validateDocument('test:>>overlay');
  assert.strictEqual(countByCode(diags, 'invalid_prefix'), 0);
});

test('valid named overlay', () => {
  const diags = validateDocument('test:@name>>overlay');
  assert.strictEqual(countByCode(diags, 'invalid_prefix'), 0);
});

test('valid ampersand prefix', () => {
  const diags = validateDocument('test:&curl http://localhost');
  assert.strictEqual(countByCode(diags, 'invalid_prefix'), 0);
});

test('invalid prefix', () => {
  const diags = validateDocument('test:%bad');
  assert.strictEqual(countByCode(diags, 'invalid_prefix'), 1);
});

// ── Placeholder tests ──────────────────────────────────────────────────

test('{comment} on comment trigger - no error', () => {
  const diags = validateDocument('comment:>>say {comment}');
  assert.strictEqual(countByCode(diags, 'comment_placeholder_wrong_trigger'), 0);
});

test('{comment} on non-comment trigger - ERROR', () => {
  const diags = validateDocument('like:>>say {comment}');
  assert.strictEqual(countByCode(diags, 'comment_placeholder_wrong_trigger'), 1);
});

// ── Multiplier tests ───────────────────────────────────────────────────

test('valid multiplier', () => {
  const diags = validateDocument('test:/cmd x5');
  assert.strictEqual(countByCode(diags, 'invalid_multiplier'), 0);
});

test('high multiplier warning', () => {
  const diags = validateDocument('test:/cmd x100');
  assert.strictEqual(countByCode(diags, 'high_multi'), 1);
});

test('high multiplier suppressed with ignore-lag', () => {
  const diags = validateDocument('test:/cmd x100 # ignore-lag');
  assert.strictEqual(countByCode(diags, 'high_multi'), 0);
});

test('invalid multiplier (non-numeric)', () => {
  const diags = validateDocument('test:/cmd xabc');
  assert.strictEqual(countByCode(diags, 'invalid_multiplier'), 1);
});

test('overlay multiplier not allowed', () => {
  const diags = validateDocument('test:>>overlay x5');
  assert.strictEqual(countByCode(diags, 'overlay_multiplier'), 1);
});

// ── Empty lines and comments ───────────────────────────────────────────

test('empty lines produce no diagnostics', () => {
  const diags = validateDocument('\n\n');
  assert.strictEqual(diags.length, 0);
});

test('full-line comment produces no diagnostics', () => {
  const diags = validateDocument('# this is a comment');
  assert.strictEqual(diags.length, 0);
});

test('inline comment is valid', () => {
  const diags = validateDocument('test:/say hi # inline comment');
  const errors = diags.filter(d => d.severity === 1);
  assert.strictEqual(errors.length, 0);
});

// ── Semicolon separated commands ───────────────────────────────────────

test('multiple commands - valid', () => {
  const diags = validateDocument('test:/first;/second');
  const errors = diags.filter(d => d.severity === 1);
  assert.strictEqual(errors.length, 0);
});

test('empty command block (double semicolon)', () => {
  const diags = validateDocument('test:/first;;/third');
  assert.strictEqual(countByCode(diags, 'empty_command_block'), 1);
});

test('trailing semicolon after multiple commands', () => {
  const diags = validateDocument('test:/first;/second;');
  assert.strictEqual(countByCode(diags, 'trailing_semicolon'), 1);
});

// ── Disabled triggers ──────────────────────────────────────────────────

test('disabled trigger ## is validated', () => {
  const diags = validateDocument('##disabled:!cmd');
  const errors = diags.filter(d => d.severity === 1);
  assert.strictEqual(errors.length, 0); // valid disabled trigger
});

test('disabled trigger with ## and duplicate', () => {
  const diags = validateDocument('##dup:/a\ndup:/b');
  assert.strictEqual(countByCode(diags, 'duplicate_trigger'), 1);
});

// ── Robustness ─────────────────────────────────────────────────────────

test('malformed file does not crash', () => {
  const diags = validateDocument(':\n  \n:::');
  assert.ok(Array.isArray(diags));
});

test('incomplete line while typing', () => {
  const diags = validateDocument('test:');
  assert.strictEqual(countByCode(diags, 'no_content_after_colon'), 1);
});

test('empty document', () => {
  const diags = validateDocument('');
  assert.strictEqual(diags.length, 0);
});

// ── Real-world examples ────────────────────────────────────────────────

test('default actions.mca has no errors', () => {
  const text = (
    "follow:/give @a minecraft:golden_apple 7 ; >>New Follower!|{user} is now following you!|5\n" +
    "likes:/execute at @a run summon minecraft:creeper ~ ~ ~ x2\n" +
    "like_2:/clear @a * ; /kill @a\n" +
    "5655:!tnt 2 0.1 2 Notch\n" +
    "16111:/give @a minecraft:diamond\n" +
    "8913:/execute at @a run summon minecraft:evoker ~ ~ ~ x3\n" +
    "6267:!tnt 600 0.1 2 Notch\n" +
    "7168:/execute at @a run summon minecraft:wither ~ ~ ~ x50\n" +
    "16071:$random\n" +
    "'Tom the Tomato':$random\n" +
    "16379:$random\n"
  );
  const diags = validateDocument(text);
  const errors = diags.filter(d => d.severity === 1);
  assert.strictEqual(errors.length, 0, `Unexpected errors: ${JSON.stringify(errors)}`);
});

console.log('\nValidator tests complete.\n');
