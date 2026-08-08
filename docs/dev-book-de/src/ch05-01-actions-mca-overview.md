# Actions.mca Referenz

Die `data/actions.mca` definiert, was passiert, wenn ein TikTok-Event eintrifft. Sie ist die Brücke zwischen TikTok-Events und Minecraft-Aktionen.

## Allgemeines Format

```
trigger: aktion1 ; aktion2 ; aktion3
```

- **Trigger**: Ein Event-Name (`follow`, `join`, `comment`, `likes`, `like_2`, `share`), eine Gift-ID (`5655`) oder ein benutzerdefinierter Name
- **Aktionen**: Eine oder mehrere durch Semikolon getrennte Aktionen
- **Datei-Pfad**: `data/actions.mca` (Fallback: `defaults/actions.mca`)

## Aktionstypen

| Typ | Beispiel | Beschreibung |
|-----|----------|--------------|
| Vanilla | `/effect give @a speed 10 1` | Minecraft-Befehl über Datapack-Funktion |
| RCON | `!say Hallo` | Befehl direkt per RCON an den Server |
| Hook | `$superjump` | Ruft einen registrierten Hook-Handler auf |
| Overlay | `>>Titel\|Untertitel\|5` | Text im Overlay anzeigen |
| Named Overlay | `@gifts>>Titel\|Text\|3` | Overlay auf einem bestimmten Kanal |
| Shell | `&notepad.exe` | Befehl auf dem Host-Rechner ausführen |

### Namens-Overlay

Mit `@name>>` kannst du Overlays auf einem bestimmten Kanal anzeigen:

```
follow: @default>>Willkommen!|{user}|3 ; @gifts>>Neuer Follower|{user}|3
```

### Multiplikator

Aktionen können mit `xN` wiederholt werden:

```
follow: /give @a diamond x5 ; !say x3
```

Der Multiplikator wird am Ende der Aktion notiert.

## Kommentare und Deaktivierung

### Vollständige Kommentare

Zeilen, die mit `#` beginnen (nach Entfernung von Leerzeichen), werden ignoriert:

```
# Das ist ein Kommentar
follow: /give @a diamond
```

### Deaktivierte Trigger

Zeilen, die mit `##` beginnen, werden geparst aber als deaktiviert markiert:

```
## follow: /give @a diamond
```

### Inline-Kommentare

Bei aktiven Zeilen wird Inhalt nach dem ersten `#` als Kommentar entfernt:

```
follow: /give @a diamond # das hier ist ein Kommentar
```

## Verarbeitung

```
TikTok-Event → on_comment() → trigger_worker()
    → execute_global_command(trigger, user)
        → Prüft: Ist trigger in script_actions?
            → Ja: Für jede Aktion unter trigger:
                → / → Minecraft-Befehl via Datapack
                → ! → RCON-Queue
                → $ → HOOK_ACTIONS[action](user, action, {})
                → >> → Overlay-Text
                → & → Shell-Befehl
```

## Beispiele

```mca
# TikTok-Standard-Events
follow:  $begruessung ; /give @a minecraft:bread 1
join:    >>Willkommen!|{user}|3
likes:   $like-effekt ; /playsound minecraft:entity.experience_orb.pickup master @a x3

# Gift-IDs
5655:    $geschenk ; !tnt 2 0.1 2
16111:   $grosses-geschenk ; /give @a minecraft:diamond x2

# Inline-Kommentar
share:   /give @a minecraft:emerald 1 # Belohnung fürs Teilen

# Deaktivierter Trigger
## likes: /kill @a

# Eigene Trigger (nur per Hook auslösbar)
bonus:   >>Bonus!|{user} hat gewonnen|4 ; /effect give @a speed 30 1
```

## Trigger-Namen mit Leerzeichen

Trigger-Namen mit Leerzeichen werden in der `actions.mca` automatisch in einfache Anführungszeichen gesetzt:

```
'mein trigger': /say Hallo
```

## Nächstes Kapitel

Der [Event-Command-Mapper](./ch05-02-event-command-mapper.md) für lose Kopplung zwischen Plugins.
