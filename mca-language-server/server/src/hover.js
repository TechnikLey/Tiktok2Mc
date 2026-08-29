// Hover provider — returns rich markdown documentation for tokens under the cursor.
// Documentation is derived from the shared mca-spec.json.

const {
  getCommandPrefixes, getEventTriggerDocs, getPlaceholders,
  getRules, NAMED_OVERLAY_RE,
} = require('./language');
const { parseLine } = require('./parser');

function provideHover(document, position) {
  try {
    const text = document.getText();
    const lines = text.split('\n');
    const lineNum = position.line;
    const rawLine = lines[lineNum] || '';
    const character = position.character;

    const result = parseLine(rawLine, lineNum);
    if (!result || result.isError) return null;

    // -- Hover over trigger name -----------------------------------------
    const tStart = result.triggerGlobalStart;
    const tEnd = tStart + result.trigger.length;
    if (character >= tStart && character <= tEnd) {
      const trigger = result.trigger;
      const docs = getEventTriggerDocs();
      const found = docs.find(d => d.name === trigger);

      if (found) {
        return {
          contents: {
            kind: 'markdown',
            value: [
              `**\`${trigger}\`** — Event Trigger`,
              '',
              found.doc || '',
              '',
              '_Trigger names are case-sensitive._',
            ].join('\n'),
          },
        };
      }

      if (/^\d+$/.test(trigger)) {
        return {
          contents: {
            kind: 'markdown',
            value: `**\`${trigger}\`** — Gift ID\n\nNumeric gift ID trigger. Fires when this specific TikTok gift is sent.\n\nAllowed characters: \`A-Z\`, \`a-z\`, \`0-9\`, \`_\`.`,
          },
        };
      }

      return {
        contents: {
          kind: 'markdown',
          value: `**\`${trigger}\`** — Custom Trigger\n\nUser-defined trigger name.\n\nAllowed characters: \`A-Z\`, \`a-z\`, \`0-9\`, \`_\`. Use single quotes for names with spaces.`,
        },
      };
    }

    // -- Hover over colon -------------------------------------------------
    if (character === result.colonIndex) {
      return {
        contents: {
          kind: 'markdown',
          value: '**Separator** — The colon separates the **trigger name** (left) from the **commands** (right).\n\nSyntax: `trigger:command1;command2`',
        },
      };
    }

    // -- Hover over command prefixes -------------------------------------
    const prefixes = getCommandPrefixes();
    for (const [prefix, info] of Object.entries(prefixes)) {
      const idx = rawLine.indexOf(prefix, result.colonIndex);
      if (idx >= 0 && character >= idx && character < idx + prefix.length) {
        return {
          contents: {
            kind: 'markdown',
            value: `**\`${prefix}\`** — ${info.label}\n\n${info.doc || ''}`,
          },
        };
      }
    }

    // -- Hover over named overlay prefix (@name>>) -----------------------
    const namedMatch = rawLine.match(NAMED_OVERLAY_RE);
    if (namedMatch) {
      const full = namedMatch[0];
      const idx = rawLine.indexOf(full);
      if (character >= idx && character < idx + full.length) {
        const name = namedMatch[1];
        return {
          contents: {
            kind: 'markdown',
            value: `**\`@${name}>>\`** — Named Overlay\n\nSends overlay text to the overlay screen named **\`${name}\`**.\n\nSyntax: \`@name>>Title|Subtitle|Duration\``,
          },
        };
      }
    }

    // -- Hover over placeholders -----------------------------------------
    const placeholders = getPlaceholders();
    for (const p of placeholders) {
      const idx = rawLine.indexOf(p.name);
      if (idx >= 0 && character >= idx && character < idx + p.name.length) {
        return {
          contents: {
            kind: 'markdown',
            value: `**\`${p.name}\`** — Placeholder\n\n${p.doc || ''}`,
          },
        };
      }
    }

    // -- Hover over multiplier -------------------------------------------
    const multMatch = rawLine.match(/\s+x(\d+)\s*$/);
    if (multMatch) {
      const idx = rawLine.lastIndexOf(`x${multMatch[1]}`);
      if (character >= idx && character < idx + multMatch[0].trim().length) {
        const amount = parseInt(multMatch[1], 10);
        const rules = getRules() || {};
        const threshold = rules.high_multi_threshold || 50;
        let warning = '';
        if (amount > threshold) {
          warning = '\n\n⚠️ High multiplier — this may cause lag. Add `# ignore-lag` to suppress the warning.';
        }
        return {
          contents: {
            kind: 'markdown',
            value: `**Multiplier x${amount}** — Repeats the command ${amount} times.${warning}`,
          },
        };
      }
    }

    // -- Hover over semicolon --------------------------------------------
    const semiIdx = rawLine.indexOf(';');
    if (semiIdx >= 0 && character === semiIdx) {
      return {
        contents: {
          kind: 'markdown',
          value: '**Command Separator** — Semicolon chains multiple commands for the same trigger.',
        },
      };
    }
  } catch (err) {
    // Silently fail for hover
  }

  return null;
}

module.exports = { provideHover };
