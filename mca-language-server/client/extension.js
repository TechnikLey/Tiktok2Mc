const path = require('path');
const { workspace, commands, window } = require('vscode');
const {
  LanguageClient,
  TransportKind,
} = require('vscode-languageclient/node');

let client;

function activate(context) {
  const serverModule = context.asAbsolutePath(path.join('server', 'server.js'));

  const serverOptions = {
    run: { module: serverModule, transport: TransportKind.ipc },
    debug: {
      module: serverModule,
      transport: TransportKind.ipc,
      options: { execArgv: ['--nolazy', '--inspect=6009'] },
    },
  };

  const clientOptions = {
    documentSelector: [{ scheme: 'file', language: 'mca' }],
    synchronize: {
      fileEvents: workspace.createFileSystemWatcher('**/.mca'),
    },
  };

  client = new LanguageClient(
    'mcaLanguageServer',
    'MCA Language Server',
    serverOptions,
    clientOptions
  );

  const ignoreLagCommand = commands.registerCommand('mca.ignoreLag', (uri, line) => {
    console.log(`Command mca.ignoreLag called for: ${uri} line: ${line}`);
  });

  context.subscriptions.push(ignoreLagCommand);

  client.start().then(() => {
    console.log('MCA Language Server is now active.');
  }).catch((err) => {
    window.showErrorMessage('MCA Server could not be started: ' + err);
  });
}

function deactivate() {
  if (!client) {
    return undefined;
  }
  return client.stop();
}

module.exports = { activate, deactivate };
