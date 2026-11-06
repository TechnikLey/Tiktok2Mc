/**
 * @file MCA line parser.
 *
 * Mirrors the logic in `src/core/validator.py` (`validate_text`) and
 * `src/core/api/services/actions.py` (`ActionsService.parse`).
 */

const { NAMED_OVERLAY_RE, TRIGGER_NAME_RE, QUOTED_TRIGGER_RE, MULTIPLIER_RE } = require('./language');

/**
 * Parse one line of an `.mca` file.
 *
 * Handles disabled triggers (`##`), full-line comments (`#`) and inline
 * comments, and records absolute character offsets so diagnostics and hover
 * can target the original text. Comment-only and blank lines return `null`.
 *
 * @param {string} rawLine One line of an `.mca` file (without the newline).
 * @param {number} lineNumber Zero-based line number.
 * @returns {object|null} Parsed line data, an error result with `isError`
 *   when the line has no colon, or `null` for comments and blank lines.
 */
function parseLine(rawLine, lineNumber) {
  const trimmed = rawLine.trimEnd();

  // -- Detect disabled trigger (##) and full-line comment (#) ----------
  let isDisabled = false;
  let codeLine; // the line we will actually parse
  let effectiveRaw; // the raw_line as modified by ## stripping (for offset computation)

  {
    const stripped = trimmed.trimStart();
    if (stripped.startsWith('##')) {
      isDisabled = true;
      const lead = trimmed.slice(0, trimmed.length - trimmed.trimStart().length);
      codeLine = lead + stripped.slice(2);
      // Reconstruct effective raw line: same as Python: lead + content_after_##
      effectiveRaw = codeLine;
    } else if (stripped.startsWith('#')) {
      return null;
    } else {
      codeLine = trimmed;
      effectiveRaw = rawLine;
    }
  }

  // -- Strip inline comment --------------------------------------------
  const inlineHash = codeLine.indexOf('#');
  const lineNoComment = inlineHash >= 0 ? codeLine.slice(0, inlineHash) : codeLine;
  const commentText = inlineHash >= 0 ? codeLine.slice(inlineHash) : '';

  if (lineNoComment.trim() === '') return null;

  const baseOffset = codeLine.indexOf(lineNoComment);
  const offset = baseOffset >= 0 ? baseOffset : 0;

  // -- Colon detection --------------------------------------------------
  const colonIndex = lineNoComment.indexOf(':');
  if (colonIndex < 0) {
    return errorResult(lineNumber, 0, Math.max(1, rawLine.length), 'Missing colon: each line must define a trigger.', 'missing_colon');
  }

  const colonGlobal = offset + colonIndex;

  // -- Trigger name -----------------------------------------------------
  const triggerRaw = lineNoComment.slice(0, colonIndex);
  const trigger = triggerRaw.trim();
  const triggerLeadingWS = triggerRaw.length - triggerRaw.trimStart().length;
  const triggerGlobalStart = offset + triggerLeadingWS;

  const isQuoted = trigger.startsWith("'") && trigger.endsWith("'");

  // -- Command part -----------------------------------------------------
  const commandsPart = lineNoComment.slice(colonIndex + 1);
  const commandsGlobalStart = offset + colonIndex + 1;

  // -- Parse individual commands ----------------------------------------
  const commands = [];
  const commandStrings = commandsPart.split(';');
  let cmdGlobalOffset = commandsGlobalStart;

  for (let idx = 0; idx < commandStrings.length; idx++) {
    const rawCmd = commandStrings[idx];
    const trimmedCmd = rawCmd.trim();
    let cmdStartGlobal;

    if (trimmedCmd) {
      // Search in effectiveRaw (may have ## stripped, matching Python behavior)
      const found = effectiveRaw.indexOf(trimmedCmd, cmdGlobalOffset);
      cmdStartGlobal = found >= 0 ? found : cmdGlobalOffset;
    } else {
      cmdStartGlobal = cmdGlobalOffset;
    }

    commands.push({
      raw: rawCmd,
      text: trimmedCmd,
      startChar: cmdStartGlobal,
      endChar: cmdStartGlobal + Math.max(trimmedCmd.length, 1),
      isEmpty: trimmedCmd === '',
    });

    cmdGlobalOffset = cmdStartGlobal + Math.max(trimmedCmd.length, rawCmd.length) + 1;
  }

  return {
    lineNumber,
    rawLine,          // original raw line
    effectiveRaw,     // raw line after ## stripping (for offset lookups, matches Python behavior)
    isDisabled,
    commentText,
    baseOffset: offset,
    colonIndex: colonGlobal,
    colonRelIndex: colonIndex,
    triggerRaw,
    trigger,
    triggerGlobalStart,
    triggerIsQuoted: isQuoted,
    hasContentAfterColon: commandsPart.trim().length > 0,
    commands,
    inlineComment: commentText,
    lineWithoutComment: lineNoComment,
  };
}

/**
 * Build a parse-error result for a malformed line.
 *
 * @param {number} line Zero-based line number.
 * @param {number} startChar Start character offset.
 * @param {number} endChar End character offset.
 * @param {string} message Human-readable error message.
 * @param {string} code Stable error identifier.
 * @returns {object} Error result consumed by the validator.
 */
function errorResult(line, startChar, endChar, message, code) {
  return {
    lineNumber: line,
    isError: true,
    errorStart: startChar,
    errorEnd: endChar,
    errorMessage: message,
    errorCode: code,
  };
}

/**
 * Parse full MCA text into an array of line results.
 *
 * @param {string} text Complete document contents.
 * @returns {object[]} Parsed lines and error results; comment-only and blank
 *   lines are omitted.
 */
function parseDocument(text) {
  const lines = text.split('\n');
  const results = [];
  for (let i = 0; i < lines.length; i++) {
    const parsed = parseLine(lines[i], i);
    if (parsed) results.push(parsed);
  }
  return results;
}

module.exports = { parseLine, parseDocument };
