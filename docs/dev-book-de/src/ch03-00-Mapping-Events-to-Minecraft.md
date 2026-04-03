# Mapping zwischen Events und Minecraft

### Das große Rätsel: Wie verbindet sich TikTok mit Minecraft?

Du weißt jetzt, wie **Events** in Python verarbeitet werden. Aber:

> Wie sagt das Programm Minecraft, was es tun soll?

**Event-Handler queued eine Aktion, aber:** Was ist eine Aktion? Wie wird sie zu einem Minecraft-Befehl?

**Die Antwort:** Ein **Mapping-System** das Events zu Minecraft-Commands übersetzt.

```
TikTok-Event (Gift, Follow, Like)
        ↓
Event-Handler
        ↓
Queue: ("GIFT_ROSE", "anna_xyz")
        ↓
MAPPING-SYSTEM (dieses Kapitel!)
        ↓
Minecraft-Command ausgeführt
        ↓
Etwas passiert im Spiel!
```

---

### Das Mapping visualisiert

Das Mapping funktioniert wie ein großes Nachschlagewerk:

```
TRIGGER (aus Event)  →  MINECRAFT COMMAND
─────────────────────────────────────────────────────
"GIFT_ROSE"          →       /give @s rose
"GIFT_DIAMOND"       →       /give @s diamond
"FOLLOW"             →       /say Willkommen!
"LIKE_GOAL_100"      →       /summon firework_rocket
```

**Die Datei `actions.mca`:** Das ist unsere Mapping-Tabelle! Sie *definiert* was passiert, wenn ein Trigger kommt.

---

### Der komplette Ablauf (Überblick)

Wenn jemand auf TikTok folgt, passiert:

```
1. TikTok sendet: FollowEvent
2. Python-Handler: on_follow() aufgerufen
3. Handler queuet: ("FOLLOW", username)
4. Worker-Thread: `for trigger, user in trigger_queue.get():`
5. Worker-Thread: `action = ACTIONS_MAP["FOLLOW"]`
6. Worker-Thread: `send_command_to_minecraft(action)`
7. RCON-Protokoll: Command wird gesendet (über Netzwerk)
8. Minecraft-Server: `/say Willkommen, anna_xyz!`
9. **Ergebnis:** Im Chat erscheint die Nachricht
```

**Dieser Ablauf kann bei einem Follow **< 100ms dauern!** Von TikTok bis Minecraft!**

---

### Wichtig zu verstehen

**3 Dinge zusammen machen das System:**

1. **actions.mca** – Die Datei mit allen Mappings (statisch)
2. **Code in main.py** – Liest die Datei beim Start
3. **RCON-Protokoll** – Sendet Commands an Minecraft (Netzwerk)

**Warum diese Aufteilung?**

- ✓ User können die `actions.mca` bearbeiten ohne Code zu ändern
- ✓ Fehler in der Datei werden beim Start erkannt
- ✓ Commands können dynamisch generiert werden

---

### Nach diesem Kapitel wirst du verstehen:

- Wie eine `.mca` Datei aufgebaut ist
- Warum Validator wichtig ist
- Wie man eigene Commands hinzufügt
- Warum RCON "insecure" ist (und warum das OK ist)
- Wann man .mcfunction-Dateien braucht

Weiter zu:
→ [Die actions.mca Datei](./ch03-01-The-actions.mca-File.md)