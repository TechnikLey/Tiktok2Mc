/**
 * @file Config-editor schema metadata, categories, help texts and field lookup.
 *
 *
 * Part of the split dashboard controller; load order is defined by index.html.
 */

/* ─── Config Editor ─── */

const SECTION_ORDER = [
  'tiktok','rcon','server_host','control_method',
  'api','java','mc_version','minecraft_server_api',
  'console','overlay','theme',
  'update','shutdown','auto_update_config','show_sudo_warning','gui',
  'plugin_sandbox',
  'port_policy','api_key',
  'outbound',
  'like_triggers',
  'gifts'
];

const CATEGORIES = {
  'Connection': ['tiktok','rcon','server_host','control_method','api'],
  'Minecraft': ['java','mc_version','minecraft_server_api'],
  'System': ['console','overlay','theme','update','shutdown','auto_update_config','show_sudo_warning','gui','plugin_sandbox','port_policy','api_key','gifts'],
  'Integration': ['outbound'],
  'Chat & Commands': ['like_triggers']
};

const SECTION_META = {
  tiktok: { title: 'TikTok Live', desc: 'Connect the tool to your TikTok live stream. Set your username and connection behavior.', category: 'Connection' },
  rcon: { title: 'Remote Console (RCON)', desc: 'RCON allows the tool to send commands to your Minecraft server. Keep this enabled.', category: 'Connection' },
  api: { title: 'API Server', desc: 'Configuration for the central API server that powers the dashboard and internal communication.', category: 'Connection' },
  java: { title: 'Minecraft Server', desc: 'Controls how much RAM the Minecraft server uses and which port it runs on.', category: 'Minecraft' },
  mc_version: { title: 'Minecraft Version', desc: 'The Minecraft version the server runs on. Used for version-aware features.', category: 'Minecraft' },
  random_triggers: { title: 'Random Trigger Filter', desc: 'Controls which triggers can be selected by the $random action in data/actions.mca.', category: 'Chat & Commands' },
  like_triggers: { title: 'Like Triggers', desc: 'Fire actions when total stream likes reach a threshold. Each trigger activates at a defined interval and runs a command from actions.mca.', category: 'Chat & Commands' },
  console: { title: 'Console Visibility', desc: 'Controls which windows and processes are shown when the tool starts.', category: 'System' },
  minecraft_server_api: { title: 'Minecraft Server API', desc: 'Handles communication between the tool and the Minecraft server. Required for player death/respawn detection.', category: 'Minecraft' },
  gui: { title: 'Dashboard', desc: 'The graphical user interface is served by the central API server and shown in a window.', category: 'System' },
  overlay: { title: 'Overlay Text', desc: 'Overlay subsystem for displaying text messages on stream.', category: 'System' },
  theme: { title: 'Overlay Colors', desc: 'Customize colors for overlays. All values are CSS hex codes like #ff0000.', category: 'System' },
  update: { title: 'Auto-Updater', desc: 'Checks for new versions on startup and installs them automatically. Strongly recommended.', category: 'System' },
  shutdown: { title: 'Auto-Shutdown', desc: 'Automatically shuts down the tool after your live stream ends.', category: 'System' },
  server_host: { title: 'Server Address', desc: 'Controls which network interfaces the tool listens on.', category: 'Connection' },
  control_method: { title: 'Control Method', desc: 'How the tool communicates with your streaming software.', category: 'Connection' },
  auto_update_config: { title: 'Auto-Update Config', desc: 'Automatically merge new options when the tool updates.', category: 'System' },
  show_sudo_warning: { title: 'Sudo Warning', desc: 'Linux only. Warns if running without sudo, which can cause permission issues.', category: 'System' },
  port_policy: { title: 'Port Policy', desc: 'Controls what happens when a required port is already in use. Can auto-resolve to the next free port.', category: 'System' },
  api_key: { title: 'API Key', desc: 'Optional API key for authentication when the server is exposed beyond localhost.', category: 'System' },
  plugin_sandbox: { title: 'Plugin Sandbox', desc: 'Restricts plugin subprocess resources to limit the impact of misbehaving or compromised plugins.', category: 'System' },
  gifts: { title: 'Gifts', desc: 'Gift synchronization settings.', category: 'System' },
};

const SECTION_META_DE = {
  tiktok: { title: 'TikTok Live', desc: 'Verbinde das Tool mit deinem TikTok-Live-Stream. Lege deinen Benutzernamen und das Verbindungsverhalten fest.' },
  rcon: { title: 'Remote Console (RCON)', desc: 'RCON erlaubt dem Tool, Befehle an deinen Minecraft-Server zu senden. Lasse diese Option aktiviert.' },
  api: { title: 'API-Server', desc: 'Konfiguration des zentralen API-Servers, der das Dashboard und die interne Kommunikation antreibt.' },
  java: { title: 'Minecraft-Server', desc: 'Steuert, wie viel RAM der Minecraft-Server verwendet und auf welchem Port er läuft.' },
  mc_version: { title: 'Minecraft-Version', desc: 'Die Minecraft-Version, auf der der Server läuft. Wird für versionsabhängige Funktionen verwendet.' },
  random_triggers: { title: 'Zufalls-Trigger-Filter', desc: 'Steuert, welche Trigger für die $random-Aktion in data/actions.mca ausgewählt werden können.' },
  like_triggers: { title: 'Like-Trigger', desc: 'Lösen Aktionen aus, wenn die Gesamtzahl der Stream-Likes einen Schwellenwert erreicht. Jeder Trigger wird bei einem definierten Intervall aktiviert und führt einen Befehl aus actions.mca aus.' },
  console: { title: 'Konsolen-Sichtbarkeit', desc: 'Steuert, welche Fenster und Prozesse beim Start des Tools angezeigt werden.' },
  minecraft_server_api: { title: 'Minecraft-Server-API', desc: 'Übernimmt die Kommunikation zwischen dem Tool und dem Minecraft-Server. Erforderlich für die Spieler-Tod-/Wiederbelebungs-Erkennung.' },
  gui: { title: 'Dashboard', desc: 'Die grafische Benutzeroberfläche wird vom zentralen API-Server bereitgestellt und in einem Fenster angezeigt.' },
  overlay: { title: 'Overlay-Text', desc: 'Overlay-Subsystem zur Anzeige von Textnachrichten im Stream.' },
  theme: { title: 'Overlay-Farben', desc: 'Passe die Farben für Overlays an. Alle Werte sind CSS-Hex-Codes wie #ff0000.' },
  update: { title: 'Auto-Updater', desc: 'Überprüft beim Start auf neue Versionen und installiert sie automatisch. Dringend empfohlen.' },
  shutdown: { title: 'Auto-Herunterfahren', desc: 'Fährt das Tool automatisch herunter, nachdem dein Live-Stream endet.' },
  server_host: { title: 'Server-Adresse', desc: 'Steuert, an welchen Netzwerkschnittstellen das Tool lauscht.' },
  control_method: { title: 'Steuerungsmethode', desc: 'Wie das Tool mit deiner Streaming-Software kommuniziert.' },
  auto_update_config: { title: 'Auto-Konfigurations-Update', desc: 'Fügt beim Tool-Update automatisch neue Optionen hinzu, ohne deine Werte zu überschreiben.' },
  show_sudo_warning: { title: 'Sudo-Warnung', desc: 'Nur Linux. Warnt, wenn du ohne sudo läufst, was Berechtigungsprobleme verursachen kann.' },
  port_policy: { title: 'Port-Richtlinie', desc: 'Steuert, was passiert, wenn ein benötigter Port bereits belegt ist. Kann automatisch zum nächsten freien Port wechseln.' },
  api_key: { title: 'API-Schlüssel', desc: 'Optionaler API-Schlüssel für die Authentifizierung, wenn der Server über localhost hinaus erreichbar ist.' },
  plugin_sandbox: { title: 'Plugin-Sandbox', desc: 'Beschränkt Ressourcen von Plugin-Subprozessen, um die Auswirkungen fehlerhafter oder kompromittierter Plugins zu begrenzen.' },
  gifts: { title: 'Geschenke', desc: 'Einstellungen zur Geschenk-Synchronisierung.' },
};

const CATEGORY_LABELS_DE = {
  'Connection': 'Verbindung',
  'Minecraft': 'Minecraft',
  'System': 'System',
  'Integration': 'Integration',
  'Chat & Commands': 'Chat & Befehle',
};

const HELP_TEXT = {
  'auto_update_config': 'When enabled (recommended), new configuration options introduced by updates are automatically merged into your existing config.yaml. Your existing values are preserved.',
  'show_sudo_warning': 'On Linux, running without sudo can cause update and permission issues. Set to false only if you have configured your system to handle permissions properly without sudo.',
  'server_host': 'Controls which network interfaces the servers listen on. "127.0.0.1" means local access only (default, safe). "0.0.0.0" allows access from other devices on your network. The central API always runs on port 29185.',
  'control_method': 'How the tool communicates with your streaming software. DCS (Direct Control System) is recommended for OBS Studio, vMix, and Streamlabs Desktop. ICS (Interface Control System) is required for TikTok Live Studio and Twitch Studio.',
  'shutdown.enabled': 'When enabled, the tool shuts down automatically after your live stream ends.',
  'shutdown.delay_seconds': 'Seconds to wait before shutting down. A countdown gives you time to cancel by typing "stop" in the console.',
  'java.xms': "Initial RAM allocation for the Minecraft server. 'G' = Gigabytes. Using the same value for xms and xmx is recommended. Default is 4G. Reduce to 2G or 1G if your system has less than 8 GB RAM. Low RAM may cause lag or crashes.",
  'java.xmx': "Maximum RAM allocation. Should match xms for stable performance. 'G' = Gigabytes.",
  'java.port': 'Minecraft server port. Default: 25565. Only change if you changed it in server.properties.',
  'rcon.enabled': 'RCON allows the tool to send commands to your Minecraft server. IMPORTANT: Keep this enabled — disabling it breaks most functionality.',
  'rcon.password': 'Set a secure password. The tool will ask you to set one on first start if this is left empty.',
  'rcon.port': 'RCON port. Default: 25575. Only change if you changed it in server.properties.',
  'rcon.http_command_api': 'Direct command endpoint (POST /api/v1/rcon/command) used by the dashboard Console tab. Disabled by default for security and stability — direct commands bypass the bridge\'s RCON queue and throttling. Enable only if you use the console or extensions need it; trigger actions keep working via the queue either way.',
  'tiktok.user': 'Your TikTok username — without the @ symbol. This is required for the tool to connect to your live stream.',
  'tiktok.reconnect_delay_seconds': 'Seconds to wait before attempting to reconnect after a connection loss.',
  'tiktok.failed_connection_popup_enabled': 'When enabled, after the configured number of consecutive failed connection attempts the tool pauses reconnecting and shows a warning in the GUI where you can choose to reconnect or keep the connection disabled. Repeated failed attempts can make TikTok block your device.',
  'tiktok.max_connect_fails': 'Number of consecutive failed connection attempts after which the tool pauses reconnecting and shows the warning popup. Set to 1 to pause after the first failure.',
  'tiktok.autosave_interval_seconds': 'How often (in seconds) the gift revenue log file is saved to disk. The log is stored at data/gift_revenue_log.jsonl.',
  'tiktok.follow_tracking.mode': 'all_time tracks follows across ALL streams. Once a user is recorded, their future follows are ignored even after restarting. per_stream resets the list every time the tool starts.',
  'tiktok.like_rate_limit': 'Caps how many likes a single viewer can add to the like counter per rolling minute. This stops one account from farming like-trigger milestones. Likes above the limit are ignored by like triggers; other viewers are unaffected. Disabled by default.',
  'tiktok.like_rate_limit.enabled': 'Enable the per-viewer like limit. Disabled by default.',
  'tiktok.like_rate_limit.max_per_user_per_minute': 'Maximum likes counted per viewer in any rolling 60-second window. Example: 500 means one viewer can contribute at most 500 likes per minute. Set to 0 for no limit.',
  'random_triggers.mode': 'deny-all means ONLY triggers in the list are eligible for $random. allow-all means ALL triggers are eligible EXCEPT those in the list.',
  'random_triggers.triggers': 'List of trigger names. Which ones are used depends on the mode. Triggers containing "$random" are automatically excluded to prevent infinite recursion.',
  'like_triggers': 'Like triggers let you automatically run a command every time your stream reaches a certain number of likes. For example: set one to fire every 100 likes so viewers see a reward as the like count grows. Each trigger connects to a command you write in the Actions Editor (data/actions.mca).',
  'like_triggers[].id': 'A short name just for you — so you can tell triggers apart in logs. Example: "likes_100" or "big_milestone".',
  'like_triggers[].every': 'How many likes between each activation. Example: 100 means the trigger fires when likes hit 100, then 200, then 300, and so on.',
  'like_triggers[].function': 'The trigger name from your Actions Editor. Write a command for this name there — it will run every time this trigger fires. Example: if you set this to "likes", create a "likes" trigger in actions.mca.',
  'like_triggers[].payload': 'This text replaces {user} in your actions.mca command. For example: setting it to "Community" means {user} becomes "Community". Leave as "Community" if unsure.',
  'like_triggers[].enabled': 'Turn off to pause this trigger without deleting it.',
  'console.log_level': 'Visibility level: 0 = Hide everything, 1 = Silent (hide console, keep GUI), 2 = Standard (recommended), 3 = Advanced, 4 = Debug, 5 = Override (debugging only).',
  'console.visible': 'Show or hide the main console window when the tool starts.',
  'console.allow_close': 'If true, typing "exit" in the console shuts everything down cleanly. If false, the launcher exits immediately after starting programs.',
  'minecraft_server_api.api_port': 'Port for the internal Minecraft API bridge. Default: 29187.',
  'minecraft_server_api.web_server_port': 'Port for the webhook server that receives Minecraft events. Default: 29188.',
  'gui.enabled': 'Launch the graphical dashboard on startup. If disabled, you can still open it manually.',
  'update.enabled': 'Checks for new versions on startup and installs them automatically. It is strongly recommended to keep this enabled.',
  'update.auto_install': 'When enabled, updates are installed automatically on startup. When disabled, you will be notified in the GUI when an update is available and can install it manually from the Updates tab.',
  'update.max_update_logs': 'Maximum number of update log files to keep in logs/update_logs/. 0 = delete all after each update. -1 = keep forever.',
  'overlay.enabled': 'Enable the built-in text overlay subsystem. When disabled, overlay windows will not open and overlay actions in actions.mca will be skipped.',
  'overlay.display_mode': 'overwrite replaces the current message immediately. queue lines up messages and shows them one after another.',
  'overlay.fade_in': 'Fade-in duration in milliseconds. Set to 0 for instant appearance.',
  'overlay.fade_out': 'Fade-out duration in milliseconds. Set to 0 for instant disappearance.',
  'overlay.max_fails': 'Consecutive failed dispatches before the circuit breaker activates and blocks further messages.',
  'overlay.cooldown': 'Seconds to wait after max_fails before allowing new messages again.',
  'overlay.overlays': 'Named overlay slots. Each slot can have its own OBS Browser Source URL. "default" is required and used when no specific overlay is requested.',
  'overlay.theme.background': 'Background colour of the overlay window. Also used as the chroma key colour.',
  'overlay.theme.text': 'Text colour shown in the overlay.',
  'port_policy.auto_resolve': 'When enabled, automatically find the next free port if the default port is already in use. When disabled, logs an error and exits.',
  'port_policy.session_only': 'When enabled, resolved ports are used only for the current session. When disabled, resolved ports are saved permanently to the config.',
  'port_policy.max_offset': 'How many ports to try before giving up. -1 means unlimited.',
  'api_key': 'Optional API key for authentication. When set, all non-localhost requests must include the X-API-Key header. Leave empty to disable authentication.',
  'plugin_sandbox.enabled': 'Enable sandboxing to restrict plugin subprocess resources.',
  'plugin_sandbox.profile': 'Built-in preset: "light" (1 GB RAM, no CPU cap), "moderate" (512 MB, 1 h CPU) or "strict" (256 MB, 15 min CPU). When set, it overrides the raw values below. Individual plugins can override it via "sandbox_profile" in their plugin.json.',
  'plugin_sandbox.max_memory_mb': 'Maximum RAM per plugin process in megabytes.',
  'plugin_sandbox.max_cpu_time': 'Maximum CPU seconds per plugin (Linux only).',
  'plugin_sandbox.max_files': 'Maximum open file descriptors per plugin (Linux only).',
  'plugin_sandbox.max_processes': 'Maximum child processes per plugin (Linux only).',
  'plugin_sandbox.priority_class': 'Windows process priority for plugin subprocesses. below_normal reduces impact on the main tool.',
  'outbound.enabled': 'Master switch for all outbound channels. When disabled, no events are forwarded.',
  'outbound.max_fails': 'Consecutive failed deliveries before a channel\'s circuit breaker activates. Same mechanism as the overlay circuit breaker.',
  'outbound.cooldown': 'Seconds a channel pauses after max_fails failed deliveries. Events arriving during the cooldown are dropped.',
  'outbound.retries': 'Extra delivery attempts per message after the first failure (1 second apart). 0 = send exactly once.',
  'outbound.timeout': 'HTTP timeout in seconds per delivery attempt.',
  'outbound.channels': 'Webhook channels. Each channel POSTs matching events to its URL. Patterns use exact names (tiktok.gift) or wildcards (tiktok.*); * matches everything.'
};

const HELP_TEXT_DE = {
  'auto_update_config': 'Wenn aktiviert (empfohlen), werden neue Konfigurationsoptionen, die durch Updates eingeführt werden, automatisch in deine bestehende config.yaml eingefügt. Deine vorhandenen Werte bleiben erhalten.',
  'show_sudo_warning': 'Unter Linux kann das Ausführen ohne sudo Update- und Berechtigungsprobleme verursachen. Setze dies nur auf false, wenn dein System die Berechtigungen auch ohne sudo korrekt handhabt.',
  'server_host': 'Steuert, an welchen Netzwerkschnittstellen die Server lauschen. „127.0.0.1" bedeutet nur lokaler Zugriff (Standard, sicher). „0.0.0.0" erlaubt Zugriff von anderen Geräten in deinem Netzwerk. Der zentrale API-Server läuft immer auf Port 29185.',
  'control_method': 'Wie das Tool mit deiner Streaming-Software kommuniziert. DCS (Direct Control System) wird für OBS Studio, vMix und Streamlabs Desktop empfohlen. ICS (Interface Control System) ist für TikTok Live Studio und Twitch Studio erforderlich.',
  'shutdown.enabled': 'Wenn aktiviert, fährt sich das Tool automatisch herunter, nachdem dein Live-Stream endet.',
  'shutdown.delay_seconds': 'Sekunden bis zum Herunterfahren. Ein Countdown gibt dir Zeit zum Abbrechen, indem du „stop" in die Konsole tippst.',
  'java.xms': 'Anfängliche RAM-Zuweisung für den Minecraft-Server. „G" = Gigabyte. Es wird empfohlen, für xms und xmx den gleichen Wert zu verwenden. Standard ist 4G. Reduziere auf 2G oder 1G, wenn dein System weniger als 8 GB RAM hat. Zu wenig RAM kann zu Verzögerungen oder Abstürzen führen.',
  'java.xmx': 'Maximale RAM-Zuweisung. Sollte für stabile Leistung xms entsprechen. „G" = Gigabyte.',
  'java.port': 'Minecraft-Server-Port. Standard: 25565. Nur ändern, wenn du ihn in server.properties geändert hast.',
  'rcon.enabled': 'RCON erlaubt dem Tool, Befehle an deinen Minecraft-Server zu senden. WICHTIG: Lasse dies aktiviert — Deaktivieren bricht die meisten Funktionen.',
  'rcon.password': 'Lege ein sicheres Passwort fest. Das Tool fragt dich beim ersten Start danach, wenn dieses Feld leer bleibt.',
  'rcon.port': 'RCON-Port. Standard: 25575. Nur ändern, wenn du ihn in server.properties geändert hast.',
  'rcon.http_command_api': 'Direkter Befehls-Endpunkt (POST /api/v1/rcon/command), den der Konsole-Tab im Dashboard nutzt. Aus Sicherheits- und Stabilitätsgründen standardmäßig deaktiviert — direkte Befehle umgehen die RCON-Queue und das Throttling der Bridge. Aktiviere ihn nur, wenn du die Konsole nutzt oder Erweiterungen ihn brauchen; Trigger-Aktionen funktionieren über die Queue weiterhin.',
  'tiktok.user': 'Dein TikTok-Benutzername — ohne das @-Zeichen. Dies ist erforderlich, damit sich das Tool mit deinem Live-Stream verbinden kann.',
  'tiktok.reconnect_delay_seconds': 'Sekunden, die vor dem erneuten Verbindungsversuch nach einem Verbindungsverlust gewartet werden.',
  'tiktok.failed_connection_popup_enabled': 'Wenn aktiviert, pausiert das Tool nach der konfigurierten Anzahl aufeinanderfolgender fehlgeschlagener Verbindungsversuche das Wiederverbinden und zeigt eine Warnung in der GUI, in der du wählen kannst, ob du erneut verbinden oder die Verbindung deaktiviert lassen möchtest. Wiederholte Fehlversuche können dazu führen, dass TikTok dein Gerät blockiert.',
  'tiktok.max_connect_fails': 'Anzahl aufeinanderfolgender fehlgeschlagener Verbindungsversuche, nach denen das Tool das Wiederverbinden pausiert und das Warn-Popup anzeigt. Setze 1, um nach dem ersten Fehlversuch zu pausieren.',
  'tiktok.autosave_interval_seconds': 'Wie oft (in Sekunden) die Geschenk-Umsatzlog-Datei auf der Festplatte gespeichert wird. Die Log-Datei liegt unter data/gift_revenue_log.jsonl.',
  'tiktok.follow_tracking.mode': 'all_time verfolgt Follower über ALLE Streams hinweg. Sobald ein Nutzer erfasst wurde, werden zukünftige Follows auch nach einem Neustart ignoriert. per_stream setzt die Liste bei jedem Start des Tools zurück.',
  'tiktok.like_rate_limit': 'Begrenzt, wie viele Likes ein einzelner Zuschauer pro rollender Minute zum Like-Zähler beitragen kann. Das verhindert, dass ein Account Like-Trigger-Meilensteine durch Like-Spam farmt. Likes über dem Limit werden von Like-Triggern ignoriert; andere Zuschauer sind nicht betroffen. Standardmäßig deaktiviert.',
  'tiktok.like_rate_limit.enabled': 'Aktiviert das Like-Limit pro Zuschauer. Standardmäßig deaktiviert.',
  'tiktok.like_rate_limit.max_per_user_per_minute': 'Maximale Likes, die pro Zuschauer in einem rollenden 60-Sekunden-Fenster gezählt werden. Beispiel: 500 bedeutet, dass ein Zuschauer höchstens 500 Likes pro Minute beitragen kann. 0 bedeutet unbegrenzt.',
  'random_triggers.mode': 'deny-all bedeutet, dass NUR Trigger in der Liste für $random infrage kommen. allow-all bedeutet, dass ALLE Trigger infrage kommen AUSSER den aufgelisteten.',
  'random_triggers.triggers': 'Liste der Triggernamen. Welche verwendet werden, hängt vom Modus ab. Trigger, die „$random" enthalten, werden automatisch ausgeschlossen, um Endlosrekursion zu verhindern.',
  'like_triggers': 'Like-Trigger lassen dich automatisch einen Befehl ausführen, sobald dein Stream eine bestimmte Like-Zahl erreicht. Zum Beispiel: Setze einen Trigger auf 100 Likes, damit Zuschauer eine Belohnung sehen, während die Like-Zahl steigt. Jeder Trigger verbindet sich mit einem Befehl, den du im Aktions-Editor (data/actions.mca) schreibst.',
  'like_triggers[].id': 'Ein kurzer Name nur für dich — damit du in Logs siehst, welcher Trigger ausgelöst wurde. Beispiel: "likes_100" oder "großer_meilenstein".',
  'like_triggers[].every': 'Wie viele Likes zwischen den Auslösungen. Beispiel: 100 löst bei 100, 200, 300 usw. aus.',
  'like_triggers[].function': 'Der Trigger-Name aus deinem Aktions-Editor. Schreibe dort einen Befehl für diesen Namen — er wird bei jeder Auslösung ausgeführt. Beispiel: Wenn du „likes" eingibst, erstelle einen „likes"-Trigger in actions.mca.',
  'like_triggers[].payload': 'Dieser Text ersetzt {user} in deinem actions.mca-Befehl. Beispiel: „Community" bedeutet, {user} wird zu „Community". Lass „Community" stehen, wenn unsicher.',
  'like_triggers[].enabled': 'Deaktiviere, um diesen Trigger zu pausieren, ohne ihn zu löschen.',
  'console.log_level': 'Sichtbarkeitsstufe: 0 = Alles ausblenden, 1 = Still (Konsole ausblenden, GUI behalten), 2 = Standard (empfohlen), 3 = Erweitert, 4 = Debug, 5 = Override (nur zum Debuggen).',
  'console.visible': 'Konsolen-Hauptfenster beim Start des Tools anzeigen oder ausblenden.',
  'console.allow_close': 'Wenn true, fährt die Eingabe von „exit" in der Konsole alles sauber herunter. Wenn false, beendet sich der Launcher sofort nach dem Start der Programme.',
  'minecraft_server_api.api_port': 'Port für die interne Minecraft-API-Brücke. Standard: 29187.',
  'minecraft_server_api.web_server_port': 'Port für den Webhook-Server, der Minecraft-Ereignisse empfängt. Standard: 29188.',
  'gui.enabled': 'Startet das grafische Dashboard beim Programmstart. Wenn deaktiviert, kannst du es trotzdem manuell öffnen.',
  'update.enabled': 'Überprüft beim Start auf neue Versionen und installiert sie automatisch. Es wird dringend empfohlen, dies aktiviert zu lassen.',
  'update.max_update_logs': 'Maximale Anzahl der Update-Logdateien, die in logs/update_logs/ aufbewahrt werden. 0 = nach jedem Update alle löschen. -1 = für immer behalten.',
  'overlay.enabled': 'Aktiviere das eingebaute Text-Overlay-Subsystem. Wenn deaktiviert, werden Overlay-Fenster nicht geöffnet und Overlay-Aktionen in actions.mca übersprungen.',
  'overlay.display_mode': 'overwrite ersetzt die aktuelle Nachricht sofort. queue reiht Nachrichten auf und zeigt sie nacheinander an.',
  'overlay.fade_in': 'Einblenddauer in Millisekunden. 0 für sofortiges Erscheinen.',
  'overlay.fade_out': 'Ausblenddauer in Millisekunden. 0 für sofortiges Verschwinden.',
  'overlay.max_fails': 'Aufeinanderfolgende fehlgeschlagene Zustellungen, bevor der Schutzschalter auslöst und weitere Nachrichten blockiert.',
  'overlay.cooldown': 'Sekunden nach max_fails, bevor neue Nachrichten wieder zugelassen werden.',
  'overlay.overlays': 'Benannte Overlay-Slots. Jeder Slot kann eine eigene OBS-Browser-Source-URL haben. „default" ist erforderlich und wird verwendet, wenn kein bestimmtes Overlay angefordert wird.',
  'overlay.theme.background': 'Hintergrundfarbe des Overlay-Fensters. Wird auch als Chroma-Key-Farbe verwendet.',
  'overlay.theme.text': 'Textfarbe, die im Overlay angezeigt wird.',
  'port_policy.auto_resolve': 'Wenn aktiviert, wird automatisch der nächste freie Port gefunden, falls der Standardport bereits belegt ist. Wenn deaktiviert, wird ein Fehler protokolliert und beendet.',
  'port_policy.session_only': 'Wenn aktiviert, werden aufgelöste Ports nur für die aktuelle Sitzung verwendet. Wenn deaktiviert, werden aufgelöste Ports dauerhaft in der Konfiguration gespeichert.',
  'port_policy.max_offset': 'Wie viele Ports versucht werden, bevor aufgegeben wird. -1 bedeutet unbegrenzt.',
  'api_key': 'Optionaler API-Schlüssel für die Authentifizierung. Wenn gesetzt, müssen alle Nicht-Localhost-Anfragen den X-API-Key-Header enthalten. Lasse leer, um die Authentifizierung zu deaktivieren.',
  'plugin_sandbox.enabled': 'Sandboxing aktivieren, um Ressourcen von Plugin-Subprozessen einzuschränken.',
  'plugin_sandbox.profile': 'Built-in-Profil: "light" (1 GB RAM, kein CPU-Limit), "moderate" (512 MB, 1 h CPU) oder "strict" (256 MB, 15 min CPU). Wenn gesetzt, überschreibt es die Rohwerte unten. Einzelne Plugins können es via "sandbox_profile" in ihrer plugin.json überschreiben.',
  'plugin_sandbox.max_memory_mb': 'Maximaler RAM pro Plugin-Prozess in Megabyte.',
  'plugin_sandbox.max_cpu_time': 'Maximale CPU-Sekunden pro Plugin (nur Linux).',
  'plugin_sandbox.max_files': 'Maximale offene Dateideskriptoren pro Plugin (nur Linux).',
  'plugin_sandbox.max_processes': 'Maximale Kindprozesse pro Plugin (nur Linux).',
  'plugin_sandbox.priority_class': 'Windows-Prozesspriorität für Plugin-Subprozesse. below_normal reduziert die Auswirkungen auf das Haupt-Tool.',
  'outbound.enabled': 'Hauptschalter für alle Outbound-Channels. Wenn deaktiviert, werden keine Events weitergeleitet.',
  'outbound.max_fails': 'Aufeinanderfolgende fehlgeschlagene Zustellungen, bevor der Schutzschalter eines Channels auslöst. Gleicher Mechanismus wie beim Overlay-Schutzschalter.',
  'outbound.cooldown': 'Sekunden, die ein Channel nach max_fails Fehlzustellungen pausiert. Events während der Pause werden verworfen.',
  'outbound.retries': 'Zusätzliche Zustellversuche pro Nachricht nach dem ersten Fehlversuch (jeweils 1 Sekunde Abstand). 0 = genau einmal senden.',
  'outbound.timeout': 'HTTP-Timeout in Sekunden pro Zustellversuch.',
  'outbound.channels': 'Webhook-Channels. Jeder Channel POSTet passende Events an seine URL. Patterns sind exakte Namen (tiktok.gift) oder Wildcards (tiktok.*); * passt auf alles.'
};

const FIELD_META = {
  'config_version': { basic: false, readonly: true, type: 'text' },
  'auto_update_config': { basic: true, type: 'bool' },
  'show_sudo_warning': { basic: false, type: 'bool' },
  'server_host': { basic: false, type: 'text', required: true },
  'control_method': { basic: true, type: 'select', options: ['DCS','ICS'] },
  'shutdown.enabled': { basic: true, type: 'bool' },
  'shutdown.delay_seconds': { basic: true, type: 'number', min: 0, max: 3600 },
  'java.xms': { basic: true, type: 'text', pattern: /^\d+[GgMm]$/ },
  'java.xmx': { basic: true, type: 'text', pattern: /^\d+[GgMm]$/ },
  'java.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'rcon.enabled': { basic: true, type: 'bool' },
  'rcon.password': { basic: true, type: 'password', required: true },
  'rcon.port': { basic: false, type: 'number', min: 1, max: 65535 },
  'rcon.http_command_api': { basic: true, type: 'bool' },
  'tiktok.user': { basic: true, type: 'text', required: true },
  'tiktok.reconnect_delay_seconds': { basic: true, type: 'number', min: 0 },
  'tiktok.failed_connection_popup_enabled': { basic: true, type: 'bool' },
  'tiktok.max_connect_fails': { basic: true, type: 'number', min: 1 },
  'tiktok.autosave_interval_seconds': { basic: true, type: 'number', min: 1 },
  'tiktok.follow_tracking': { basic: true },
  'tiktok.follow_tracking.mode': { basic: true, type: 'select', options: ['all_time','per_stream'] },
  'tiktok.like_rate_limit': { basic: true },
  'tiktok.like_rate_limit.enabled': { basic: true, type: 'bool' },
  'tiktok.like_rate_limit.max_per_user_per_minute': { basic: true, type: 'number', min: 0 },

  'random_triggers': { basic: true },
  'random_triggers.mode': { basic: true, type: 'select', options: ['deny-all','allow-all'] },
  'console.log_level': { basic: false, type: 'number', min: 0, max: 5 },
  'console.visible': { basic: false, type: 'bool' },
  'console.allow_close': { basic: false, type: 'bool' },
  'minecraft_server_api.api_port': { basic: false, type: 'number', min: 1, max: 65535 },
  'minecraft_server_api.web_server_port': { basic: false, type: 'number', min: 1, max: 65535 },
  'gui.enabled': { basic: true, type: 'bool' },
  'update.enabled': { basic: true, type: 'bool' },
  'update.auto_install': { basic: true, type: 'bool' },
  'update.max_update_logs': { basic: true, type: 'number' },
  'overlay.enabled': { basic: true, type: 'bool' },
  'overlay.display_mode': { basic: true, type: 'select', options: ['overwrite','queue'] },
  'overlay.fade_in': { basic: true, type: 'number', min: 0 },
  'overlay.fade_out': { basic: true, type: 'number', min: 0 },
  'overlay.max_fails': { basic: true, type: 'number', min: 1 },
  'overlay.cooldown': { basic: true, type: 'number', min: 0 },
  'overlay.overlays': { basic: true, type: 'json' },
  'overlay.theme.background': { basic: true, type: 'color' },
  'overlay.theme.text': { basic: true, type: 'color' },
  'theme': { basic: true },
  'api_key': { basic: false, type: 'password' },
  'port_policy.auto_resolve': { basic: false, type: 'bool' },
  'port_policy.session_only': { basic: false, type: 'bool' },
  'port_policy.max_offset': { basic: false, type: 'number', min: -1 },
  'plugin_sandbox.enabled': { basic: false, type: 'bool' },
  'plugin_sandbox.profile': { basic: false, type: 'select', options: ['', 'light', 'moderate', 'strict'] },
  'plugin_sandbox.max_memory_mb': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.max_cpu_time': { basic: false, type: 'number', min: 0 },
  'plugin_sandbox.max_files': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.max_processes': { basic: false, type: 'number', min: 1 },
  'plugin_sandbox.priority_class': { basic: false, type: 'select', options: ['below_normal', 'idle'] },

  'like_triggers': { basic: true },
  'like_triggers[].id': { basic: true, type: 'text' },
  'like_triggers[].every': { basic: true, type: 'number', min: 1 },
  'like_triggers[].function': { basic: true, type: 'text' },
  'like_triggers[].payload': { basic: true, type: 'text' },
  'like_triggers[].enabled': { basic: true, type: 'bool' },

  'outbound': { basic: true },
  'outbound.enabled': { basic: true, type: 'bool' },
  'outbound.max_fails': { basic: true, type: 'number', min: 1 },
  'outbound.cooldown': { basic: true, type: 'number', min: 0 },
  'outbound.retries': { basic: true, type: 'number', min: 0 },
  'outbound.timeout': { basic: true, type: 'number', min: 1 },
  'outbound.channels': { basic: true, type: 'list' },
};

/** Return editor metadata (label, help and type) for a config path. */
function getMeta(path) {
  if (FIELD_META[path]) return FIELD_META[path];
  const p = path.replace(/\.groups\[\d+\]/, '.groups[]').replace(/\.triggers\[\d+\]/, '.triggers[]').replace(/\.overlays\[\d+\]/, '.overlays[]').replace(/\.commands_config\.\w+/, '.commands_config[]').replace(/\.like_triggers\[\d+\]/, '.like_triggers[]');
  return FIELD_META[p] || { basic: false, type: 'text' };
}

/** Normalize a config path to the dot-separated form used by editor metadata. */
function _normalizeEditorPath(path) {
  return path
    .replace(/\.groups\[\d+\]/, '.groups[]')
    .replace(/\.triggers\[\d+\]/, '.triggers[]')
    .replace(/\.overlays\[\d+\]/, '.overlays[]')
    .replace(/\.commands_config\.\w+/, '.commands_config[]')
    .replace(/\.like_triggers\[\d+\]/, '.like_triggers[]');
}

/** Return whether the editor language is German. */
function _editorLangIsDe() {
  return window.I18N && I18N.lang && I18N.lang() === 'de';
}

/** Return localized help text for a config path. */
function getHelp(path) {
  const p = HELP_TEXT[path] ? path : _normalizeEditorPath(path);
  const en = HELP_TEXT[p];
  if (!en) return '';
  if (_editorLangIsDe() && HELP_TEXT_DE[p]) return HELP_TEXT_DE[p];
  return en;
}

/** Return the section metadata used to group configuration fields. */
function sectionMeta(key) {
  const en = SECTION_META[key] || null;
  if (!_editorLangIsDe() || !en) return en;
  return SECTION_META_DE[key] || en;
}

/** Return the localized display label for a configuration category. */
function categoryLabel(cat) {
  if (_editorLangIsDe() && CATEGORY_LABELS_DE[cat]) return CATEGORY_LABELS_DE[cat];
  return cat;
}

