# Actions.mca Überblick

Die `actions.mca` ist eine Konfigurationsdatei, die TikTok-Events (oder benutzerdefinierte Trigger) auf Minecraft-Aktionen abbildet. Sie ist die zentrale Brücke zwischen dem Event-System und der Minecraft-Welt.

## Zweck

Die `actions.mca` definiert, was passieren soll, wenn ein bestimmtes TikTok-Event eintrifft:

```
follow: /give @a minecraft:golden_apple 1
```

Wenn jemand folgt, bekommen alle Spieler einen goldenen Apfel.

## Allgemeines Format

Jede Zeile hat das Format:

```
trigger: aktion1 ; aktion2 ; aktion3
```

- **Trigger**: Ein Event-Name (z. B. `follow`), eine Gift-ID (z. B. `5655`) oder ein benutzerdefinierter Name.
- **Aktionen**: Eine oder mehrere durch Semikolon getrennte Aktionen.

## Aktionstypen

Du kannst verschiedene Arten von Aktionen in der `actions.mca` verwenden:

| Typ | Beispiel | Beschreibung |
|---|---|---|
| Vanilla-Befehl | `/effect give @a speed 10 1` | Minecraft-Befehl über Datapack |
| RCON-Befehl | `!say Hallo` | Befehl direkt über RCON |
| Hook-Aktion | `$mein-befehl` | Ruft einen registrierten Hook-Handler auf |
| Overlay-Text | `>>Titel\|Untertitel\|5` | Zeigt Text im Overlay an |
| Shell-Befehl | `&notepad.exe` | Führt einen Befehl auf dem Host aus |

## Wie Plugin-Entwickler mit actions.mca interagieren

### Hooks registrieren

Als Hook-Entwickler registrierst du Aktionen, die in der `actions.mca` verwendet werden können:

```python
api.register_action("superjump", handler)
```

Der Benutzer trägt dann in der `actions.mca` ein:

```
follow: $superjump
```

### Eigene Trigger definieren

Du kannst eigene Trigger-Namen in der `actions.mca` definieren, die nie automatisch von TikTok ausgelöst werden, sondern nur über `api.enqueue_trigger()`:

```
mein-eigener-trigger: $mein-handler ; /say Trigger ausgelöst!
```

### Kombinationen

Eine Zeile kann mehrere Aktionstypen kombinieren:

```
follow: $superjump ; /give @a minecraft:diamond 1 ; >>Willkommen!|{user} ist da!|3
```

## Wichtige Hinweise

- Die `actions.mca` wird vom Benutzer bearbeitet. Dokumentiere in deinem Plugin oder Hook, welche `$`-Befehle definiert sind.
- Die Datei wird beim Start geladen und kann zur Laufzeit neu geladen werden.
- Kommentare mit `#` am Zeilenanfang werden ignoriert.
- Inline-Kommentare nach `#` werden ebenfalls ignoriert.

## Beispiel

```
# TikTok-Standard-Events
follow:    $begruessung ; /give @a minecraft:bread 1
like:      $like-effekt ; /playsound minecraft:entity.experience_orb.pickup master @a

# Gift-IDs
5655:      $geschenk ; !tnt 2 0.1 2
16111:     $grosses-geschenk

# Eigene Trigger
danke:     >>Danke!|{user}|4
```
