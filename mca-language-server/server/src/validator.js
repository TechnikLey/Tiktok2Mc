// Validator – mirrors src/core/validator.py in the Python codebase.
//
// Produces an array of diagnostic objects matching the VS Code diagnostic
// format (severity, range, message, code, source).

const {
  COMMAND_PREFIXES, NAMED_OVERLAY_RE, TRIGGER_NAME_RE,
  QUOTED_TRIGGER_RE, MULTIPLIER_RE, VALID_PREFIX_CHARS,
} = require('./language');
const { parseLine } = require('./parser');

const DiagnosticSeverity = {
  Error: 1,
  Warning: 2,
  Information: 3,
  Hint: 4,
};

function diag(line, startChar, endChar, message, severity, code) {
  return {
    severity,
    range: {
      start: { line, character: startChar },
      end: { line, character: endChar },
    },
    message,
    code,
    source: 'mca',
  };
}

function validateDocument(text) {
  const diagnostics = [];
  const lines = text.split('\n');
  const seenTriggers = new Set();

  for (let lineNumber = 0; lineNumber < lines.length; lineNumber++) {
    try {
      const rawLine = lines[lineNumber];
      const result = parseLine(rawLine, lineNumber);

      if (!result) continue; // comment / empty line

      if (result.isError) {
        diagnostics.push(diag(
          lineNumber, result.errorStart, result.errorEnd,
          result.errorMessage, DiagnosticSeverity.Error, result.errorCode
        ));
        continue;
      }

      const base = result.baseOffset;
      const ln = lineNumber;

      // -- 1. Space after colon (WARNING) -------------------------------
      if (result.hasContentAfterColon) {
        const charAfter = result.lineWithoutComment[result.colonRelIndex + 1];
        if (charAfter === ' ' || charAfter === '\t') {
          diagnostics.push(diag(
            ln, result.colonIndex + 1, result.colonIndex + 2,
            'Space after colon is unusual (expected \'trigger:command\' without space).',
            DiagnosticSeverity.Warning, 'space_after_colon'
          ));
        }
      } else {
        // No content after colon
        diagnostics.push(diag(
          ln, result.colonIndex, result.colonIndex + 1,
          'No content after \':\' (no commands).',
          DiagnosticSeverity.Error, 'no_content_after_colon'
        ));
        continue;
      }

      // -- 2. Trailing colons (ERROR) -----------------------------------
      const colonCount = result.lineWithoutComment.split(':').length - 1;
      if (colonCount > 1 && result.lineWithoutComment.trimEnd().endsWith(':')) {
        const lastColon = base + result.lineWithoutComment.lastIndexOf(':');
        diagnostics.push(diag(
          ln, lastColon, base + result.lineWithoutComment.length,
          'Trailing colon at end of command.',
          DiagnosticSeverity.Error, 'trailing_colons'
        ));
      }

      // -- 3. Trailing semicolon (INFO) ---------------------------------
      if (/;\s*$/.test(result.lineWithoutComment)) {
        const lastSc = base + result.lineWithoutComment.lastIndexOf(';');
        diagnostics.push(diag(
          ln, lastSc, lastSc + 1,
          'Unnecessary semicolon at end of line.',
          DiagnosticSeverity.Information, 'trailing_semicolon'
        ));
      }

      // -- 4. Bracket balance (ERROR) -----------------------------------
      let square = 0, curly = 0;
      let inSingle = false, inDouble = false;
      const lwc = result.lineWithoutComment;

      for (let i = 0; i < lwc.length; i++) {
        const ch = lwc[i];
        if (ch === '\\' && i + 1 < lwc.length) { i++; continue; }
        if (ch === "'" && !inDouble) { inSingle = !inSingle; continue; }
        if (ch === '"' && !inSingle) { inDouble = !inDouble; continue; }
        if (inSingle || inDouble) continue;

        if (ch === '[') square++;
        else if (ch === ']') {
          square--;
          if (square < 0) {
            diagnostics.push(diag(ln, base + i, base + i + 1,
              'Unmatched closing square bracket \']\'.',
              DiagnosticSeverity.Error, 'unmatched_close_square'));
            square = 0;
          }
        } else if (ch === '{') curly++;
        else if (ch === '}') {
          curly--;
          if (curly < 0) {
            diagnostics.push(diag(ln, base + i, base + i + 1,
              'Unmatched closing curly bracket \'}\'.',
              DiagnosticSeverity.Error, 'unmatched_close_curly'));
            curly = 0;
          }
        }
      }

      if (square > 0) {
        diagnostics.push(diag(ln, 0, base + lwc.length,
          'Unbalanced opening square bracket \'[\' (check selectors!).',
          DiagnosticSeverity.Error, 'unbalanced_square'));
      }
      if (curly > 0) {
        diagnostics.push(diag(ln, 0, base + lwc.length,
          'Unbalanced opening curly bracket \'{\' (check NBT data!).',
          DiagnosticSeverity.Error, 'unbalanced_curly'));
      }

      // -- 5. Trigger name validation (ERROR) ---------------------------
      const isValidName = result.triggerIsQuoted
        ? QUOTED_TRIGGER_RE.test(result.trigger)
        : TRIGGER_NAME_RE.test(result.trigger);

      if (!isValidName) {
        const msg = result.triggerIsQuoted
          ? 'Invalid quoted trigger (allowed: A-Z, a-z, 0-9, _, space, inside single quotes).'
          : 'Invalid trigger name (allowed: A-Z, a-z, 0-9, _). For spaces, wrap the trigger in single quotes.';
        diagnostics.push(diag(ln, result.triggerGlobalStart,
          result.triggerGlobalStart + result.trigger.length,
          msg, DiagnosticSeverity.Error, 'invalid_trigger_name'));
      }

      // -- 6. Duplicate trigger (ERROR) ---------------------------------
      if (seenTriggers.has(result.trigger)) {
        diagnostics.push(diag(ln, result.triggerGlobalStart,
          result.triggerGlobalStart + result.trigger.length,
          `Duplicate trigger: '${result.trigger}' defined multiple times.`,
          DiagnosticSeverity.Error, 'duplicate_trigger'));
      }
      seenTriggers.add(result.trigger);

      // -- 7. Command validation ----------------------------------------
      const cmdStr = result.lineWithoutComment.slice(result.colonRelIndex + 1);

      for (let ci = 0; ci < result.commands.length; ci++) {
        const cmd = result.commands[ci];

        if (cmd.isEmpty) {
          if (ci < result.commands.length - 1) {
            diagnostics.push(diag(ln, cmd.startChar, cmd.startChar + 1,
              'Empty command block (double semicolon?).',
              DiagnosticSeverity.Warning, 'empty_command_block'));
          }
          continue;
        }

        const t = cmd.text;

        // Detect prefix
        const isOverlay = t.startsWith('>>') || NAMED_OVERLAY_RE.test(t);

        if (isOverlay) {
          // {comment} placeholder check
          if (t.includes('{comment}') && result.trigger.toLowerCase() !== 'comment') {
            const phPos = cmd.startChar + t.indexOf('{comment}');
            diagnostics.push(diag(ln, phPos, phPos + '{comment}'.length,
              '\'{comment}\' is only resolved for the \'comment\' trigger. It will not be replaced for other triggers.',
              DiagnosticSeverity.Error, 'comment_placeholder_wrong_trigger'));
          }

          // Multiplier on overlay
          const multOv = t.match(MULTIPLIER_RE);
          if (multOv) {
            const token = `x${multOv[1]}`;
            const tokPos = cmd.startChar + t.lastIndexOf(token);
            diagnostics.push(diag(ln, tokPos, tokPos + token.length,
              'Multiplier is not allowed on overlay commands (>> or @name>>).',
              DiagnosticSeverity.Error, 'overlay_multiplier'));
          }
        } else {
          const firstChar = t[0];
          if (firstChar === '@') {
            // Could be named overlay but didn't match -- check
            if (!NAMED_OVERLAY_RE.test(t)) {
              diagnostics.push(diag(ln, cmd.startChar, cmd.endChar,
                'Invalid overlay prefix — expected @name>>.',
                DiagnosticSeverity.Error, 'invalid_prefix'));
            }
          } else if (!VALID_PREFIX_CHARS.includes(firstChar)) {
            diagnostics.push(diag(ln, cmd.startChar, cmd.endChar,
              `Each command must start with '/', '$', '!', '&' or '>>' (found: '${firstChar}').`,
              DiagnosticSeverity.Error, 'invalid_prefix'));
          }
        }

        // -- 8. Multiplier validation -----------------------------------
        const mm = t.match(MULTIPLIER_RE);
        if (mm) {
          const amount = parseInt(mm[1], 10);
          const xToken = `x${amount}`;
          const xPos = cmd.startChar + t.lastIndexOf(xToken);

          if (amount > 50 && !result.rawLine.includes('# ignore-lag')) {
            diagnostics.push(diag(ln, xPos, xPos + xToken.length,
              `Performance warning: x${amount} is very high.`,
              DiagnosticSeverity.Warning, 'high_multi'));
          }
        } else {
          // Check for invalid multiplier (x followed by non-numeric)
          const badMult = t.match(/\s+x([^\s]+)\s*$/);
          if (badMult && !/^\d+$/.test(badMult[1])) {
            const token = `x${badMult[1]}`;
            const tokPos = cmd.startChar + t.lastIndexOf(token);
            diagnostics.push(diag(ln, tokPos, tokPos + token.length,
              `Invalid multiplier '${badMult[1]}' (use xNumber).`,
              DiagnosticSeverity.Error, 'invalid_multiplier'));
          }
        }
      }
    } catch (err) {
      // Robustness: never crash the language server
      diagnostics.push(diag(
        lineNumber, 0, Math.max(1, lines[lineNumber].length),
        `Internal error: ${err.message}`,
        DiagnosticSeverity.Error, 'internal_error'
      ));
    }
  }

  return diagnostics;
}

module.exports = { validateDocument, DiagnosticSeverity, diag };
