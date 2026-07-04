const assert = require('assert');
const { provideCompletions, resolveCompletion } = require('../src/completions');

// Mock TextDocument
function makeDoc(text) {
  return {
    getText: () => text,
  };
}

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

test('provides trigger name completions before colon', () => {
  const doc = makeDoc('');
  const results = provideCompletions(doc, { line: 0, character: 0 });
  const labels = results.map(r => r.label);
  assert.ok(labels.includes('follow'));
  assert.ok(labels.includes('comment'));
  assert.ok(!labels.includes('likes'));
});

test('provides trigger name completions at trigger area', () => {
  const doc = makeDoc('f');
  const results = provideCompletions(doc, { line: 0, character: 1 });
  const labels = results.map(r => r.label);
  assert.ok(labels.includes('follow'));
});

test('provides command prefix completions after colon', () => {
  const doc = makeDoc('test:');
  const results = provideCompletions(doc, { line: 0, character: 6 });
  const labels = results.map(r => r.label);
  assert.ok(labels.includes('/'));
  assert.ok(labels.includes('$'));
  assert.ok(labels.includes('!'));
  assert.ok(labels.includes('&'));
  assert.ok(labels.includes('>>'));
});

test('provides placeholder completions', () => {
  const doc = makeDoc('test:>>say {');
  const results = provideCompletions(doc, { line: 0, character: 11 });
  const labels = results.map(r => r.label);
  assert.ok(labels.includes('{user}'));
  assert.ok(labels.includes('{comment}'));
});

test('provides $random script completion', () => {
  const doc = makeDoc('test:$');
  const results = provideCompletions(doc, { line: 0, character: 6 });
  const labels = results.map(r => r.label);
  assert.ok(labels.includes('$random'));
});

test('provides multiplier completions at end of command', () => {
  const doc = makeDoc('test:/cmd ');
  const results = provideCompletions(doc, { line: 0, character: 10 });
  const labels = results.map(r => r.label);
  assert.ok(labels.includes('x2'));
  assert.ok(labels.includes('x5'));
  assert.ok(labels.includes('x10'));
});

test('provides named overlay completion after @', () => {
  const doc = makeDoc('test:@');
  const results = provideCompletions(doc, { line: 0, character: 6 });
  const labels = results.map(r => r.label);
  assert.ok(labels.some(l => l.includes('screenName')));
});

test('resolveCompletion returns item unchanged', () => {
  const item = { label: 'test' };
  const resolved = resolveCompletion(item);
  assert.strictEqual(resolved, item);
});

console.log('\nCompletions tests complete.\n');
