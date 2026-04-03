## ​RCON und seine Limitierungen

### Was ist RCON?

**RCON = Remote Console** – Ein Protokoll um von außen Commands an Minecraft zu senden.

Es funktioniert über **TCP/Port 25575** (standardmäßig). Der Minecraft-Server muss vorher `enable-rcon=true` in server.properties haben.

---

### Das Problem: Beschränkte Bandbreite

Stell dir RCON wie ein **dünnes Rohr** vor:

```
TikTok-Befehle
        ↓ (viele kommen an)
    RCON-Rohr  ← Begrenzte Kapazität!
        ↓ (muss der Reihe nach raus)
  Minecraft
```

**Das Problem:** Wenn zu viele Commands gleichzeitig ankommen → Überlastung!

**Die Lösung:** **Queues (Warteschlangen)** – Commands der Reihe nach abarbeiten!

---

### Queue-Limits

```python
trigger_queue = Queue(maxsize=10_000)  # Max 10k eingehende Events
rcon_queue = Queue(maxsize=10_000)     # Max 10k Commands an Minecraft
like_queue = Queue()                   # ∞ (unbegrenzt!)
```

**Warum keine Limits bei like_queue?**

Likes sind klein und kommen oft → viele in der Queue ist OK.
Like-Daten sind nur `delta` (Integer), nicht volle Commands!

---

### Dynamisches Throttling

Das System passt die Sendgeschwindigkeit an:

```python
q_size = rcon_queue.qsize()
        wait_time = THROTTLE_TIME
        inner_pause = 0.01 

if q_size > 100:
    wait_time, inner_pause = 0.01, 0.001
elif q_size > 50:
    wait_time, inner_pause = 0.05, 0.005
elif q_size > 20:
    wait_time, inner_pause = 0.1, 0.01
```

**Effekt:**
- Wenn Queue groß: schneller verarbeiten
- Wenn Queue leer: langsamer senden (Ressourcen sparen)

---

### Limitierungen & Edge Cases

| Problem | Folge | Lösung |
|---------|-------|--------|
| Queue voll | Events gehen verloren | `put_nowait()` mit Exception-Handling |
| Verbindung bricht ab | Es kommen keine Commands an | Auto-reconnect |
| Command zu groß | RCON-Error | Command splitten |
| Zu schnell senden | Minecraft-Crash | Throttling anpassen |

---

### Best Practice

```python
# DO: Befehle nacheinander ausführen
while True:
    command = rcon_queue.get()
    minecraft_server.execute(command)
    time.sleep(0.05)  # Kurze Pause für Stabilität

# DON'T: Befehle parallel ausführen (führt zu Instabilität!)
for command in large_command_batch:
    minecraft_server.execute(command)  # ← Zu schnell!
```

> [!NOTE]
> Dieses Beispiel ist stark vereinfacht.
> Im Hauptprogramm sind mehrere hundert Zeilen notwendig,
> um RCON stabil zu betreiben, Fehler sauber abzufangen
> und alle Befehle zuverlässig der Reihe nach abzuarbeiten.

---

### Zusammenfassung

- **RCON** = Netzwerk-Protokoll für Commands
- **Queued** = Um nicht zu überlasten
- **Rate-Limiting** = Dynamisch angepasst

→ [Nächstes Kapitel: mcfunction-Dateien](./ch03-08-The-Use-of-mcfunction-Files.md)