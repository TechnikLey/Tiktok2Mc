const assert = require('assert');
const { parseLine, parseDocument } = require('../src/parser');

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

// ── Parser tests ───────────────────────────────────────────────────────

test('parseLine - empty line', () => {
  assert.strictEqual(parseLine('', 0), null);
});

test('parseLine - full-line comment #', () => {
  assert.strictEqual(parseLine('# comment', 0), null);
});

test('parseLine - full-line comment with leading spaces', () => {
  assert.strictEqual(parseLine('  # comment', 0), null);
});

test('parseLine - disabled trigger ##', () => {
  const r = parseLine('##test:/cmd', 0);
  assert.ok(r);
  assert.strictEqual(r.isDisabled, true);
  assert.strictEqual(r.trigger, 'test');
});

test('parseLine - active trigger', () => {
  const r = parseLine('test:/say hi', 0);
  assert.ok(r);
  assert.strictEqual(r.isDisabled, false);
  assert.strictEqual(r.trigger, 'test');
  assert.strictEqual(r.commands.length, 1);
  assert.strictEqual(r.commands[0].text, '/say hi');
});

test('parseLine - missing colon returns error', () => {
  const r = parseLine('no colon here', 0);
  assert.ok(r);
  assert.strictEqual(r.isError, true);
  assert.strictEqual(r.errorCode, 'missing_colon');
});

test('parseLine - multiple commands with semicolons', () => {
  const r = parseLine('test:/first;/second;/third', 0);
  assert.ok(r);
  assert.strictEqual(r.commands.length, 3);
  assert.strictEqual(r.commands[0].text, '/first');
  assert.strictEqual(r.commands[1].text, '/second');
  assert.strictEqual(r.commands[2].text, '/third');
});

test('parseLine - trailing semicolon', () => {
  const r = parseLine('test:/first;/second;', 0);
  assert.ok(r);
  assert.strictEqual(r.commands.length, 3);
  assert.strictEqual(r.commands[2].isEmpty, true);
});

test('parseLine - inline comment stripped', () => {
  const r = parseLine('test:/say hi # inline comment', 0);
  assert.ok(r);
  assert.ok(r.commentText.includes('inline comment'));
  assert.strictEqual(r.trigger, 'test');
  assert.strictEqual(r.commands.length, 1);
});

test('parseLine - quoted trigger', () => {
  const r = parseLine("'my trigger':/cmd", 0);
  assert.ok(r);
  assert.strictEqual(r.triggerIsQuoted, true);
  assert.strictEqual(r.trigger, "'my trigger'");
});

test('parseLine - disabled quoted trigger', () => {
  const r = parseLine("##'my trigger':/cmd", 0);
  assert.ok(r);
  assert.strictEqual(r.isDisabled, true);
  assert.strictEqual(r.triggerIsQuoted, true);
  assert.strictEqual(r.trigger, "'my trigger'");
});

test('parseLine - overlay command', () => {
  const r = parseLine('test:>>Title|Subtitle|5', 0);
  assert.ok(r);
  assert.strictEqual(r.commands[0].text, '>>Title|Subtitle|5');
});

test('parseLine - named overlay command', () => {
  const r = parseLine('test:@screen>>Title|Subtitle|5', 0);
  assert.ok(r);
  assert.strictEqual(r.commands[0].text, '@screen>>Title|Subtitle|5');
});

test('parseLine - shell command &', () => {
  const r = parseLine('test:&curl http://localhost', 0);
  assert.ok(r);
  assert.strictEqual(r.commands[0].text, '&curl http://localhost');
});

test('parseLine - script command $', () => {
  const r = parseLine('test:$random', 0);
  assert.ok(r);
  assert.strictEqual(r.commands[0].text, '$random');
});

test('parseLine - rcon command !', () => {
  const r = parseLine('test:!tnt 2 0.1 2 Notch', 0);
  assert.ok(r);
  assert.strictEqual(r.commands[0].text, '!tnt 2 0.1 2 Notch');
});

test('parseLine - empty command block (double semicolon)', () => {
  const r = parseLine('test:/first;;/third', 0);
  assert.ok(r);
  assert.strictEqual(r.commands.length, 3);
  assert.strictEqual(r.commands[0].text, '/first');
  assert.strictEqual(r.commands[1].isEmpty, true);
  assert.strictEqual(r.commands[2].text, '/third');
});

test('parseDocument - full file', () => {
  const results = parseDocument(
    '# comment\n' +
    '##disabled:!cmd\n' +
    'likes:/execute at @a run summon creeper ~ ~ ~ x2\n'
  );
  assert.strictEqual(results.length, 2);
  assert.strictEqual(results[0].isDisabled, true);
  assert.strictEqual(results[1].trigger, 'likes');
});

console.log('\nParser tests complete.\n');
