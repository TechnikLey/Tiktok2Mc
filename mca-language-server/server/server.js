// MCA Language Server — main entry point.
//
// Delegates to modular src/ modules for validation, completions, hover,
// symbols, and code actions.

const {
  createConnection,
  TextDocuments,
  ProposedFeatures,
  DiagnosticSeverity,
  CompletionItemKind,
  SymbolKind,
  FoldingRangeKind,
} = require('vscode-languageserver/node');

const { TextDocument } = require('vscode-languageserver-textdocument');

const { validateDocument } = require('./src/validator');
const { provideCompletions, resolveCompletion } = require('./src/completions');
const { provideHover } = require('./src/hover');
const { provideDocumentSymbols, provideFoldingRanges } = require('./src/symbols');

const connection = createConnection(ProposedFeatures.all);
const documents = new TextDocuments(TextDocument);

// ── Server capabilities ────────────────────────────────────────────────

connection.onInitialize(() => ({
  capabilities: {
    textDocumentSync: documents.syncKind,
    completionProvider: {
      resolveProvider: true,
      triggerCharacters: [':', ';', ' ', '/', '!', '$', '&', '>', 'x', '{'],
    },
    hoverProvider: true,
    documentSymbolProvider: true,
    foldingRangeProvider: true,
    codeActionProvider: true,
  },
}));

// ── Diagnostics ────────────────────────────────────────────────────────

documents.onDidChangeContent((change) => {
  try {
    const diagnostics = validateDocument(change.document.getText());
    connection.sendDiagnostics({ uri: change.document.uri, diagnostics });
  } catch (err) {
    connection.sendDiagnostics({
      uri: change.document.uri,
      diagnostics: [{
        severity: DiagnosticSeverity.Error,
        range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
        message: `Language server internal error: ${err.message}`,
        source: 'mca',
      }],
    });
  }
});

// ── Completions ────────────────────────────────────────────────────────

connection.onCompletion((params) => {
  try {
    const document = documents.get(params.textDocument.uri);
    if (!document) return [];
    return provideCompletions(document, params.position);
  } catch (err) {
    return [];
  }
});

connection.onCompletionResolve((item) => {
  try {
    return resolveCompletion(item);
  } catch (err) {
    return item;
  }
});

// ── Hover ──────────────────────────────────────────────────────────────

connection.onHover((params) => {
  try {
    const document = documents.get(params.textDocument.uri);
    if (!document) return null;
    return provideHover(document, params.position);
  } catch (err) {
    return null;
  }
});

// ── Document Symbols (Outline + Go-to-Symbol) ─────────────────────────

connection.onDocumentSymbol((params) => {
  try {
    const document = documents.get(params.textDocument.uri);
    if (!document) return [];
    return provideDocumentSymbols(document);
  } catch (err) {
    return [];
  }
});

// ── Folding Ranges ─────────────────────────────────────────────────────

connection.onFoldingRanges((params) => {
  try {
    const document = documents.get(params.textDocument.uri);
    if (!document) return [];
    return provideFoldingRanges(document);
  } catch (err) {
    return [];
  }
});

// ── Code Actions (Quick Fixes) ─────────────────────────────────────────

connection.onCodeAction((params) => {
  const codeActions = [];
  try {
    const document = documents.get(params.textDocument.uri);
    if (!document) return [];

    const lines = document.getText().split('\n');

    for (const diagnostic of params.context.diagnostics) {
      const lineNum = diagnostic.range.start.line;
      const lineText = lines[lineNum] || '';
      const code = diagnostic.code;

      if (code === 'trailing_colons' || code === 'no_space_after_colon' || code === 'trailing_semicolon') {
        // Auto-fix: clean up syntax
        const commentSplit = lineText.split('#');
        let codePart = commentSplit[0];
        codePart = codePart.replace(/[:\s;]+$/, '').replace(/:\s+/, ':');
        const newText = codePart + (commentSplit.length > 1 ? '#' + commentSplit.slice(1).join('#') : '');

        let title = 'Clean up syntax (Auto-Fix)';
        if (code === 'no_space_after_colon') title = 'Remove space after \':\'';
        if (code === 'trailing_semicolon') title = 'Remove unnecessary \';\'';
        if (code === 'trailing_colons') title = 'Remove trailing colons';

        codeActions.push({
          title,
          kind: 'quickfix',
          diagnostics: [diagnostic],
          edit: {
            changes: {
              [params.textDocument.uri]: [{
                range: {
                  start: { line: lineNum, character: 0 },
                  end: { line: lineNum, character: lineText.length },
                },
                newText,
              }],
            },
          },
          isPreferred: true,
        });
      }

      if (code === 'high_multi') {
        codeActions.push({
          title: 'Ignore lag warning (# ignore-lag)',
          kind: 'quickfix',
          diagnostics: [diagnostic],
          edit: {
            changes: {
              [params.textDocument.uri]: [{
                range: {
                  start: { line: lineNum, character: lineText.length },
                  end: { line: lineNum, character: lineText.length },
                },
                newText: ' # ignore-lag',
              }],
            },
          },
        });
      }
    }
  } catch (err) {
    // Return whatever we have
  }

  return codeActions;
});

// ── Start ──────────────────────────────────────────────────────────────

documents.listen(connection);
connection.listen();
