// Standalone JS validator runner for differential testing.
// Called by tools/diff_test_mca.py via subprocess.
//
// Usage: node test/run_validator.js '<json-escaped-mca-text>'
// Outputs: JSON array of diagnostics to stdout.

const { validateDocument } = require('../src/validator');

const input = process.argv[2];
if (!input) {
  console.error('Usage: node run_validator.js "<text>"');
  process.exit(1);
}

let text;
try {
  text = JSON.parse(input);
} catch (e) {
  // If not valid JSON, treat as raw string
  text = input;
}

const diagnostics = validateDocument(text);

// Output normalized diagnostics matching Python format
const results = diagnostics.map(d => ({
  line: d.range.start.line,
  start_char: d.range.start.character,
  end_char: d.range.end.character,
  message: d.message,
  severity: d.severity === 1 ? 'ERROR' : d.severity === 2 ? 'WARNING' : 'INFO',
  code: d.code,
}));

console.log(JSON.stringify(results));
