// MCA line parser.  Mirrors the logic in
// src/core/validator.py (validate_text) and
// src/core/api/services/actions.py (ActionsService.parse).
//
// Each parseLine() call returns a structured object describing one line,
// or null for comment-only / empty lines.

const { NAMED_OVERLAY_RE, TRIGGER_NAME_RE, QUOTED_TRIGGER_RE, MULTIPLIER_RE, VALID_PREFIX_CHARS } = require('./language');

/**
 * @param {string} rawLine  One line of an .mca file (including trailing newline).
 * @param {number} lineNumber  0-based line number.
 * @returns {object|null}
 */
function parseLine(rawLine, lineNumber) {
  const trimmed = rawLine.trimEnd();

  // -- Detect disabled trigger (##) and full-line comment (#) ----------
  let isDisabled = false;
  let codeLine; // the line we will actually parse

  {
    const stripped = trimmed.trimStart();
    if (stripped.startsWith('##')) {
      isDisabled = true;
      // Reconstruct: preserve leading whitespace, strip ##
      const lead = trimmed.slice(0, trimmed.length - trimmed.trimStart().length);
      codeLine = lead + stripped.slice(2);
    } else if (stripped.startsWith('#')) {
      return null; // full-line comment
    } else {
      codeLine = trimmed;
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
      const found = rawLine.indexOf(trimmedCmd, cmdGlobalOffset);
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
    rawLine,
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
 * Parse full MCA text into an array of parse results (including error objects).
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
