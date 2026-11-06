/**
 * @file Document symbols and folding ranges for MCA files.
 *
 * Each active or disabled trigger becomes a symbol; consecutive full-line
 * comments become foldable comment blocks.
 */

const { parseLine } = require('./parser');

const SymbolKind = {
  Function: 12,
  Constant: 14,
  Number: 16,
  Field: 8,
};

let KNOWN_SET = null;
/**
 * Return the cached set of known event trigger names.
 *
 * The set is built lazily so the language module can fail without preventing
 * the server from starting.
 *
 * @returns {Set<string>} Known event trigger names.
 */
function getKnownSet() {
  if (!KNOWN_SET) {
    const { getEventTriggers } = require('./language');
    KNOWN_SET = new Set(getEventTriggers());
  }
  return KNOWN_SET;
}

/**
 * Build outline/document symbols for every trigger in a document.
 *
 * Event triggers, numeric gift IDs and custom triggers receive different
 * symbol kinds; disabled (`##`) triggers are included as constants. Malformed
 * lines are skipped so the outline always remains usable.
 *
 * @param {import('vscode-languageserver-textdocument').TextDocument} document
 *   Open document to inspect.
 * @returns {object[]} LSP `DocumentSymbol` objects in source order.
 */
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
      // Skip if trigger name is empty (invalid line like ':command')
      if (!name) continue;

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

/**
 * Build folding ranges for blocks of consecutive comment lines.
 *
 * Single comment lines are not foldable.
 *
 * @param {import('vscode-languageserver-textdocument').TextDocument} document
 *   Open document to inspect.
 * @returns {Array<{startLine: number, endLine: number, kind: string}>} LSP
 *   folding ranges.
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
