// Test runner for MCA language server modules.
// Usage: node test/run.js

console.log('=== MCA Language Server Tests ===\n');

require('./test_spec');
require('./test_parser');
require('./test_validator');
require('./test_completions');
require('./test_hover');

console.log('\n=== All tests completed ===\n');

if (process.exitCode) {
  console.log('Some tests FAILED.');
} else {
  console.log('All tests PASSED.');
}
