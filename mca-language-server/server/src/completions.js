// Completion provider for MCA files.
//
// Provides context-aware completions:
//   - Trigger names (event triggers, gift IDs, custom names)
//   - Command prefixes (/, !, $, &, >>)
//   - Known script names
//   - Placeholders ({user}, {comment})
//   - Multiplier syntax
//   - Snippets for common patterns

const {
  COMMAND_PREFIXES, KNOWN_EVENT_TRIGGERS, PLACEHOLDERS, SNIPPETS,
} = require('./language');

const CompletionItemKind = {
  Keyword: 14,
  Snippet: 15,
  Value: 13,
  Function: 2,
  Constant: 9,
  Class: 5,
  Property: 10,
  Operator: 20,
};

/**
 * Determine context from position in the line.
 */
function getContext(line, character) {
  const before = line.slice(0, character);
  
  // Check if we're before the colon (trigger name area)
  const colonIdx = line.indexOf(':');
  
  // Check if we're in a comment
  const hashIdx = line.indexOf('#');
  if (hashIdx >= 0 && hashIdx < character && !before.includes(':')) {
    return { type: 'comment' };
  }

  if (colonIdx < 0 || character <= colonIdx + 1) {
    // Before or at the colon -- trigger name area
    const triggerPart = colonIdx >= 0 ? line.slice(0, colonIdx) : line.slice(0, character);
    const afterColon = colonIdx >= 0 ? line.slice(colonIdx + 1, character) : '';
    return { type: 'trigger', triggerPart, afterColon };
  }

  // After colon -- command area
  const afterColon = line.slice(colonIdx + 1, character);
  const cmdPart = line.slice(colonIdx + 1);

  // Check if just after a semicolon (new command)
  const lastSemi = afterColon.lastIndexOf(';');
  const currentCmd = lastSemi >= 0 ? afterColon.slice(lastSemi + 1).trim() : afterColon.trim();

  // Check if we're at the end of a command (multiplier area)
  const atEnd = character >= line.length || /^\s*$/.test(line.slice(character));

  // Detect if cursor is right after a prefix character
  if (currentCmd === '' && (afterColon.endsWith('/') || afterColon.endsWith('!') || 
      afterColon.endsWith('$') || afterColon.endsWith('&') || afterColon.endsWith('>'))) {
    const prefixChar = currentCmd === '' ? afterColon.trimEnd().slice(-1) : '';
    if (prefixChar === '>') {
      return { type: 'overlay_body', cmdPart: currentCmd };
    }
    return { type: 'command_body', prefix: prefixChar, cmdPart: currentCmd };
  }

  // Detect multiplier context (end of command, space before)
  if (atEnd && currentCmd.length > 0 && /\s$/.test(afterColon)) {
    return { type: 'multiplier', cmdPart: currentCmd };
  }

  // In the middle of a command
  if (currentCmd.length > 0) {
    // Check for { placeholder
    if (currentCmd.endsWith('{')) {
      return { type: 'placeholder', cmdPart: currentCmd };
    }
    return { type: 'command_body', cmdPart: currentCmd };
  }

  // Start of command area
  return { type: 'command_start', cmdPart: '' };
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
      // -- Trigger name completions ---------------------------------------
      // Event triggers
      for (const t of KNOWN_EVENT_TRIGGERS) {
        completions.push({
          label: t.name,
          kind: CompletionItemKind.Keyword,
          detail: 'Event trigger',
          documentation: t.doc,
          insertText: `${t.name}:`,
        });
      }

      // Add common gift ID examples (from defaults/actions.mca)
      const giftExamples = [
        { id: '5655', name: 'Rose' },
        { id: '16111', name: 'Mamma Mia' },
        { id: '8913', name: 'Rosa' },
        { id: '6267', name: 'Corgi' },
        { id: '7168', name: 'Money Gun' },
        { id: '16071', name: 'Flower Show' },
      ];
      for (const g of giftExamples) {
        completions.push({
          label: g.id,
          kind: CompletionItemKind.Value,
          detail: `Gift: ${g.name}`,
          documentation: `Gift ID for ${g.name}`,
          insertText: `${g.id}:`,
        });
      }

      // Quoted trigger suggestion
      completions.push({
        label: "'quoted trigger'",
        kind: CompletionItemKind.Snippet,
        detail: 'Trigger with spaces',
        documentation: 'Use single quotes for trigger names containing spaces.',
        insertText: "'${1:trigger name}':",
      });

      // Snippets
      for (const s of SNIPPETS) {
        completions.push({
          label: s.label,
          kind: CompletionItemKind.Snippet,
          detail: 'Snippet',
          documentation: s.doc,
          insertText: s.insertText,
          insertTextFormat: 2, // SnippetTextFormat
        });
      }
    } else if (ctx.type === 'command_start' || ctx.type === 'command_body') {
      // -- Command prefix completions -------------------------------------
      for (const [prefix, info] of Object.entries(COMMAND_PREFIXES)) {
        completions.push({
          label: prefix,
          kind: CompletionItemKind.Operator,
          detail: info.label,
          documentation: info.doc,
          insertText: prefix,
        });
      }

      // Script names (known scripts from the Python hook system)
      completions.push({
        label: '$random',
        kind: CompletionItemKind.Function,
        detail: 'Built-in script: random trigger',
        documentation: 'Executes the commands of a randomly selected trigger from the file. Configured via random/config.yaml.',
        insertText: '$random',
      });

      // Named overlay prefix
      completions.push({
        label: '@name>>',
        kind: CompletionItemKind.Operator,
        detail: 'Named overlay',
        documentation: 'Send overlay text to a specific named overlay screen.',
        insertText: '@${1:screenName}>>',
        insertTextFormat: 2,
      });

      // Placeholders
      for (const p of PLACEHOLDERS) {
        completions.push({
          label: p.name,
          kind: CompletionItemKind.Constant,
          detail: 'Placeholder',
          documentation: p.doc,
          insertText: p.name,
        });
      }
    } else if (ctx.type === 'overlay_body') {
      // -- Overlay body hints --------------------------------------------
      completions.push({
        label: 'Title|Subtitle|Duration',
        kind: CompletionItemKind.Snippet,
        detail: 'Overlay format',
        documentation: '>>Title|Subtitle|Duration\n- Title: Main text (large)\n- Subtitle: Subtext (small, optional)\n- Duration: seconds (optional, default: 3)',
        insertText: '${1:Title}|${2:Subtitle}|${3:3}',
        insertTextFormat: 2,
      });

      for (const p of PLACEHOLDERS) {
        completions.push({
          label: p.name,
          kind: CompletionItemKind.Constant,
          detail: 'Placeholder',
          documentation: p.doc,
          insertText: p.name,
        });
      }
    } else if (ctx.type === 'multiplier') {
      // -- Multiplier completions ----------------------------------------
      for (const n of [2, 3, 5, 10, 25, 50, 100]) {
        completions.push({
          label: `x${n}`,
          kind: CompletionItemKind.Value,
          detail: `Repeat ${n} times`,
          documentation: n > 50 ? 'High multiplier — may cause lag. Add # ignore-lag to suppress warning.' : '',
          insertText: `x${n}`,
        });
      }
    } else if (ctx.type === 'placeholder') {
      // -- Placeholder completions ---------------------------------------
      for (const p of PLACEHOLDERS) {
        completions.push({
          label: p.name,
          kind: CompletionItemKind.Constant,
          detail: 'Placeholder',
          documentation: p.doc,
          insertText: p.name,
        });
      }
    }
  } catch (err) {
    // Fallback: return basic completions even on error
    for (const prefix of Object.keys(COMMAND_PREFIXES)) {
      completions.push({
        label: prefix,
        kind: CompletionItemKind.Operator,
        insertText: prefix,
      });
    }
  }

  return completions;
}

function resolveCompletion(item) {
  // Enrich item if needed
  return item;
}

module.exports = { provideCompletions, resolveCompletion };
