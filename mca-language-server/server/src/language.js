// Language definition for MCA (derived from src/core/validator.py and
// src/core/api/services/actions.py in the Python codebase).
//
// Keep this file in sync when the Python implementation changes.

const COMMAND_PREFIXES = {
  '/': { type: 'vanilla', label: 'Vanilla Minecraft', doc: 'Minecraft command executed via datapack .mcfunction' },
  '!': { type: 'rcon', label: 'RCON', doc: 'Command sent directly via RCON connection' },
  '$': { type: 'script', label: 'Script', doc: 'Hook script action registered via HOOK_ACTIONS' },
  '&': { type: 'shell', label: 'Shell', doc: 'Host shell command executed via subprocess' },
  '>>': { type: 'overlay', label: 'Overlay', doc: 'Overlay text: >>Title|Subtitle|Duration' },
};

const NAMED_OVERLAY_RE = /^@(\w+)>>/;

const KNOWN_EVENT_TRIGGERS = [
  { name: 'follow', doc: 'Fires when someone follows the stream' },
  { name: 'join', doc: 'Fires when someone joins the stream' },
  { name: 'comment', doc: 'Fires when someone sends a chat comment ({comment} is available)' },
  { name: 'likes', doc: 'Fires every N likes (configurable in config.yaml)' },
  { name: 'like_2', doc: 'Fires at a bigger milestone (default: 100_000 likes)' },
  { name: 'share', doc: 'Fires when someone shares the stream' },
];

const VALID_PREFIX_CHARS = ['/', '!', '$', '&'];

const TRIGGER_NAME_RE = /^[A-Za-z0-9_]+$/;
const QUOTED_TRIGGER_RE = /^'[A-Za-z0-9_ ]+'$/;

const MULTIPLIER_RE = /\s+x(\d+)\s*$/;

const PLACEHOLDERS = [
  { name: '{user}', doc: 'Replaced with the triggering user\'s display name', triggers: ['all'] },
  { name: '{comment}', doc: 'Replaced with comment text (only works on the "comment" trigger)', triggers: ['comment'] },
];

const SNIPPETS = [
  {
    label: 'Trigger with vanilla command',
    insertText: '${1:trigger_name}:${2:/command}',
    doc: 'Basic trigger with a Minecraft command',
  },
  {
    label: 'Trigger with overlay',
    insertText: '${1:trigger_name}:>>${2:Title}|${3:Subtitle}|${4:3}',
    doc: 'Trigger that sends text to the overlay',
  },
  {
    label: 'Trigger with multiple commands',
    insertText: '${1:trigger_name}:${2:/command1} ; ${3:/command2}',
    doc: 'Chain multiple commands with semicolons',
  },
  {
    label: 'Trigger with shell command',
    insertText: '${1:trigger_name}:&${2:curl http://localhost:29191/add}',
    doc: 'Trigger that runs a shell command on the host',
  },
  {
    label: 'Trigger with script action',
    insertText: '${1:trigger_name}:$${2:random}',
    doc: 'Trigger that invokes a hook script',
  },
  {
    label: 'Disabled trigger',
    insertText: '##${1:trigger_name}:${2:/command}',
    doc: 'Disabled trigger (prefixed with ##)',
  },
  {
    label: 'Command with multiplier',
    insertText: '${1:trigger_name}:${2:/command} x${3:5}',
    doc: 'Repeat a command N times with xN multiplier',
  },
  {
    label: 'Named overlay',
    insertText: '${1:trigger_name}:@${2:screenName}>>${3:Title}|${4:Subtitle}|${5:3}',
    doc: 'Overlay text sent to a specific named overlay screen',
  },
];

module.exports = {
  COMMAND_PREFIXES,
  NAMED_OVERLAY_RE,
  KNOWN_EVENT_TRIGGERS,
  VALID_PREFIX_CHARS,
  TRIGGER_NAME_RE,
  QUOTED_TRIGGER_RE,
  MULTIPLIER_RE,
  PLACEHOLDERS,
  SNIPPETS,
};
