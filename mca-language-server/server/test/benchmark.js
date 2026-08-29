// Performance benchmark for MCA language server validation.
//
// Tests with 100, 500, 1000, 5000 triggers and measures validation time.

const { validateDocument } = require('../src/validator');

function generateMCA(numTriggers) {
  const lines = [];
  const prefixes = ['/', '!', '$', '&', '>>', '@screen>>'];
  const commands = [
    'say hello',
    'give @a diamond',
    'execute at @a run summon creeper ~ ~ ~',
    'clear @a *',
    'kill @a',
    'tp @a ~ ~5 ~',
    'tnt 2 0.1 2 Notch',
    'random',
    'curl http://localhost:29191/add',
    'Welcome!|{user} joined!|5',
    'Title|Subtitle|3',
  ];
  const multipliers = ['', ' x5', ' x10', ' x50'];

  lines.push('# MCA Benchmark File');
  lines.push('# Generated for performance testing');
  lines.push('');

  for (let i = 0; i < numTriggers; i++) {
    const name = `trigger_${i}`;
    const numCmds = (i % 3) + 1;
    const cmdParts = [];

    for (let j = 0; j < numCmds; j++) {
      const prefix = prefixes[(i + j) % prefixes.length];
      const body = commands[(i + j) % commands.length];
      let cmd = prefix + body;
      const mult = multipliers[(i + j) % multipliers.length];
      if (mult && !prefix.startsWith('>')) {
        cmd += mult;
      }
      cmdParts.push(cmd);
    }

    lines.push(`${name}:${cmdParts.join(' ; ')}`);
  }

  return lines.join('\n');
}

function benchmark(size) {
  const text = generateMCA(size);

  // Warmup
  for (let w = 0; w < 3; w++) {
    validateDocument(text);
  }

  const runs = 10;
  const times = [];

  for (let r = 0; r < runs; r++) {
    const start = process.hrtime.bigint();
    const results = validateDocument(text);
    const end = process.hrtime.bigint();
    const ms = Number(end - start) / 1e6;
    times.push(ms);
  }

  const avg = times.reduce((a, b) => a + b, 0) / times.length;
  const min = Math.min(...times);
  const max = Math.max(...times);

  return { size, avg: avg.toFixed(2), min: min.toFixed(2), max: max.toFixed(2), lines: text.split('\n').length };
}

console.log('=== MCA Validator Performance Benchmark ===\n');
console.log('Size    | Lines  | Avg (ms) | Min (ms) | Max (ms)');
console.log('--------|--------|----------|----------|----------');

const sizes = [100, 500, 1000, 2000, 5000];
for (const size of sizes) {
  const result = benchmark(size);
  console.log(
    `${String(result.size).padStart(7)} | ${String(result.lines).padStart(6)} | ${result.avg.padStart(8)} | ${result.min.padStart(8)} | ${result.max.padStart(8)}`
  );
}

console.log('\nBenchmark complete.');
