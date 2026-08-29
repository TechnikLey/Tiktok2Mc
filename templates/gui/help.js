/* ─── Help module ───
 * In-app context help for the dashboard. Unlike the dev docs
 * (docs/dev-book-{en,de}/), the content below ships inside the GUI itself, so
 * end users never need to read developer documentation.
 *
 * Two responsibilities:
 *   1. Help topic content (per view, bilingual DE/EN) rendered in a modal.
 *   2. formatApiError() — translates raw HTTP status codes and backend error
 *      codes (e.g. "TIKTOK-0001", see src/core/error_codes.py) into readable,
 *      actionable messages for toasts / inline error slots.
 *
 * Usage:
 *   Help.openHelp('status')         -> open the help modal for the Status view
 *   Help.closeHelp()                -> close the help modal
 *   Help.formatApiError(500, '...') -> friendly localized message string
 */
(function () {
  'use strict';

  const LANG_FALLBACK = 'en';

  const _content = {
    status: {
      title: { en: 'Status', de: 'Status' },
      sections: [
        {
          h: { en: 'System Status', de: 'Systemstatus' },
          body: {
            en: [
              'This page gives you a quick overview of the whole system: server version, active plugins, configuration state, uptime and the TikTok Live connection.',
              'All values refresh automatically. If a value shows "Offline" or "Not configured", use the Settings view to fix it.',
            ],
            de: [
              'Diese Seite gibt dir einen schnellen Überblick über das gesamte System: Serverversion, aktive Plugins, Konfigurationsstatus, Betriebszeit und die TikTok-Live-Verbindung.',
              'Alle Werte aktualisieren sich automatisch. Zeigt ein Wert „Offline" oder „Nicht konfiguriert", behebe das über die Einstellungen.',
            ],
          },
        },
        {
          h: { en: 'Live Statistics', de: 'Live-Statistiken' },
          body: {
            en: [
              'Shows live numbers from the TikTok→Minecraft bridge: RCON queue size, trigger queue size, events per minute and today\u2019s gift value.',
              'The queue cards turn yellow when a queue grows and red when it is very full. A large RCON queue usually means the Minecraft server cannot keep up with commands.',
            ],
            de: [
              'Zeigt Live-Zahlen aus der TikTok→Minecraft-Bridge: RCON-Warteschlangenlänge, Trigger-Warteschlangenlänge, Events pro Minute und den heutigen Geschenk-Wert.',
              'Die Warteschlangen-Karten werden gelb, wenn eine Warteschlange wächst, und rot, wenn sie sehr voll ist. Eine große RCON-Warteschlange bedeutet meist, dass der Minecraft-Server mit den Befehlen nicht nachkommt.',
            ],
          },
        },
        {
          h: { en: 'Plugin Health', de: 'Plugin-Status' },
          body: {
            en: [
              'Lists every registered plugin with its current state. Use the Plugins view to enable, disable or restart plugins and to edit their configuration.',
            ],
            de: [
              'Listet jedes registrierte Plugin mit seinem aktuellen Zustand. Über die Plugins-Ansicht kannst du Plugins aktivieren, deaktivieren oder neu starten und deren Konfiguration bearbeiten.',
            ],
          },
        },
      ],
    },

    plugins: {
      title: { en: 'Plugins', de: 'Plugins' },
      sections: [
        {
          h: { en: 'Plugin Management', de: 'Plugin-Verwaltung' },
          body: {
            en: [
              'Plugins extend TikTok2Mc (for example overlay widgets, chat integrations or counters). Here you can enable, disable and restart them and open their configuration.',
              'Be careful with plugins from external sources: they run their own process and could contain harmful code. Only enable plugins you trust.',
            ],
            de: [
              'Plugins erweitern TikTok2Mc (z. B. Overlay-Widgets, Chat-Integrationen oder Zähler). Hier kannst du sie aktivieren, deaktivieren und neu starten sowie ihre Konfiguration öffnen.',
              'Sei vorsichtig bei Plugins aus externen Quellen: Sie laufen als eigener Prozess und können schädlichen Code enthalten. Aktiviere nur Plugins, denen du vertraust.',
            ],
          },
        },
        {
          h: { en: 'Configuration', de: 'Konfiguration' },
          body: {
            en: [
              'Plugin settings are shown as a form built from the plugin\u2019s schema. Use the search box to filter settings and "Advanced" to reveal expert options.',
              'If a plugin provides no schema, you can edit the raw JSON. Invalid JSON is rejected on save. After saving, the plugin is usually restarted automatically.',
            ],
            de: [
              'Plugin-Einstellungen werden als Formular angezeigt, das aus dem Schema des Plugins erzeugt wird. Nutze die Suche zum Filtern und „Erweitert", um Expertenoptionen einzublenden.',
              'Stellt ein Plugin kein Schema bereit, kannst du das rohe JSON bearbeiten. Ungültiges JSON wird beim Speichern abgelehnt. Nach dem Speichern wird das Plugin in der Regel automatisch neu gestartet.',
            ],
          },
        },
        {
          h: { en: 'Keyboard Shortcuts', de: 'Tastenkürzel' },
          body: {
            en: [
              'Ctrl+S saves the current changes.',
            ],
            de: [
              'Ctrl+S speichert die aktuellen Änderungen.',
            ],
          },
        },
      ],
    },

    hooks: {
      title: { en: 'Hooks', de: 'Hooks' },
      sections: [
        {
          h: { en: 'What are Hooks?', de: 'Was sind Hooks?' },
          body: {
            en: [
              'Hooks are small scripts that run inside the TikTok2Mc process and react to events (for example "update the stream title when a gift arrives"). They are lightweight and restart with the app.',
              'Unlike plugins they run in-process, so a crashing hook can affect the whole system. Keep installed hooks to a minimum.',
            ],
            de: [
              'Hooks sind kleine Skripte, die innerhalb des TikTok2Mc-Prozesses laufen und auf Events reagieren (z. B. „Streamtitel aktualisieren, wenn ein Geschenk eintrifft"). Sie sind leichtgewichtig und starten mit der App neu.',
              'Anders als Plugins laufen sie im selben Prozess — ein abstürzender Hook kann daher das gesamte System beeinträchtigen. Halte die Zahl der installierten Hooks klein.',
            ],
          },
        },
        {
          h: { en: 'Enable / Configure', de: 'Aktivieren / Konfigurieren' },
          body: {
            en: [
              'Enable or disable a hook with its toggle. Changes take effect after a restart. Use "Configuration" to edit schema-based settings or raw JSON.',
            ],
            de: [
              'Aktiviere oder deaktiviere einen Hook über seinen Schalter. Änderungen werden erst nach einem Neustart wirksam. Über „Konfiguration" bearbeitest du Schema-basierte Einstellungen oder rohes JSON.',
            ],
          },
        },
        {
          h: { en: 'Keyboard Shortcuts', de: 'Tastenkürzel' },
          body: {
            en: [
              'Ctrl+S saves the current changes.',
            ],
            de: [
              'Ctrl+S speichert die aktuellen Änderungen.',
            ],
          },
        },
      ],
    },

    overlays: {
      title: { en: 'Overlays', de: 'Overlays' },
      sections: [
        {
          h: { en: 'Overlay URLs', de: 'Overlay-URLs' },
          body: {
            en: [
              'Overlays are browser pages that display TikTok events on stream (gift animations, recent viewers, comments). Add the URL as a "Browser Source" in OBS Studio, Streamlabs or any other streaming software.',
              'The built-in overlay is always available; plugins can register additional overlays, which appear in the "Plugin Overlays" section.',
            ],
            de: [
              'Overlays sind Browser-Seiten, die TikTok-Events auf dem Stream anzeigen (Geschenk-Animationen, letzte Zuschauer, Kommentare). Füge die URL in OBS Studio, Streamlabs oder einer anderen Streaming-Software als „Browser-Quelle" hinzu.',
              'Das eingebaute Overlay ist immer verfügbar; Plugins können zusätzliche Overlays registrieren, die im Abschnitt „Plugin-Overlays" erscheinen.',
            ],
          },
        },
        {
          h: { en: 'Preview & Test', de: 'Vorschau & Test' },
          body: {
            en: [
              'Every overlay has a live preview right in the dashboard. Click "Test" to send a sample message to the overlay — it appears in the preview and in your OBS browser source instantly.',
              'The preview uses a transparent background so it blends into the dashboard; the URL you copy for OBS uses the chroma-key background so it can be filtered out in your streaming software.',
            ],
            de: [
              'Jedes Overlay hat eine Live-Vorschau direkt im Dashboard. Klicke „Testen", um eine Beispielnachricht an das Overlay zu senden — sie erscheint sofort in der Vorschau und in deiner OBS-Browser-Quelle.',
              'Die Vorschau verwendet einen transparenten Hintergrund, damit sie ins Dashboard passt; die kopierte URL für OBS nutzt den Chroma-Key-Hintergrund, damit er in deiner Streaming-Software herausgefiltert werden kann.',
            ],
          },
        },
      ],
    },

    actions: {
      title: { en: 'Actions', de: 'Aktionen' },
      sections: [
        {
          h: { en: 'Event Triggers', de: 'Event-Trigger' },
          body: {
            en: [
              'Actions define what happens when a TikTok event occurs: a Follow, a Like, a Comment, a Gift or a custom event. Every trigger has a name, a status and a list of commands that run when it fires.',
              'Disabled triggers are skipped. Duplicate enabled triggers are rejected when saving.',
            ],
            de: [
              'Aktionen legen fest, was passiert, wenn ein TikTok-Event eintritt: ein Follow, ein Like, ein Kommentar, ein Geschenk oder ein benutzerdefiniertes Event. Jeder Trigger hat einen Namen, einen Status und eine Liste von Befehlen, die beim Auslösen laufen.',
              'Deaktivierte Trigger (## in der Datei) werden übersprungen. Doppelte aktivierte Trigger werden beim Speichern abgelehnt.',
            ],
          },
        },
        {
          h: { en: 'Command Types', de: 'Befehlstypen' },
          body: {
            en: [
              'Each command starts with a prefix that decides how it is executed:',
            ],
            de: [
              'Jeder Befehl beginnt mit einem Präfix, das bestimmt, wie er ausgeführt wird:',
            ],
          },
          list: {
            en: [
              '<code>/</code> vanilla — runs directly in Minecraft',
              '<code>!</code> rcon — sent via RCON to a server / plugin',
              '<code>$</code> script — runs a script file',
              '<code>&</code> shell — executed as a system command',
              '<code>>></code> overlay — shown in the overlay',
              '<code>@name>></code> named overlay — shown in a specific overlay',
              '<code>xN</code> multiplies a command, <code>{user}</code> / <code>{comment}</code> are placeholders',
            ],
            de: [
              '<code>/</code> vanilla — wird direkt in Minecraft ausgeführt',
              '<code>!</code> rcon — wird per RCON an einen Server / ein Plugin gesendet',
              '<code>$</code> Skript — führt eine Skriptdatei aus',
              '<code>&</code> Shell — wird als Systembefehl ausgeführt',
              '<code>>></code> Overlay — wird im Overlay angezeigt',
              '<code>@name>></code> benanntes Overlay — wird in einem bestimmten Overlay angezeigt',
              '<code>xN</code> multipliziert einen Befehl, <code>{user}</code> / <code>{comment}</code> sind Platzhalter',
            ],
          },
        },
        {
          h: { en: 'Keyboard Shortcuts', de: 'Tastenkürzel' },
          body: {
            en: [
              'Ctrl+S saves the current changes.',
            ],
            de: [
              'Ctrl+S speichert die aktuellen Änderungen.',
            ],
          },
        },
      ],
    },

    reactions: {
      title: { en: 'Reactions', de: 'Reaktionen' },
      sections: [
        {
          h: { en: 'What are Reactions?', de: 'Was sind Reaktionen?' },
          body: {
            en: [
              'Reactions connect an event to a plugin command: "When this happens, run that command on this plugin." For example: "When I die in Minecraft, pause my Spotify music."',
              'A reaction has three steps: the triggering event, the plugin, and the command to run. You can type a custom event name to integrate with external tools.',
            ],
            de: [
              'Reaktionen verbinden ein Event mit einem Plugin-Befehl: „Wenn das passiert, führe diesen Befehl auf diesem Plugin aus." Zum Beispiel: „Wenn ich in Minecraft sterbe, pausiere meine Spotify-Musik."',
              'Eine Reaktion besteht aus drei Schritten: dem auslösenden Event, dem Plugin und dem auszuführenden Befehl. Für die Integration mit externen Tools kannst du einen benutzerdefinierten Eventnamen eingeben.',
            ],
          },
        },
        {
          h: { en: 'Testing', de: 'Testen' },
          body: {
            en: [
              'The "Test" button sends a test event so you can verify a reaction without waiting for a real event. The plugin must be enabled for the reaction to fire.',
            ],
            de: [
              'Der „Testen"-Button sendet ein Test-Event, damit du eine Reaktion verifizieren kannst, ohne auf ein echtes Event zu warten. Damit die Reaktion ausgelöst wird, muss das Plugin aktiviert sein.',
            ],
          },
        },
        {
          h: { en: 'Keyboard Shortcuts', de: 'Tastenkürzel' },
          body: {
            en: [
              'Ctrl+S saves the current changes.',
            ],
            de: [
              'Ctrl+S speichert die aktuellen Änderungen.',
            ],
          },
        },
      ],
    },

    commentCommands: {
      title: { en: 'Comment Commands', de: 'Kommentar-Befehle' },
      sections: [
        {
          h: { en: 'What are Comment Commands?', de: 'Was sind Kommentar-Befehle?' },
          body: {
            en: [
              'Comment commands let viewers run actions via the TikTok live chat: when a viewer types a registered command (for example "!discord"), the configured handler answers automatically.',
              'Use "+ Add Command Group" to create a group in three steps: basic data (prefix and handler), access (enabled state, allowed roles, mode) and the commands with their responses.',
            ],
            de: [
              'Kommentar-Befehle lassen Viewer über den TikTok-Live-Chat Aktionen auslösen: Tippt ein Viewer einen registrierten Befehl (z. B. „!discord"), antwortet der konfigurierte Handler automatisch.',
              'Mit „+ Befehlsgruppe hinzufügen" legst du eine Gruppe in drei Schritten an: Basisdaten (Präfix und Handler), Zugriff (Aktiv-Status, erlaubte Rollen, Modus) und die Befehle mit ihren Antworten.',
            ],
          },
        },
        {
          h: { en: 'Handlers & Overrides', de: 'Handler & Overrides' },
          body: {
            en: [
              'Each group has a handler: RCON runs a command on your Minecraft server, HTTP sends a request to a web URL and Plugin routes the command to an installed plugin.',
              'Per command you can set overrides that replace the group defaults — for example an extra cooldown, restricted roles or a different handler. Use the search box to filter groups.',
            ],
            de: [
              'Jede Gruppe hat einen Handler: RCON führt einen Befehl auf deinem Minecraft-Server aus, HTTP sendet eine Anfrage an eine Web-URL und Plugin leitet den Befehl an ein installiertes Plugin weiter.',
              'Pro Befehl kannst du Overrides setzen, die die Gruppen-Standards ersetzen — z. B. einen zusätzlichen Cooldown, eingeschränkte Rollen oder einen anderen Handler. Über die Suche filterst du die Gruppen.',
            ],
          },
        },
        {
          h: { en: 'Master Switch & Cooldowns', de: 'Hauptschalter & Cooldowns' },
          body: {
            en: [
              'The "Enable all command groups" switch at the top turns every group on or off at once. The global cooldown limits how often any command may fire, the global user cooldown how often a single viewer may trigger one.',
              'Remember to save your changes with "Save Changes" or Ctrl+S.',
            ],
            de: [
              'Der Schalter „Alle Befehlsgruppen aktivieren" oben schaltet alle Gruppen gleichzeitig ein oder aus. Der globale Cooldown begrenzt, wie oft überhaupt ein Befehl ausgelöst werden darf, der globale Benutzer-Cooldown, wie oft ein einzelner Viewer einen auslösen kann.',
              'Vergiss nicht, deine Änderungen mit „Änderungen speichern" oder Ctrl+S zu sichern.',
            ],
          },
        },
      ],
    },

    chatbot: {
      title: { en: 'Chatbot', de: 'Chatbot' },
      sections: [
        {
          h: { en: 'What does the bot do?', de: 'Was macht der Bot?' },
          body: {
            en: [
              'The chatbot writes messages into the TikTok live chat on its own: it thanks viewers for gifts and follows, welcomes them to the stream and answers keyword commands (e.g. "!discord").',
              'Reading events works without a login, but for sending messages the bot needs a one-time TikTok sign-in with a session ID (see below).',
            ],
            de: [
              'Der Chatbot schreibt selbstständig Nachrichten in den TikTok-Live-Chat: Er bedankt sich bei Geschenken und Follows, heißt Viewer willkommen und beantwortet Keyword-Befehle (z. B. „!discord").',
              'Das Lesen von Events funktioniert ohne Login, zum Senden braucht der Bot aber eine einmalige TikTok-Anmeldung mit einer Session-ID (siehe unten).',
            ],
          },
        },
        {
          h: { en: 'TikTok sign-in (session ID)', de: 'TikTok-Anmeldung (Session-ID)' },
          body: {
            en: [
              'To let the bot post, copy the session ID of your logged-in TikTok account from your browser and paste it into the field in the Chatbot tab, then click "Sign in".',
              'The session ID is as valuable as a password: it is stored encrypted on this device only and never shown in full again. If sends start failing, the session has probably expired, just sign in again.',
            ],
            de: [
              'Damit der Bot schreiben kann, kopiere die Session-ID deines eingeloggten TikTok-Accounts aus dem Browser und füge sie in das Feld im Chatbot-Tab ein. Klicke dann auf „Anmelden".',
              'Die Session-ID ist so wertvoll wie ein Passwort: Sie wird nur verschlüsselt auf diesem Gerät gespeichert und nie wieder vollständig angezeigt. Schlägt das Senden fehl, ist sie vermutlich abgelaufen, einfach neu anmelden.',
            ],
          },
        },
        {
          h: { en: 'Spam protection & risks', de: 'Spam-Schutz & Risiken' },
          body: {
            en: [
              'TikTok limits chat messages strictly. The built-in protection keeps a minimum interval, a per-minute limit and drops duplicates automatically.',
              'Automated posts are a grey area in TikTok\u2019s terms of service, so keep the limits conservative and prefer a dedicated bot account over your main account.',
            ],
            de: [
              'TikTok limitiert Chat-Nachrichten streng. Der eingebaute Schutz hält einen Mindestabstand, ein Minuten-Limit und überspringt Duplikate automatisch.',
              'Automatisierte Posts sind eine ToS-Grauzone, halte die Limits also konservativ und benutze lieber einen eigenen Bot-Account statt des Haupt-Accounts.',
            ],
          },
        },
      ],
    },

    settings: {
      title: { en: 'Settings', de: 'Einstellungen' },
      sections: [
        {
          h: { en: 'Configuration Editor', de: 'Konfigurations-Editor' },
          body: {
            en: [
              'The configuration is grouped by category (Connection, Minecraft, System, Chat & Commands). Use the search box to find a setting quickly.',
              'Most settings apply immediately after saving. Some require a restart — a banner will remind you.',
            ],
            de: [
              'Die Konfiguration ist nach Kategorien gruppiert (Verbindung, Minecraft, System, Chat & Befehle). Nutze die Suche, um eine Einstellung schnell zu finden.',
              'Die meisten Einstellungen werden sofort nach dem Speichern angewendet. Einige erfordern einen Neustart — ein Banner erinnert dich daran.',
            ],
          },
        },
        {
          h: { en: 'Advanced Settings', de: 'Erweiterte Einstellungen' },
          body: {
            en: [
              'Expert options are hidden behind the "Advanced" button. Unlocking them requires typing a confirmation phrase, because misconfiguration can break the system.',
            ],
            de: [
              'Expertenoptionen sind hinter dem „Erweitert"-Button verborgen. Zum Freischalten musst du einen Bestätigungssatz eingeben, weil eine falsche Konfiguration das System beschädigen kann.',
            ],
          },
        },
        {
          h: { en: 'Keyboard Shortcuts', de: 'Tastenkürzel' },
          body: {
            en: [
              'Ctrl+S saves the current changes and / focuses the search box.',
            ],
            de: [
              'Ctrl+S speichert die aktuellen Änderungen und / fokussiert das Suchfeld.',
            ],
          },
        },
      ],
    },

    log: {
      title: { en: 'Live Log', de: 'Live-Log' },
      sections: [
        {
          h: { en: 'Log Stream', de: 'Log-Stream' },
          body: {
            en: [
              'Shows the live log of the whole system. Filter by level (Info, Warn, Error, Critical, Debug), search the entries and pause auto-scroll to inspect older lines.',
              'Use "Export" to save the current log as a file — this is very helpful when reporting a problem.',
            ],
            de: [
              'Zeigt das Live-Log des gesamten Systems. Filtere nach Ebene (Info, Warn, Fehler, Kritisch, Debug), durchsuche die Einträge und pausiere den Auto-Scroll, um ältere Zeilen zu prüfen.',
              'Mit „Exportieren" speicherst du das aktuelle Log als Datei — das ist sehr hilfreich, wenn du ein Problem meldest.',
            ],
          },
        },
        {
          h: { en: 'Crash Reports', de: 'Absturzberichte' },
          body: {
            en: [
              'If a component crashed, the report is listed here and can be opened to inspect the stack trace. Crash reports help the developers fix bugs.',
            ],
            de: [
              'Wenn eine Komponente abgestürzt ist, wird der Bericht hier aufgelistet und kann geöffnet werden, um den Stack-Trace zu prüfen. Absturzberichte helfen den Entwicklern, Fehler zu beheben.',
            ],
          },
        },
      ],
    },

    console: {
      title: { en: 'Console', de: 'Konsole' },
      sections: [
        {
          h: { en: 'RCON Connection', de: 'RCON-Verbindung' },
          body: {
            en: [
              'The console opens an RCON session to a Minecraft server so you can send commands directly. Select a server from the dropdown and click "Connect".',
              'RCON must be enabled in the TikTok2Mc settings (Settings → Minecraft → RCON) and on the server you want to connect to.',
            ],
            de: [
              'Die Konsole öffnet eine RCON-Sitzung zu einem Minecraft-Server, damit du Befehle direkt senden kannst. Wähle einen Server aus der Liste und klicke auf „Verbinden".',
              'RCON muss in der server.properties des Servers und in den TikTok2Mc-Einstellungen aktiviert sein (Einstellungen → Minecraft → RCON).',
            ],
          },
        },
        {
          h: { en: 'Autocomplete & History', de: 'Autovervollständigung & Verlauf' },
          body: {
            en: [
              'Tab completes the current command (e.g. \u201Cga\u201D → \u201Cgamemode\u201D). Press Tab repeatedly to cycle through matching commands.',
              'The ↑/↓ arrow keys navigate the command history from the current session. The last 50 commands are also remembered between restarts.',
            ],
            de: [
              'Tab vervollständigt den aktuellen Befehl (z. B. „ga\u201D → „gamemode\u201D). Mehrfaches Drücken von Tab blättert durch die passenden Befehle.',
              'Mit den Pfeiltasten ↑/↓ navigierst du durch den Befehlsverlauf der aktuellen Sitzung. Die letzten 50 Befehle werden auch über Neustarts hinweg gespeichert.',
            ],
          },
        },
      ],
    },

    servers: {
      title: { en: 'Server Manager', de: 'Server-Manager' },
      sections: [
        {
          h: { en: 'Instances', de: 'Instanzen' },
          body: {
            en: [
              'The Server Manager runs and manages Minecraft servers for you. Each instance has its own folder, port and version. Use "Create Server" to add one.',
              'An instance needs a server.jar. Download a tested PaperMC version ("Download Version"), import a custom jar ("Add Custom Version") or switch to an installed version.',
            ],
            de: [
              'Der Server-Manager startet und verwaltet Minecraft-Server für dich. Jede Instanz hat einen eigenen Ordner, Port und Version. Mit „Server erstellen" fügst du eine hinzu.',
              'Eine Instanz benötigt eine server.jar. Lade eine getestete PaperMC-Version herunter („Version herunterladen"), importiere eine benutzerdefinierte jar („Benutzerdefinierte Version") oder wechsle zu einer installierten Version.',
            ],
          },
        },
        {
          h: { en: 'Java', de: 'Java' },
          body: {
            en: [
              'If no compatible Java runtime is found, a banner appears and you can install Java with one click. Minecraft needs Java 17 or newer (depending on the version).',
            ],
            de: [
              'Wenn keine kompatible Java-Laufzeit gefunden wird, erscheint ein Banner und du kannst Java mit einem Klick installieren. Minecraft benötigt Java 17 oder neuer (je nach Version).',
            ],
          },
        },
      ],
    },

    revenue: {
      title: { en: 'Revenue', de: 'Einnahmen' },
      sections: [
        {
          h: { en: 'Revenue Tracking', de: 'Einnahmen-Tracking' },
          body: {
            en: [
              'Shows the gift value you received per day. Use the period buttons (All, 7, 30, 90 days) or a custom date range, and clear the filter to go back.',
              'Gross is what your viewers spent on coins (2 coins = 1 diamond, coins ≈ $0.013 each). Net is your payout after TikTok takes its share. The chart stacks the TikTok fee (hatched) below your net payout.',
              'The summary cards highlight your net payout, the gross viewer spend and TikTok\u2019s share, plus days with revenue, average per day, best and worst day.',
            ],
            de: [
              'Zeigt den pro Tag erhaltenen Geschenk-Wert. Nutze die Zeitraum-Buttons (Alle, 7, 30, 90 Tage) oder einen eigenen Datumsbereich und setze den Filter zurück, um zum Anfang zu gelangen.',
              'Brutto ist, was deine Zuschauer für Coins ausgegeben haben (2 Coins = 1 Diamant, Coins ≈ 0,013 $ ≈ 0,011 €). Netto ist deine Auszahlung nach TikToks Anteil. Das Diagramm stapelt die TikTok-Gebühr (schraffiert) unter deiner Netto-Auszahlung.',
              'Die Übersichtskarten heben deine Netto-Auszahlung, den Brutto-Zuschauer-Umsatz und TikToks Anteil hervor, dazu Tage mit Einnahmen, Durchschnitt pro Tag sowie besten und schlechtesten Tag.',
              'In der deutschen Oberfläche werden alle Beträge in Euro angezeigt (umgerechnet mit 1 $ ≈ 0,86 €).',
            ],
          },
        },
      ],
    },

    sessions: {
      title: { en: 'Sessions', de: 'Sessions' },
      sections: [
        {
          h: { en: 'Session Tracking', de: 'Session-Tracking' },
          body: {
            en: [
              'Whenever a live stream ends, TikTok2Mc automatically saves a summary with gifts, likes, follows, comments, shares, and joins for that session.',
              'The summary cards at the top show aggregated totals across all recorded sessions. The table below lists each session in reverse chronological order.',
              'Use "Download Report" to save a Markdown summary of all sessions to a file.',
            ],
            de: [
              'Wann immer ein Livestream endet, speichert TikTok2Mc automatisch eine Zusammenfassung mit Gifts, Likes, Follows, Kommentaren, Shares und Joins für diese Session.',
              'Die Übersichtskarten oben zeigen aggregierte Summen über alle aufgezeichneten Sessions. Die Tabelle unten listet jede Session in umgekehrter chronologischer Reihenfolge auf.',
              '"Bericht herunterladen" speichert eine Markdown-Zusammenfassung aller Sessions in eine Datei.',
            ],
          },
        },
      ],
    },

    triggers: {
      title: { en: 'Event Tester', de: 'Event-Tester' },
      sections: [
        {
          h: { en: 'Test Mode', de: 'Testmodus' },
          body: {
            en: [
              'The Event Tester simulates TikTok events to verify your setup. Simulated events behave exactly like real ones — be careful on a live server.',
            ],
            de: [
              'Der Event-Tester simuliert TikTok-Events, um dein Setup zu prüfen. Simulierte Events verhalten sich genau wie echte — sei auf einem Live-Server vorsichtig.',
            ],
          },
        },
        {
          h: { en: 'TikTok Connection', de: 'TikTok-Verbindung' },
          body: {
            en: [
              'The toggle disconnects or reconnects the live TikTok stream. Turning it OFF disconnects immediately, so the button asks for confirmation.',
            ],
            de: [
              'Der Schalter trennt oder verbindet den TikTok-Live-Stream. Beim AUSSCHALTEN wird sofort getrennt, daher fragt der Button nach einer Bestätigung.',
            ],
          },
        },
        {
          h: { en: 'Trigger Simulator', de: 'Trigger-Simulator' },
          body: {
            en: [
              'Pick an event type (Follow, Like, Join, Share, Comment, Gift, Custom), fill in the details (user, comment text, gift) and send the trigger. Recent events stay visible in the session history.',
            ],
            de: [
              'Wähle einen Eventtyp (Follow, Like, Join, Share, Kommentar, Geschenk, Benutzerdefiniert), fülle die Details aus (Benutzer, Kommentartext, Geschenk) und sende den Trigger. Kürzliche Events bleiben im Sitzungsverlauf sichtbar.',
            ],
          },
        },
      ],
    },

    updates: {
      title: { en: 'Updates', de: 'Updates' },
      sections: [
        {
          h: { en: 'Update System', de: 'Update-System' },
          body: {
            en: [
              'Check for new versions of TikTok2Mc and its plugins. Tool updates are applied and the application restarts; plugin updates are installed and require a restart to finish.',
            ],
            de: [
              'Suche nach neuen Versionen von TikTok2Mc und seinen Plugins. Tool-Updates werden angewendet und die Anwendung startet neu; Plugin-Updates werden installiert und benötigen einen Neustart zum Abschluss.',
            ],
          },
        },
      ],
    },
    backups: {
      title: { en: 'Backups', de: 'Backups' },
      sections: [
        {
          h: { en: 'Automatic Backups', de: 'Automatische Backups' },
          body: {
            en: [
              'A backup is created automatically whenever you save your configuration, your actions, plugin settings or the plugin registry. All backups are managed automatically and older copies are cleaned up.',
            ],
            de: [
              'Bei jedem Speichern deiner Konfiguration, deiner Aktionen, von Plugin-Einstellungen oder der Plugin-Registry wird automatisch ein Backup erstellt. Alle Backups werden automatisch verwaltet, ältere Kopien werden bereinigt.',
            ],
          },
        },
        {
          h: { en: 'Restore', de: 'Wiederherstellen' },
          body: {
            en: [
              'Each backup can be restored with the "Restore" button. A confirmation dialog warns you that the current file will be overwritten. A safety backup of the current state is created first, so the restore itself can be undone.',
            ],
            de: [
              'Jedes Backup lässt sich über die Schaltfläche „Wiederherstellen" zurückspielen. Ein Bestätigungsdialog weist darauf hin, dass die aktuelle Datei überschrieben wird. Vorher wird ein Sicherheits-Backup des aktuellen Stands erstellt, sodass auch die Wiederherstellung selbst rückgängig gemacht werden kann.',
            ],
          },
        },
        {
          h: { en: 'Backup Now', de: 'Jetzt sichern' },
          body: {
            en: [
              'Use "Backup Now" to create a snapshot of your config, actions and plugin registry on demand — for example before a larger change. Entries marked "Not restorable" are kept as reference only and cannot be restored directly.',
            ],
            de: [
              'Mit „Jetzt sichern" erstellst du jederzeit einen Schnappschuss von Konfiguration, Aktionen und Plugin-Registry — zum Beispiel vor einer größeren Änderung. Einträge mit „Nicht wiederherstellbar" dienen nur als Referenz und können nicht direkt wiederhergestellt werden.',
            ],
          },
        },
        {
          h: { en: 'Config Bundle', de: 'Config-Bundle' },
          body: {
            en: [
              'The config bundle collects your active configuration into a single ZIP: config.yaml, actions.mca, event_commands.yaml, and the config.yaml of every plugin and hook. "Export Bundle" downloads it; "Import Bundle" restores it on this or another device. During import every file is validated first and a safety backup is created before anything is overwritten. gifts.json is intentionally not part of the bundle.',
            ],
            de: [
              'Das Config-Bundle fasst deine aktive Konfiguration in einer einzigen ZIP zusammen: config.yaml, actions.mca, event_commands.yaml sowie die config.yaml jedes Plugins und Hooks. „Bundle exportieren" lädt es herunter; „Bundle importieren" stellt es auf diesem oder einem anderen Gerät wieder her. Beim Import wird jede Datei zuerst validiert und vor jedem Überschreiben ein Sicherheits-Backup erstellt. gifts.json ist absichtlich nicht Teil des Bundles.',
            ],
          },
        },
      ],
    },

    shortcuts: {
      title: { en: 'Keyboard Shortcuts', de: 'Tastenkürzel' },
      sections: [
        {
          h: { en: 'Global Shortcuts', de: 'Globale Kürzel' },
          body: {
            en: [
              'The dashboard supports keyboard shortcuts for the most common actions. They work in every view and in the editors.',
              'The "/" shortcut works on every keyboard layout, even when producing the character requires Shift (for example on German keyboards).',
            ],
            de: [
              'Das Dashboard unterstützt Tastenkürzel für die häufigsten Aktionen. Sie funktionieren in jeder Ansicht und in den Editoren.',
              'Das Kürzel „/" funktioniert auf jedem Tastaturlayout, auch wenn das Zeichen nur mit Umschalttaste erreichbar ist (z. B. auf deutschen Tastaturen).',
            ],
          },
          list: {
            en: [
              '<kbd>Ctrl</kbd> + <kbd>S</kbd> — Save the current changes in the active editor',
              '<kbd>/</kbd> — Focus the search field of the current view',
              '<kbd>Esc</kbd> — Close the topmost dialog / overlay',
            ],
            de: [
              '<kbd>Ctrl</kbd> + <kbd>S</kbd> — Aktuelle Änderungen im aktiven Editor speichern',
              '<kbd>/</kbd> — Suchfeld der aktuellen Ansicht fokussieren',
              '<kbd>Esc</kbd> — Obersten Dialog / Overlay schließen',
            ],
          },
        },
        {
          h: { en: 'Typing Safety', de: 'Eingabe-Sicherheit' },
          body: {
            en: [
              'Except for Ctrl+S and Esc, shortcuts are ignored while you are typing in an input field, so they never interfere with entering text or commands.',
            ],
            de: [
              'Außer für Ctrl+S und Esc werden Kürzel ignoriert, solange du in ein Eingabefeld tippst — so stören sie nie bei der Texteingabe oder bei Befehlen.',
            ],
          },
        },
      ],
    },
  };
  const _err = {
    operationFailed: { en: 'The operation failed.', de: 'Die Aktion ist fehlgeschlagen.' },
    seeLog: { en: 'Check the Live Log for more details.', de: 'Weitere Details findest du im Live-Log.' },
    retry: { en: 'Please try the action again.', de: 'Bitte versuche die Aktion erneut.' },
    auth: { en: 'Open the dashboard with your API key (?key=YOUR_KEY) to authenticate.', de: 'Öffne das Dashboard mit deinem API-Schlüssel (?key=YOUR_KEY), um dich zu authentifizieren.' },
  };

  const _status = {
    400: { en: 'The request was rejected.', de: 'Die Anfrage wurde abgelehnt.' },
    401: { en: 'Authentication failed.', de: 'Authentifizierung fehlgeschlagen.' },
    403: { en: 'You are not allowed to perform this action.', de: 'Du darfst diese Aktion nicht ausführen.' },
    404: { en: 'The requested item does not exist.', de: 'Das angeforderte Element existiert nicht.' },
    405: { en: 'This action is not supported.', de: 'Diese Aktion wird nicht unterstützt.' },
    409: { en: 'The change conflicts with the current state.', de: 'Die Änderung kollidiert mit dem aktuellen Zustand.' },
    422: { en: 'The submitted data is not valid.', de: 'Die übermittelten Daten sind ungültig.' },
    429: { en: 'Too many requests were sent.', de: 'Es wurden zu viele Anfragen gesendet.' },
    500: { en: 'The server encountered an unexpected error.', de: 'Der Server ist auf einen unerwarteten Fehler gestoßen.' },
    502: { en: 'The server received an invalid response.', de: 'Der Server hat eine ungültige Antwort erhalten.' },
    503: { en: 'The service is temporarily unavailable.', de: 'Der Dienst ist vorübergehend nicht verfügbar.' },
  };

  const _subsystemLabel = {
    API: { en: 'API server', de: 'API-Server' },
    BACKUP: { en: 'Backup', de: 'Backup' },
    CONFIG: { en: 'Configuration', de: 'Konfiguration' },
    CORE: { en: 'Core runtime', de: 'Kernsystem' },
    GUI: { en: 'Dashboard', de: 'Dashboard' },
    HOOK: { en: 'Hook system', de: 'Hook-System' },
    MC: { en: 'Minecraft / RCON', de: 'Minecraft / RCON' },
    NETWORK: { en: 'Network', de: 'Netzwerk' },
    OVERLAY: { en: 'Overlay', de: 'Overlay' },
    PLUGIN: { en: 'Plugin system', de: 'Plugin-System' },
    SECURITY: { en: 'Security', de: 'Sicherheit' },
    TIKTOK: { en: 'TikTok connection', de: 'TikTok-Verbindung' },
    UPDATE: { en: 'Update system', de: 'Update-System' },
  };

  function _lang() {
    if (typeof window.I18N !== 'undefined' && typeof I18N.lang === 'function') {
      return I18N.lang();
    }
    return LANG_FALLBACK;
  }

  function _extractCode(detail) {
    if (!detail) return null;
    const m = String(detail).match(/\b[A-Z]+-\d{4}\b/);
    return m ? m[0] : null;
  }

  function formatApiError(status, detail) {
    const lang = _lang();
    const code = _extractCode(detail);
    if (code) {
      const subsystem = code.split('-')[0];
      const label = _subsystemLabel[subsystem];
      if (label) {
        return label[lang] + ': ' + _err.operationFailed[lang] + ' ' + _err.seeLog[lang];
      }
      return _err.operationFailed[lang] + ' ' + _err.seeLog[lang];
    }
    const msg = _status[status];
    if (msg) {
      if (status === 401) return msg[lang] + ' ' + _err.auth[lang];
      if (status >= 500) return msg[lang] + ' ' + _err.seeLog[lang];
      return msg[lang] + ' ' + _err.retry[lang];
    }
    return _err.operationFailed[lang] + ' ' + _err.seeLog[lang];
  }

  /* ── Modal ── */
  let _current = _content.status;

  function _render() {
    const lang = _lang();
    const modal = document.getElementById('help-modal');
    if (!modal) return;
    const titleEl = document.getElementById('help-modal-title');
    if (titleEl) titleEl.textContent = _current.title[lang] || _current.title.en;
    const body = document.getElementById('help-modal-body');
    if (!body) return;
    body.innerHTML = _current.sections.map((sec) => {
      const heading = sec.h[lang] || sec.h.en;
      const paragraphs = (sec.body[lang] || sec.body.en)
        .map((p) => '<p>' + p + '</p>')
        .join('');
      const list = sec.list && sec.list[lang]
        ? '<ul>' + sec.list[lang].map((li) => '<li>' + li + '</li>').join('') + '</ul>'
        : '';
      return '<section class="help-section"><h4>' + heading + '</h4>' + paragraphs + list + '</section>';
    }).join('');
  }

  function _handleKeydown(e) {
    if (e.key === 'Escape') closeHelp();
  }

  function openHelp(topic) {
    const modal = document.getElementById('help-modal');
    if (!modal) return;
    _current = _content[topic] || _content.status;
    _render();
    modal.classList.remove('hidden');
    const closeBtn = document.getElementById('help-modal-close');
    if (closeBtn) closeBtn.focus();
    document.addEventListener('keydown', _handleKeydown);
  }

  function closeHelp() {
    const modal = document.getElementById('help-modal');
    if (modal) modal.classList.add('hidden');
    document.removeEventListener('keydown', _handleKeydown);
  }

  function isOpen() {
    const modal = document.getElementById('help-modal');
    return !!modal && !modal.classList.contains('hidden');
  }

  function init() {
    const modal = document.getElementById('help-modal');
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeHelp();
      });
    }
    document.addEventListener('i18n:changed', () => {
      if (isOpen()) _render();
    });
  }

  window.Help = {
    openHelp,
    closeHelp,
    isOpen,
    formatApiError,
    topics: Object.keys(_content),
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
