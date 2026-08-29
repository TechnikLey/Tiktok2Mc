// Completion provider for MCA files.
//
// Provides context-aware completions derived from the shared mca-spec.json
// (generated from the Python implementation).

const {
  getEventTriggers, getEventTriggerDocs, getCommandPrefixes,
  getPlaceholders, getRules, NAMED_OVERLAY_RE,
} = require('./language');

const CompletionItemKind = {
  Keyword: 14,
  Snippet: 15,
  Value: 13,
  Function: 2,
  Constant: 9,
  Operator: 20,
};

// Priority scores for sorting completions (higher = more relevant)
const PRIORITY = {
  EXACT_MATCH: 100,
  PREFIX_MATCH: 80,
  CONTEXT_TRIGGER: 70,
  CONTEXT_COMMAND: 60,
  CONTEXT_SCRIPT: 55,
  CONTEXT_PLACEHOLDER: 50,
  CONTEXT_MULTIPLIER: 45,
  SNIPPET: 30,
  GENERIC: 10,
};

/**
 * Determine context from position in the line.
 */
function getContext(line, character) {
  const before = line.slice(0, character);

  const hashIdx = line.indexOf('#');
  if (hashIdx >= 0 && hashIdx < character && !before.includes(':')) {
    return { type: 'comment' };
  }

  const colonIdx = line.indexOf(':');

  if (colonIdx < 0 || character <= colonIdx) {
    return { type: 'trigger', triggerPart: colonIdx >= 0 ? line.slice(0, colonIdx) : '' };
  }

  const afterColon = line.slice(colonIdx + 1, character);
  const lastSemi = afterColon.lastIndexOf(';');
  const currentCmd = lastSemi >= 0 ? afterColon.slice(lastSemi + 1) : afterColon;

  const atEnd = character >= line.length || /^\s*$/.test(line.slice(character));

  // If cursor is right after $, suggest scripts
  if (currentCmd.trim() === '$') {
    return { type: 'script_name', cmdPart: '' };
  }

  // If cursor is right after @, suggest overlay names
  if (currentCmd.trim() === '@') {
    return { type: 'overlay_name', cmdPart: '' };
  }

  // If cursor is at end after space, suggest multiplier
  if (atEnd && /\s$/.test(afterColon) && currentCmd.trim().length > 0) {
    const lastChar = currentCmd.trimEnd().slice(-1);
    if (lastChar === 'x') {
      return { type: 'multiplier_value', cmdPart: currentCmd.trim() };
    }
    return { type: 'multiplier', cmdPart: currentCmd.trim() };
  }

  // Middle of command — detect prefix for ranking
  const trimmed = currentCmd.trim();
  if (trimmed.startsWith('$')) {
    return { type: 'script_body', cmdPart: trimmed };
  }
  if (trimmed.startsWith('@')) {
    return { type: 'overlay_body', cmdPart: trimmed };
  }
  if (trimmed === '' || trimmed.length === 0) {
    return { type: 'command_start', cmdPart: '' };
  }
  if (trimmed.includes('{')) {
    return { type: 'placeholder', cmdPart: trimmed };
  }

  return { type: 'command_body', cmdPart: trimmed };
}

function provideCompletions(document, position) {
  const text = document.getText();
  const lines = text.split('\n');
  const line = lines[position.line] || '';
  const character = position.character;

  const completions = [];

  try {
    const ctx = getContext(line, character);

    if (ctx.type === 'trigger') {
      // -- Trigger name completions (ranked: event triggers first) ----
      const eventTriggers = getEventTriggers().filter(t => t !== 'likes' && t !== 'like_2');
      const eventDocs = getEventTriggerDocs();
      const docMap = {};
      for (const d of eventDocs) docMap[d.name] = d.doc;

      for (const t of eventTriggers) {
        const priority = line.length <= 1 ? PRIORITY.EXACT_MATCH : PRIORITY.CONTEXT_TRIGGER;
        completions.push({
          label: t,
          kind: CompletionItemKind.Keyword,
          detail: 'Event trigger',
          documentation: docMap[t] || '',
          insertText: `${t}:`,
          data: { priority },
          sortText: String(100000 - priority).padStart(6, '0'),
        });
      }

      // Quoted trigger
      completions.push({
        label: "'quoted trigger'",
        kind: CompletionItemKind.Snippet,
        detail: 'Trigger with spaces',
        insertText: "'${1:trigger name}':",
        insertTextFormat: 2,
        data: { priority: PRIORITY.SNIPPET },
        sortText: String(100000 - PRIORITY.SNIPPET).padStart(6, '0'),
      });
    } else if (ctx.type === 'command_start') {
      // -- Command prefix completions (highest priority at command start) --
      const prefixes = getCommandPrefixes();
      for (const [prefix, info] of Object.entries(prefixes)) {
        completions.push({
          label: prefix,
          kind: CompletionItemKind.Operator,
          detail: info.label,
          documentation: info.doc || '',
          insertText: prefix,
          data: { priority: PRIORITY.EXACT_MATCH },
          sortText: String(100000 - PRIORITY.EXACT_MATCH).padStart(6, '0'),
        });
      }
    } else if (ctx.type === 'script_name' || ctx.type === 'script_body') {
      // -- Script names (highest priority after $) -----------------------
      completions.push({
        label: '$random',
        kind: CompletionItemKind.Function,
        detail: 'Built-in script: random trigger',
        documentation: 'Executes the commands of a randomly selected trigger. Configured via random/config.yaml.',
        insertText: '$random',
        data: { priority: PRIORITY.CONTEXT_SCRIPT },
        sortText: String(100000 - PRIORITY.CONTEXT_SCRIPT).padStart(6, '0'),
      });
    } else if (ctx.type === 'overlay_name') {
      // -- Overlay name suggestions (after @) --------------------------
      completions.push({
        label: 'screenName>>',
        kind: CompletionItemKind.Operator,
        detail: 'Named overlay target',
        documentation: 'Replace screenName with your overlay screen identifier.',
        insertText: '${1:screenName}>>',
        insertTextFormat: 2,
        data: { priority: PRIORITY.EXACT_MATCH },
        sortText: String(100000 - PRIORITY.EXACT_MATCH).padStart(6, '0'),
      });
    } else if (ctx.type === 'multiplier') {
      // -- Multiplier suggestions (ranked by common values) --------------
      const multValues = [
        { n: 2, doc: 'Repeat 2 times' },
        { n: 3, doc: 'Repeat 3 times' },
        { n: 5, doc: 'Repeat 5 times' },
        { n: 10, doc: 'Repeat 10 times' },
        { n: 25, doc: 'Repeat 25 times' },
        { n: 50, doc: 'Repeat 50 times' },
        { n: 100, doc: '⚠️ High — may cause lag. Add # ignore-lag to suppress warning.' },
      ];
      for (const m of multValues) {
        completions.push({
          label: `x${m.n}`,
          kind: CompletionItemKind.Value,
          detail: `${m.n}× repeat`,
          documentation: m.doc,
          insertText: `x${m.n}`,
          data: { priority: PRIORITY.CONTEXT_MULTIPLIER },
          sortText: String(100000 - PRIORITY.CONTEXT_MULTIPLIER + (100 - m.n)).padStart(6, '0'),
        });
      }
    } else if (ctx.type === 'multiplier_value') {
      // After typing "x", suggest just the number
      const multValues = [2, 3, 5, 10, 25, 50, 100];
      for (const n of multValues) {
        completions.push({
          label: String(n),
          kind: CompletionItemKind.Value,
          detail: `${n}× repeat`,
          insertText: String(n),
          data: { priority: PRIORITY.CONTEXT_MULTIPLIER },
          sortText: String(100000 - PRIORITY.CONTEXT_MULTIPLIER + (100 - n)).padStart(6, '0'),
        });
      }
    } else if (ctx.type === 'placeholder') {
      // -- Placeholder completions (only valid in context) --------------
      const placeholders = getPlaceholders();
      for (const p of placeholders) {
        completions.push({
          label: p.name,
          kind: CompletionItemKind.Constant,
          detail: 'Placeholder',
          documentation: p.doc || '',
          insertText: p.name,
          data: { priority: PRIORITY.CONTEXT_PLACEHOLDER },
          sortText: String(100000 - PRIORITY.CONTEXT_PLACEHOLDER).padStart(6, '0'),
        });
      }
    } else if (ctx.type === 'command_body' || ctx.type === 'overlay_body') {
      // -- Inside a command body, suggest placeholders with medium priority
      const placeholders = getPlaceholders();
      for (const p of placeholders) {
        completions.push({
          label: p.name,
          kind: CompletionItemKind.Constant,
          detail: 'Placeholder',
          documentation: p.doc || '',
          insertText: p.name,
          data: { priority: PRIORITY.CONTEXT_PLACEHOLDER },
          sortText: String(100000 - PRIORITY.CONTEXT_PLACEHOLDER).padStart(6, '0'),
        });
      }

      // Overlay body template
      if (ctx.type === 'overlay_body') {
        completions.push({
          label: 'Title|Subtitle|Duration',
          kind: CompletionItemKind.Snippet,
          detail: 'Overlay format',
          documentation: '>>Title|Subtitle|Duration\nTitle: required\nSubtitle: optional\nDuration: seconds (default 3)',
          insertText: '${1:Title}|${2:Subtitle}|${3:3}',
          insertTextFormat: 2,
          data: { priority: PRIORITY.SNIPPET },
          sortText: String(100000 - PRIORITY.SNIPPET).padStart(6, '0'),
        });
      }
    }
  } catch (err) {
    // Fallback: return basic prefix completions
    const prefixes = getCommandPrefixes();
    for (const prefix of Object.keys(prefixes)) {
      completions.push({
        label: prefix,
        kind: CompletionItemKind.Operator,
        insertText: prefix,
        data: { priority: 0 },
        sortText: '999999',
      });
    }
  }

  return completions;
}

function resolveCompletion(item) {
  return item;
}

module.exports = { provideCompletions, resolveCompletion };
