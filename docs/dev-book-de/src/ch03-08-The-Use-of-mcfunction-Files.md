# Der Nutzen von mcfunction-Dateien

### Das Problem: RCON ist das Engpas

Wenn jemand ein extremes Event definiert:

```
7168:/execute at @a run summon minecraft:wither ~ ~ ~ x500
```

Das bedeutet: **500 Wither spawnen!**

**Ohne Optimierung:**
- 500 einzelne RCON-Befehle senden → **Verbindung bricht ab!**
- Mit Throttling: ~5 Sekunden Verzögerung nur für dieses Event
- Andere Events müssen warten → **Queue läuft voll**

**Die Lösung:** `.mcfunction`-Dateien!

---

### Was sind .mcfunction-Dateien?

`.mcfunction`-Dateien speichern eine Liste von Vanilla-Befehlen, die der Minecraft-Server **intern** ausführt.

**Statt:**
```
RCON: /summon wither x1
RCON: /summon wither x1
...  (500x!)
```

**Jetzt:**
```
# 7168.mcfunction (gespeichert datei)
/execute at @a run summon minecraft:wither ~ ~ ~
/execute at @a run summon minecraft:wither ~ ~ ~
... (500x als Text!)
```

**Und dann nur:**
```
RCON: function namespace:7168
```

→ **Ein Befehl statt 500!**

---

### Der Prozess

```
1. Programmstart
   ↓
2. actions.mca wird gelesen
   ↓
3. Für jeden `/`-Befehl mit `xN` (N > 1):
   → Schreibe N Zeilen in eine .mcfunction-Datei
   ↓
4. Laufzeit:
   Event kommt an
   → Sende nur: "function namespace:7168"
   ↓
5. Minecraft Server:
   → Führt alle 500 Befehle in einem Tick aus!
   (1/20 Sekunde = super schnell)
```

---

### Vorteile

| Aspekt | Ohne .mcfunction | Mit .mcfunction |
|--------|---------|---------|
| RCON-Last | 500 Pakete | 1 Paket |
| Geschwindigkeit | 5+ Sekunden | ~1 Tick |
| Queue-Belastung | Hoch | Minimal |
| Datendurchsatz | Riesig | Winzig |

---

### Limitierungen

**1. Nur Vanilla-Commands**

```
✓ /summon, /give, /execute  (OK!)
✗ /mods-custom-command      (Nicht OK!)
```

Plugin-Commands können nicht in Dateien stehen.

**Lösung:** Nutze `!` Prefix statt `/` um RCON direct zu senden.

---

**2. Statische Generierung (beim Start)**

```python
# Beim Programmstart:
for trigger, command in actions.mca:
    write_to_mcfunction(trigger, command)

# Änderungen an actions.mca NICHT Live!
# Du musst neu starten, um Änderungen zu laden!
```

**Wichtig:** `actions.mca` Änderungen werden erst ab nächstem Start aktiv!

---

**3. Server-Performance Warnung**

```
x500 bedeutet: Der Server muss 500 Befehle in 1 Tick ausführen!

✓ x10, x50 = OK
x100+ = Warnung aus dem Programm
✗ x500+ = Wahrscheinlich Server-Crash oder starke lags
```

**Nicht Übertreiben!**

---

### Beispiel

```
# Einfach (RCON direct)
follow:/give @a diamond

# Komplex (wird zu .mcfunction)
7168:/summon minecraft:wither ~ ~ ~ x50
```

Das Programm erstellt:

```
# 7168.mcfunction
/summon minecraft:wither ~ ~ ~
/summon minecraft:wither ~ ~ ~
...
(50x repeat)
```

Beim Event `7168`:
- Sendet NUR: `/function namespace:7168`
- Server führt Datei aus (50 Befehle in einem Tick!)

---

### Zusammenfassung

- **Vanilla Commands(`/`)** mit `xN` → werden in .mcfunction-Dateien ausgelagert
- **Plugin Commands(`!`)** & **Built-in(`$`)** → RCON direct sent
- **.mcfunction-Dateien** werden beim Start generiert, nicht live updatet
- **Performance:** `xN` sollte ≤ 100 sein um Server nicht zu überlasten

→ **Ende!** Jetzt verstehst du: TikTok → Events → Minecraft-Commands!

---

→ [Nächstes Kapitel: System-Architektur](../ch04-00-System-Modules-and-Integration.md)