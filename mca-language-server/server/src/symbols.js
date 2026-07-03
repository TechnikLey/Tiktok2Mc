// Document symbols, folding ranges, and selection ranges for MCA files.
//
// Document symbols: each trigger (active or disabled) is a top-level symbol.
// Folding ranges: comment blocks and disabled trigger sections.
// Selection ranges: whole trigger lines.

const { parseLine } = require('./parser');

const SymbolKind = {
  Function: 12,
  Variable: 13,
  Constant: 14,
  String: 15,
  Number: 16,
  Field: 8,
};

/**
 * Extract document symbols for outline / go-to-symbol.
 */
function provideDocumentSymbols(document) {
  const text = document.getText();
  const lines = text.split('\n');
  const symbols = [];

  for (let i = 0; i < lines.length; i++) {
    try {
      const rawLine = lines[i];
      const stripped = rawLine.trim();

      // Comment lines — skip for symbols (handled by folding)
      if (stripped.startsWith('#') && !stripped.startsWith('##')) continue;

      const result = parseLine(rawLine, i);
      if (!result || result.isError) continue;

      let name = result.trigger;
      let kind = SymbolKind.Function;
      let detail = 'Trigger';

      if (result.isDisabled) {
        detail = 'Disabled Trigger';
        kind = SymbolKind.Constant;
      }

      if (KNOWN_EVENT_TRIGGERS_NAMES && KNOWN_EVENT_TRIGGERS_NAMES.has(name)) {
        detail = 'Event Trigger';
        kind = SymbolKind.Field;
      } else if (/^\d+$/.test(name)) {
        detail = 'Gift Trigger';
        kind = SymbolKind.Number;
      }

      symbols.push({
        name,
        kind,
        detail,
        range: {
          start: { line: i, character: 0 },
          end: { line: i, character: rawLine.length },
        },
        selectionRange: {
          start: { line: i, character: result.triggerGlobalStart },
          end: { line: i, character: result.triggerGlobalStart + result.trigger.length },
        },
      });
    } catch (err) {
      // skip lines that fail to parse
    }
  }

  return symbols;
}

// Lazy-init for the known triggers set
let KNOWN_EVENT_TRIGGERS_NAMES = null;
function getKnownTriggerNames() {
  if (!KNOWN_EVENT_TRIGGERS_NAMES) {
    const { KNOWN_EVENT_TRIGGERS } = require('./language');
    KNOWN_EVENT_TRIGGERS_NAMES = new Set(KNOWN_EVENT_TRIGGERS.map(t => t.name));
  }
  return KNOWN_EVENT_TRIGGERS_NAMES;
}

/**
 * Provide folding ranges for comment blocks and disabled trigger sections.
 */
function provideFoldingRanges(document) {
  const text = document.getText();
  const lines = text.split('\n');
  const ranges = [];

  let commentStart = -1;

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();

    if (trimmed.startsWith('#') && !trimmed.startsWith('##')) {
      if (commentStart < 0) commentStart = i;
    } else {
      if (commentStart >= 0 && i - commentStart > 1) {
        ranges.push({
          startLine: commentStart,
          endLine: i - 1,
          kind: 'comment',
        });
      }
      commentStart = -1;
    }
  }

  // Close last comment block
  if (commentStart >= 0 && lines.length - commentStart > 1) {
    ranges.push({
      startLine: commentStart,
      endLine: lines.length - 1,
      kind: 'comment',
    });
  }

  return ranges;
}

/**
 * Provide selection ranges to support Shift+click selection.
 */
function provideSelectionRanges(document) {
  const text = document.getText();
  const lines = text.split('\n');
  const ranges = [];

  for (let i = 0; i < lines.length; i++) {
    try {
      const result = parseLine(lines[i], i);
      if (result && !result.isError) {
        ranges.push([{
          start: { line: i, character: 0 },
          end: { line: i, character: lines[i].length },
        }]);
      }
    } catch (err) {
      // Skip
    }
  }

  return ranges;
}

module.exports = { provideDocumentSymbols, provideFoldingRanges, provideSelectionRanges };
