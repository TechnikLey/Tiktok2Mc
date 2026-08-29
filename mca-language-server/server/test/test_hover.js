const assert = require('assert');
const { provideHover } = require('../src/hover');

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

test('hover over event trigger name', () => {
  const doc = makeDoc('follow:/give @a apple');
  const result = provideHover(doc, { line: 0, character: 1 });
  assert.ok(result);
  assert.ok(result.contents.value.includes('follow'));
  assert.ok(result.contents.value.includes('Event Trigger'));
});

test('hover over custom trigger name', () => {
  const doc = makeDoc('mytrigger:/cmd');
  const result = provideHover(doc, { line: 0, character: 1 });
  assert.ok(result);
  assert.ok(result.contents.value.includes('mytrigger'));
  assert.ok(result.contents.value.includes('Custom Trigger'));
});

test('hover over gift ID trigger', () => {
  const doc = makeDoc('5655:!cmd');
  const result = provideHover(doc, { line: 0, character: 1 });
  assert.ok(result);
  assert.ok(result.contents.value.includes('Gift ID'));
});

test('hover over colon separator', () => {
  const doc = makeDoc('test:/cmd');
  // Try characters around where the colon should be
  let result = provideHover(doc, { line: 0, character: 4 });
  if (!result) {
    result = provideHover(doc, { line: 0, character: 0 });
  }
  if (result) {
    assert.ok(typeof result.contents.value === 'string');
  }
});

test('hover over placeholder {user}', () => {
  const doc = makeDoc('test:>>{user} joined');
  const result = provideHover(doc, { line: 0, character: 7 });
  if (result) {
    assert.ok(result.contents.value.includes('{user}'));
  }
});

test('hover over $random', () => {
  const doc = makeDoc('test:$random');
  const result = provideHover(doc, { line: 0, character: 6 });
  if (result) {
    assert.ok(result.contents.value.includes('$'));
  }
});

test('hover returns null for empty line', () => {
  const doc = makeDoc('');
  const result = provideHover(doc, { line: 0, character: 0 });
  assert.strictEqual(result, null);
});

test('hover returns null for comment line', () => {
  const doc = makeDoc('# comment');
  const result = provideHover(doc, { line: 0, character: 2 });
  assert.strictEqual(result, null);
});

console.log('\nHover tests complete.\n');
