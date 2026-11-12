# Analytics-Tracking — Planung

> **Status:** Planung, festgehalten am 2026-11-12.
>
> **Entscheidung:** Kein Minuten-Zeitverlauf und keine abgeleiteten Kennzahlen
> (Durchschnittswerte, Quoten, Umsatz pro Zuschauer usw.).

---

## 1. Ziel

Mehr Daten aus dem TikTok-Livestream erfassen, ohne bei langen Streams, vielen
Zuschauern oder hohen Event-Raten den Bridge-Prozess zu blockieren oder
unnötig Speicherplatz zu verbrauchen.

Grundprinzip:

- Event-Handler aktualisieren nur In-Memory-Aggregate.
- Ein Hintergrund-Writer schreibt gebündelt in SQLite.
- Details haben eine konfigurierbare Retention.
- Langzeitdaten sind Aggregate, keine Roh-Events.

---

## 2. Aktueller Stand

Bereits vorhanden:

- `data/revenue_log.jsonl`: pro Tag `date` und `estimated_revenue_usd`.
- `data/sessions.jsonl`: pro Stream Start, Ende, Dauer sowie Summen für Gifts,
  Gift-Wert, Likes, Follows, Kommentare, Shares und Joins.
- Keine per-Zuschauer-, per-Gift-, Unique- oder All-Time-Auswertung.

---

## 3. Was genau getrackt wird

### 3.1 Session-Gesamtzahlen

- `gift_events`: Anzahl der Gift-Events
- `gift_units`: Anzahl inklusive Combo-`repeat_count`
- `gift_diamonds`
- `gift_value_usd`
- `unique_gifters`
- `likes_raw`
- `likes_counted`
- `unique_likers`
- `follows`
- `unique_followers`
- `comments`
- `unique_commenters`
- `shares`
- `unique_sharers`
- `joins`
- `unique_joiners`
- `unique_viewers`
- größtes Einzelgeschenk (Name, Wert, Diamanten)
- größte Combo (Name, Einheiten)

### 3.2 Pro Zuschauer

- stabile User-ID, falls verfügbar
- Anzeigename und normalisierter Username
- `gift_events`
- `gift_units`
- `gift_diamonds`
- `gift_value_usd`
- `likes_raw`
- `likes_counted`
- `comments`
- `follows`
- `shares`
- `joins`
- erster und letzter Auftritt in der Session

### 3.3 Pro Gift

- Gift-ID
- Gift-Name
- `events`
- `units`
- `diamonds`
- `value_usd`
- `unique_gifters`
- erster und letzter Auftritt in der Session
- größte Combo dieses Gifts

### 3.4 Top-Listen

- Top-Gifter nach Wert
- Top-Gifter nach Gift-Einheiten
- Top-Gifts nach Einheiten
- Top-Gifts nach Wert
- Top-Liker
- Top-Commenter
- größtes Einzelgeschenk
- größte Combo

Top-Listen werden auch dann gespeichert, wenn die vollständigen
Zuschauer-/Gift-Details deaktiviert sind.

### 3.5 Session-Metadaten

- `session_id`
- Start und Ende
- Dauer
- Reconnect-Anzahl
- Endgrund, falls verfügbar
- TikTok-User und Room-ID, falls verfügbar

### 3.6 All-Time

- Lifetime-Werte pro Zuschauer:
  - Gifts, Einheiten, Diamanten, Wert
  - Likes roh/gezählt
  - Kommentare, Follows, Shares, Joins
  - Anzahl gesehener Sessions
  - erster/letzter Auftritt
- Lifetime-Werte pro Gift:
  - Events, Einheiten, Diamanten, Wert
  - erster/letzter Auftritt
- Tages-Rollups:
  - Sessions
  - Gift-Summen
  - Likes, Follows, Kommentare, Shares, Joins
- All-Time-Leaderboards:
  - Top-Gifter nach Wert/Einheiten
  - Top-Gifts nach Einheiten/Wert
  - Top-Liker
  - Top-Commenter

### 3.7 Zähler-Semantik

- Unbekannte User landen im Bucket `unknown`.
- Likes werden als `likes_raw` und `likes_counted` getrennt geführt.
- Gifts werden als `gift_events` und `gift_units` getrennt geführt.
- Combo-Gifts zählen als Einheiten, nicht als einzelne Events.
- Diamanten und USD werden getrennt gespeichert.
- Gift-Name und Gift-ID werden zum Event-Zeitpunkt festgehalten.

### 3.8 Optional und standardmäßig aus

- Kommentartexte
- Roh-Event-Log
- Trigger-Auslösungen pro Session

---

## 4. Nicht Teil des Plans

- **Kein Minuten-Zeitverlauf** und keine Aktivitäts-Charts.
- **Keine abgeleiteten Kennzahlen**, z. B.:
  - durchschnittlicher Gift-Wert
  - Diamanten pro Gift
  - Gifter-/Liker-/Commenter-/Follower-Quote
  - Umsatz pro Zuschauer
  - Gifts pro Zuschauer

Diese Werte können später ergänzt werden, sind aber ausdrücklich nicht
Bestandteil dieser Umsetzung.

---

## 5. Speicherung

### 5.1 SQLite

Neue Datei: `data/analytics.sqlite3`

`sqlite3` ist in der Standardbibliothek enthalten; es wird keine neue
Abhängigkeit benötigt.

Tabellen:

| Tabelle | Inhalt |
|---|---|
| `sessions` | eine Zeile pro Stream, Gesamtzahlen und Metadaten |
| `session_viewers` | Details pro Session und Zuschauer |
| `session_gifts` | Details pro Session und Gift |
| `session_tops` | Top-Listen pro Session |
| `viewer_lifetime` | All-Time-Werte pro Zuschauer |
| `gift_lifetime` | All-Time-Werte pro Gift |
| `daily_rollup` | Tageswerte |
| `raw_events` | optionales Roh-Event-Log |

Einstellungen:

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- `busy_timeout` für parallele API-Reads
- Indizes auf `session_id`, `started_at`, `user_key`, `gift_id`
- `INSERT ... ON CONFLICT DO UPDATE` für inkrementelle Upserts
- Batch-Transaktionen statt Einzel-Schreibvorgängen

### 5.2 Kompatibilität

- `data/sessions.jsonl` bleibt vorerst als kleiner Summary-Backup-Log bestehen.
- `data/revenue_log.jsonl` bleibt unverändert.
- Alte Session-Summaries werden beim ersten Start einmalig importiert.
- Die API liest primär SQLite und fällt bei Problemen auf JSONL zurück.
- Neue optionale Felder brechen alte Einträge nicht.

---

## 6. Retention

Mehrere Stufen, damit Details nicht unbegrenzt wachsen:

```yaml
analytics:
  retention:
    details_days: 90        # session_viewers, session_gifts, session_tops
    summaries_days: 0       # 0 = unbegrenzt; sessions-Tabelle
    raw_events_days: 7      # nur falls raw_events aktiviert
    aggregates_days: 0      # daily_rollup, viewer_lifetime, gift_lifetime
```

- Details nach 90 Tagen löschen.
- Session-Summaries dauerhaft behalten.
- Lifetime- und Tages-Aggregate dauerhaft behalten.
- Roh-Events standardmäßig aus; wenn aktiviert, nur wenige Tage.
- Cleanup beim Start und danach täglich.
- Löschen in Batches (z. B. 1000 Zeilen), nie alles auf einmal.
- Danach `PRAGMA incremental_vacuum` und WAL-Checkpoint.
- Kein vollständiges `VACUUM` während eines laufenden Streams.

Wenn alle Daten nach einer bestimmten Zeit verschwinden sollen, müssen
`details_days`, `summaries_days` und `aggregates_days` entsprechend gesetzt
werden.

---

## 7. Sehr viele Events gleichzeitig

- Event-Handler machen keine Disk-I/O.
- Ein dedizierter Analytics-Writer-Thread schreibt alle 15–30 Sekunden.
- Es werden nur geänderte Zeilen geschrieben, nicht die komplette Session.
- Schreibvorgänge laufen gebündelt in einer Transaktion.
- Bounded Queue: Bei Überlast wird der Flush verworfen und beim nächsten
  Intervall wiederholt; der TikTok-Event-Loop blockiert nie.
- Bei extrem vielen Unique-Viewern greift `max_tracked_viewers`; darüber wird
  in einen `__other__`-Bucket aggregiert, damit der RAM begrenzt bleibt.
- Top-Listen werden am Session-Ende aus den In-Memory-Aggregaten berechnet und
  in `session_tops` gespeichert.
- Lifetime- und Tages-Aggregate werden am Session-Ende in einer Transaktion
  aktualisiert.
- Bei einem Absturz gehen höchstens die Events seit dem letzten Flush verloren.

---

## 8. Konfiguration

```yaml
analytics:
  enabled: true
  store:
    viewer_details: true
    gift_details: true
    top_lists: true
    lifetime_aggregates: true
    comment_text: false
    raw_events: false
  top_n: 10
  max_tracked_viewers: 50000
  flush_interval_seconds: 30
  retention:
    details_days: 90
    summaries_days: 0
    raw_events_days: 7
    aggregates_days: 0
```

Verhalten:

- `enabled: false` → keine Analytics-DB-Schreibvorgänge; bestehende
  Session-/Revenue-Erfassung bleibt unverändert.
- `viewer_details: false` → keine vollständige Zuschauer-Tabelle; Top-Listen
  bleiben verfügbar.
- `gift_details: false` → keine vollständige Gift-Tabelle; Top-Listen bleiben
  verfügbar.
- `top_lists: false` → keine `session_tops`-Einträge.
- `lifetime_aggregates: false` → keine All-Time-/Tages-Aggregate.
- `comment_text: false` → nur Kommentar-Zähler, keine Texte.
- `raw_events: false` → keine Roh-Event-Tabelle.

---

## 9. API und UI

### API

- `GET /sessions` → Session-Summaries und Pagination
- `GET /sessions/{session_id}` → Details, Top-Listen und Zuschauer/Gifts
- `GET /sessions/report` → Markdown-Bericht mit Top-Listen
- `GET /analytics/leaderboard` → All-Time-Leaderboards

Keine Timeline- und keine Kennzahlen-Endpunkte.

### GUI

- Sessions-Ansicht:
  - Karten für Gesamtzahlen und Unique-Werte
  - Session-Tabelle
  - Detailansicht mit Zuschauer- und Gift-Tabellen
  - Top-Listen
- All-Time-Leaderboards
- Einstellungen für Store-Umfang und Retention
- Revenue-Ansicht: zusätzlich Gift-Anzahl, Diamanten und Unique-Gifter

---

## 10. Umsetzungsreihenfolge

1. SQLite-Schema, Migration und Config-Defaults.
2. `SessionAggregator` + Flush-/Retention-Worker in der Bridge.
3. Service/API: Summary, Detail-Endpoint, Top-Listen, Pagination.
4. GUI: Session-Detail, Top-Listen, All-Time, Einstellungen.
5. Tests: Burst-Simulation, Retention-Cleanup, Config-Toggles, Migration,
   API-Pagination.
6. Benchmark: viele Events in kurzer Zeit und viele Unique-Viewer.

---

## 11. Test- und Abnahmekriterien

- Combo-Gifts zählen korrekt als Einheiten.
- Likes roh und gezählt weichen bei aktivem Rate-Limit korrekt voneinander ab.
- Unbekannte User werden nicht verworfen.
- Top-Listen funktionieren auch ohne vollständige Detail-Speicherung.
- Retention löscht nur die konfigurierten Stufen.
- `enabled: false` erzeugt keine Analytics-Schreibvorgänge.
- Ein voller Writer-Puffer blockiert den Event-Loop nicht.
- Alte `sessions.jsonl`-Einträge bleiben lesbar.
- API liefert bei alten Sessions leere Detailfelder statt Fehlern.
- Ein Burst-Test mit vielen Events bleibt ohne Speicher- oder CPU-Ausreißer.
