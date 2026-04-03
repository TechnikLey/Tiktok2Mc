# Eigenes Plugin erstellen

> [!WARNING]
> Aktuell nutzen alle Plugins die `config.yaml`.
> In Zukunft wird sich das jedoch ändern, da diese Datei ausschließlich
> für das Hauptprogramm vorgesehen sein soll.
> Die genaue Umsetzung wird in zukünftigen Updates eingeführt, und das Kapitel wird entsprechend angepasst.
> Behalte dies im Hinterkopf und halte Ausschau nach Änderungen.
>
> Du kannst bereits jetzt eine eigene `config.yaml` im Plugin-Ordner erstellen und diese für Einstellungen nutzen.
> So sparst du dir später Anpassungen am Code, wenn die globale `config.yaml` nicht mehr für Plugins verwendet werden darf.

###  Was ist ein Plugin?

Ein **Plugin** ist ein unabhängiges Python-Programm, das sich in das Streaming Tool integriert. Jedes Plugin:
- Läuft als **separater Prozess** (in der Registry registriert)
- **Kommuniziert über DCS** (HTTP) mit anderen Plugins
- Hat optional eine **GUI (ICS)** mit pywebview
- Wird zentral in `config.yaml` konfiguriert
- Hat **Zugriff auf Events** via Webhook

**Built-in Plugins (Beispiele):**
- **DeathCounter**: Zählt Tode, sendet an Minecraft
- **LikeGoal**: Verwaltet Like-Ziele
- **Timer**: Countdown-Timer
- **WinCounter**: Siege zählen

(Alle Build-in Plugins untersützen `ICS`)

### Plugin-Lifecycle

```
1. Plugin-Ordner erstellen (mit create_plugin.ps1) (plugins/myPlugin/)
   ↓
2. main.py schreiben (HTTP-Server, Event-Handler)
   ↓
3. In registry.py registrieren (PLUGIN_REGISTRY)
   ↓
4. config.yaml bearbeiten (Benutzerkonfiguration)
   ↓
5. In Start.py laden (Prozess starten)
   ↓
6. Events kommen via /webhook Endpoint
   ↓
7. Plugin verarbeitet, sendet Befehle
```

### Roadmap dieses Kapitels

1. **Plugin-Struktur verstehen** (Ordner, Dateien, Config)
2. **HTTP-Server mit Flask erstellen** (Events empfangen)
3. **Minecraft-Befehle senden** (RCON-Kommunikation)
4. **Datenspeicherung & Konfiguration** (Benutzerdaten)
5. **GUI mit pywebview** (Visuelles Interface optional)
6. **Zwischen Plugins kommunizieren** (HTTP + Fehlerbehandlung)
7. **Best Practices & Fehlerbehandlung** (Production-Ready)

→ **Start**: [Plugin-Struktur & Setup](./ch02-01-plugin-structure-and-setup.md)
- Logging in `logs/` Ordner
- Typische Fehler vermeiden
- Resource Management (Memory & Thread Leaks)

## Programmiersprachen: Python oder etwas anderes?

Ein Plugin muss nicht zwingend in Python geschrieben sein. Du kannst es grundsätzlich in jeder Programmiersprache entwickeln. Mehr dazu erfährst du im Kapitel [Plugin erstellen ohne Python](...).

**Aber Achtung:** Mit Python brauchst du etwa 20 Zeilen Code für die Basis. Mit anderen Sprachen (Java, C++, Rust, etc.) können das schnell mehrere hundert Zeilen werden, da du vieles selbst implementieren musst.

In Zukunft werden möglicherweise weitere Programmiersprachen direkt unterstützt. Python bleibt jedoch die primär unterstützte Sprache: mit den meisten Hilfestellungen, Integrationen und regelmäßigen Updates.

## Los geht's!

Bist du bereit? Dann starten wir mit [Plugin-Aufbau und Struktur](./ch02-01-plugin-structure-and-setup.md).

Nach dem Durcharbeiten dieser Kapitel wirst du verstehen:
- Wie Plugins technisch aufgebaut sind
- Wie Events dich erreichen und wie du darauf reagierst
- Wie du Konfiguration und Daten verwaltest
- Wie du GUIs mit pywebview baust
- Wie Plugins sich untereinander austauschen
- Wie du dein Plugin stabil hältst

Die konkrete Umsetzung und die kreative Nutzung dieser Tools – das ist dein Part! 