// Document symbols, folding ranges for MCA files.
//
// Document symbols: each trigger (active or disabled) is a symbol node.
// Folding ranges: comment blocks.

const { parseLine } = require('./parser');

const SymbolKind = {
  Function: 12,
  Constant: 14,
  Number: 16,
  Field: 8,
};

let KNOWN_SET = null;
function getKnownSet() {
  if (!KNOWN_SET) {
    const { getEventTriggers } = require('./language');
    KNOWN_SET = new Set(getEventTriggers());
  }
  return KNOWN_SET;
}

function provideDocumentSymbols(document) {
  const text = document.getText();
  const lines = text.split('\n');
  const symbols = [];

  for (let i = 0; i < lines.length; i++) {
    try {
      const rawLine = lines[i];
      const stripped = rawLine.trim();
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

      if (getKnownSet().has(name)) {
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
      // skip
    }
  }

  return symbols;
}

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
        ranges.push({ startLine: commentStart, endLine: i - 1, kind: 'comment' });
      }
      commentStart = -1;
    }
  }

  if (commentStart >= 0 && lines.length - commentStart > 1) {
    ranges.push({ startLine: commentStart, endLine: lines.length - 1, kind: 'comment' });
  }

  return ranges;
}

module.exports = { provideDocumentSymbols, provideFoldingRanges };
