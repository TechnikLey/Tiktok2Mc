# P3a — Update-Architektur: Ein Runtime-Layout, zwei Hüllen

> **Status:** Verbindliche Planung (Entscheidung vom 2026-10-30). Vor Umsetzung: P0 (Baseline-Tests)
> muss abgeschlossen sein, da diese Änderung `paths.py` und das Release-Layout berührt.
>
> **Nachrichtliche Einordnung:** Teil des Roadmaps aus der Architektur-Erklärung 2026-10-30.
> Ersetzt die bisherige In-Place-Update-Choreografie (Kill-Signal, Whitelist-Kopie, `execv`-Resume).

---

## 1. Ziel & Prinzipien

**Ziel:** Der Updater überschreibt **niemals** Dateien einer laufenden App (Omaha/Squirrel-Muster,
wie Chrome, Squirrel.Windows, Firefox-portable). Updates werden parallel in ein neues
`app-<ver>`-Verzeichnis installiert; ein Pointer entscheidet beim nächsten Start über die aktive
Version.

**Prinzipien (nicht verhandelbar):**

1. **Kein Kontakt mit laufenden Prozessen.** Der Updater killt/wartet auf nichts.
2. **Ein Runtime-Layout für alle Kanäle** (Windows-NSIS, Windows-Portable, Linux-Portable).
   Die Installations-*Hülle* unterscheidet sich, das Layout *drin* nicht.
3. **User-Daten haben ein definiertes Home**, das vom App-Code getrennt ist.
4. **Rollback durch Design:** die alte Versions-Verzeichnis bleibt intakt.
5. **Integrity ist Pflicht:** sha256 je Datei + Ed25519-Signatur über das Manifest.

**Nicht Teil von P3a (Stufe 2, später):** OV/EV-Code-Signing-Zertifikat der EXEs (Certum /
Microsoft Artifact Signing), winget-Bucket, Staged-Rollout-Kanäle, MSIX.

---

## 2. Ziel-Layout (Release)

```text
<install-root>/                      ← egal, wie es dorthin kam (NSIS, Zip-Entpacken)
├── start{.exe|.bin}                 ← LAUNCHER (stabil, wird praktisch nie ersetzt)
├── update{.exe|.bin}                ← DOWNLOADER (ersetzt sich ggf. selbst, siehe §8)
├── current.json                     ← POINTER (atomisch geschrieben, siehe §4)
├── manifest.json + manifest.json.sig ← Release-Manifest + Signature (siehe §5)
├── app-1.1.0/                       ← Versions-Verzeichnis (immutable!) *
│   ├── core/  plugins/  server-tool/*  gui{.exe|.bin} ...
│   └── version.txt
├── app-1.2.0/                       ← neue Version, parallel installierbar
├── config/                          ← USER-DATEN (Home, außerhalb der Versions-Dirs)
├── data/                            ← USER-DATEN (inkl. plugin_data/, backups/)
├── server/                          ← USER-DATEN (MC-Server-Instanzen)
├── versions/                        ← USER-DATEN (Template-Repo)
└── core/runtime/                    ← IPC/Status-Artefakte (nicht config!)

* „immutable": Der Updater löscht/verändert ein Versions-Verzeichnis nur in diesen
  Ausnahmen: (a) die aktuell laufende Version wird NIEMALS angetastet, (b) Löschen nur
  beim Prune *alter, nicht-aktiver* Versionen.
```

**Dev-Layout bleibt unangetastet:** `src/core/paths.py`-Dev-Zweig (Marker
`src/core/paths.py`) funktioniert weiter — P3a betrifft nur den Release-Zweig.

---

## 3. Data-Home-Auflösung (die zentrale Änderung in `paths.py`)

Neue Funktion `get_data_home()` mit definierter Suchreihenfolge:

| Priorität | Ort | Sinn |
|---|---|---|
| 1 | `<install-root>/{config,data,server,versions} existieren` | **Portable- und NSIS-Layout (neu identisch):** Daten liegen neben den `app-*`-Dirs |
| 2 | `%LOCALAPPDATA%/Tiktok2Mc/{config,...}` (Windows) bzw. `~/.local/share/Tiktok2Mc/` (Linux) | **NSIS-Fallback**, falls User das NSIS-Layout wählt — UND Ziel für zukünftige Store/MSIX-Varianten |
| 3 | Fallback Richtung Installations-Root | Legacy-Installationen vor Migration (§8) |

Konsequenz für `paths.py`:

- Alle Funktionen `get_config_file()`, `get_runtime_dir()`, `get_plugin_data_dir()`,
  `get_servers_dir()`, `get_versions_dir()` wechseln von `get_root_dir()` auf
  `get_data_home_base()`.
- **App-Pfade** (`get_base_file()`, `get_plugins_dir()` Release-Zweig) wechseln
  von Root auf `get_active_app_dir()` (aus dem Pointer, siehe §4).
- Prozeduraler Schutz: Die Data-Home-Erkennung darf nie vom aktiven App-Dir abhängen
  und umgekehrt (das App-Dir liegt immer unter dem Root; das Data-Home kann überall liegen).

Aufwand-Begründung: Es sind ~10 Funktionen an einer Datei — deshalb ist P3a klein,
obwohl die Wirkung groß ist.

---

## 4. `current.json` — Pointer-Spec

```json
{
  "active_app_dir": "app-1.2.0",
  "tool_version": "1.2.0",
  "installed_at_utc": "2026-10-30T14:03:11Z",
  "manifest_sha256": "<hex of manifest.json at install time>",
  "previous_app_dir": "app-1.1.0"
}
```

Regeln:

- **Atomischer Schreibpfad:** `current.json.tmp` → `os.replace()` → fertig. Kein Teil-Schreiben, kein Rumpf-Zustand.
- **Leser-Fallback:** Wenn `current.json` fehlt/korrupt ist: alle bekannten `app-*`-Verzeichnisse in SemVer-Sortierung, neueste gewinnt, Warnung loggen. Der Launcher crasht dadurch NIE wegen Pointer.
- **Schreiber: nur `update.exe`** (sowohl install als auch rollback). Der Launcher schreibt nie am Pointer.
- `previous_app_dir` macht Rollback **einstufig**: GUI-Button „Letzte Version wiederherstellen" → Updater läuft als `--rollback`-Modus.

---

## 5. `manifest.json` + Signatur

```json
{
  "tool_version": "1.2.0",
  "updater_version": "0.3.0",
  "config_version_expected": "1.1",
  "min_start_version": "1.0.0",
  "channel": "stable",
  "created_utc": "...",
  "files": [
    { "path": "app-1.2.0/core/main.exe", "sha256": "<hex>", "size": 4821139 },
    ...
  ]
}
```

- Der Datei-Index wird aus dem Release-Build erzeugt: `build.py` generiert ihn (er
  ersetzt die hartkodierten `WHITELIST_DIRS/FILES` in `update.py` → **das Duplikat stirbt**).
- `manifest.json.sig` = Ed25519-**Detached-Signatur** über die exakten Bytes der Datei
  (keine JSON-Kanonisierung nötig). Signiert in CI; privater Key in **CI-Secret**
  (`enc_pk`); der öffentliche Key ist statisch in `update.exe`/Launcher-Code eingebettet.
- Library: `cryptography` (bereits in `requirements.txt`, 50.0.0) — `Ed25519PrivateKey`.
- **Im Updater:** erst Signatur prüfen, dann Datei-Checksums; ein FAIL genügt → Exit-Code
  `EXIT_SIGNATURE_MISMATCH` (neuer Code in `core.update_exit`).

---

## 6. Neuer `update.exe`-Ablauf (lineare Zustandsmaschine)

| # | Schritt | Beschreibung | Fail → |
|---|---|---|---|
| 1 | `CHECK` | GitHub-Release (Retry × 3 via `core.update_exit`-Konvention), Beta-Kanal-Skip in Auto-Mode | `EXIT_API_ERROR` |
| 2 | `FETCH` | Download in `core/runtime/update-tmp/` (Progress an GUI-Splash wie bisher) | `EXIT_DOWNLOAD_FAILED` |
| 3 | `VERIFY_SIG` | `manifest.json.sig` mit eingebettetem Public-Key über `manifest.json` | `EXIT_SIGNATURE_MISMATCH` |
| 4 | `VERIFY_SHA` | jede manifest-Datei gegen volle sha256 | `EXIT_CHECKSUM_MISMATCH` |
| 5 | `STAGE` | nach `<inst-root>/app-<ver>/` extrahieren (Reihenfolge: erst vollständig in Temp-Dir, dann `os.replace`-Move) | `EXIT_EXTRACT_FAILED` |
| 6 | `FLIP` | `current.json` atomisch umschreiben | `EXIT_POINTER_FAILED` |
| 7 | `PRUNE` | alle Versionen außer aktuelle + `previous_app_dir` löschen (keep 2) | nur geloggt |
| 8 | `NOTIFY` | Status-Phase in `core/runtime/update_state.json` (Mechanismus existiert — Single-Source-of-Truth für GUI-Splash **und** GUI-Banner) | — |

**Wichtig:** Kein Schritt interagiert mit laufenden Apps. Der User sieht in der GUI:
> „Update 1.2.0 bereit — aktiv bei nächstem Start."
> Der GUI-Banner [Jetzt neu starten] ruft normalen Restart (Supervisor übernimmt).

**Was hierdurch physikalisch verschwindet (Widerspruchs-Beilage):**

- Kein `update_signal.tmp` im Root mehr (bzw. umzug nach `core/runtime/` — nur noch
  als unidirektionales Signal „Supervisor kann herunterfahren", nicht als Kill-Choreografie).
- Keine zwei Kill-Kanäle mehr (API + Datei + 30-s-Poll-Loop).
- Kein `execv`/`--resume`-Resume-Kette für den Updater-Self-Update
  (Updater-Self-Update: `update{.exe|.bin}` landet als `update_new{.exe|.bin}` daneben und wird
  einfach beim *nächsten* Start von `start.exe` übernommen — siehe §8; der Tausch erfolgt via
  `os.replace`, nicht via `execv`).
- Keine `WHITELIST_DIRS/FILES`-Doppeltheit (**das Manifest ist die einzige Quelle**).

---

## 7. Launcher `start.exe`

Neuer Ablauf:

1. `get_active_app_dir()` aus Pointer lesen (mit Fallback §4).
2. Alle Kinder/App-Exes aus der **aktiv Version** starten (heutige `start.py`-Logik bleibt,
   nur die Pfade ändern sich).
3. **First-Start-nach-Update-Hook:** wenn `current.json.tool_version` ≠ registrierte
   zuletzt gesehene Version (in `core/runtime/last_run_version.txt`):
   - `auto_update_config`-Merge (existiert, bereits bewährt) + `EXPECTED_CONFIG_VERSION`-Bump.
   - Einmalige Layout-Konsolidierung (§8), falls Migration noch nicht abgeschlossen.
4. Abwärtskompatibel: Wenn kein `app-*`-Verzeichnis existiert (frisch entpacktes Portable-Zip ohne Update) → aktuelles Verhalten
   (alles im Root = Legacy-Kompatibilität, siehe §8).

---

## 8. Migration bestehender Installationen (einmalig, idempotent, abgesichert)

Trigger: `start.exe` erkennt Legacy-Layout (Binaries + `config/` im selben Ordner) OHNE `current.json`.

Ablauf (vom Launcher oder vom Updater — identischer Code in `core/update_engine/migration.py`):

1. `core/runtime/migration_state.json` init (append-only-Log mit Step-Nummern).
2. `app-<ver>/` erzeugen (SemVer aus `version.txt`).
3. Programmdateien (analog zum heutigen WHITELIST-Inhalt — für die Migration einmalig aus der
    alten Hart-Kodierung generiert, danach findet sich diese Information nur noch im Manifest)
    *verschieben* → `app-<ver>/`.
4. User-Datenverzeichnisse (`config/`, `data/`, `server/`, `versions/`, `core/runtime/`)
  `BLEIBEN` am Root (das neue Data-Home = Root ist bereits Priority-1 → KEIN Verschieben nötig!).
5. `current.json` schreiben.
6. Alte Root-Binaries (die nicht ins `app-<ver>` kamen, doppelt/falsch platziert) entfernen.

**Abbruchfestigkeit:** Jeder Schritt bestätigt sich im Log — bei Crash setzt der nächste
Start am letzten Log-Step fort. Zustand in `migration_state.json`: `phase: done | running | resume_at_N`.

→ **Der Punkt, der P3a von „Standard-Rewrite" hebt:** Bestehende Installationen brauchen
nur Verschieben der *Programm*-Dateien in `app-<ver>/`; User-Daten bleibt. Risiko:
minimal.

---

## 9. `build.py`-Änderungen

1. Release-Assembly: `app-<ver>/`-Layout (siehe §2) anstelle heutigem Flat-Layout.
2. **Portable Zip** = genau dieses Layout inkl. `start{.exe|.bin}`, `update{.exe|.bin}`, `current.json` im Root.
3. **NSIS** = Install-Skript entpackt dasselbe Zip unter `%LOCALAPPDATA%\Tiktok2Mc\`
   (+ Startmenü-/Desktop-Shortcut, + Uninstaller, der `app-*`-Verzeichnisse löscht und
   User-Daten zur Abfrage belässt).
4. `manifest.json` + `.sig` erzeugen (CI-Secret `T2M_SIGNING_PRIVATE_KEY`).
5. `.sha256` pro Release-Archiv bleibt (infra-Kompatibilität).

---

## 10. Test-Plan

**pytest** (`tests/test_core/test_update_engine.py`, `test_pointer.py`, `test_migration.py`):

- Pointer: atomischer Write, corrupt-read fallback, rollback.
- Manifest-Verifikation: sig ok/fail, sha ok/fail, fehlender sig.
- Data-Home-Resolution für alle 3 Prioritäten.
- Migration: legacy→pointer, resume nach sim. Crash, idempotence (2-mal ausführen).

**E2E-Harness** (`tools/update_test/`, Szenarien ersetzen die alten Kill-Choreo-Tests):

1. `success` (bestehend), 2. `sig_fail`, 3. `sha_fail`, 4. `extract_fail`,
5. `pointer_crash_resume` (FLIP-Abbruch simuliert), 6. `prune`,
7. `legacy_migration`, 8. **`parity_installer_portable`** (beide Hüllen → identisches Layout).

---

## 11. Aufwand

| Baustein | Aufwand |
|---|---|
| `paths.py`: Data-Home + Active-App + Fallbacks (+ Tests) | 1,5 d |
| `update_engine`: Pointer + Manifest + Signatur + Steps (§4–6) | 3–4 d |
| Launcher First-Start-Hook + Migration (§7–8) | 2 d |
| `build.py`: Layout + Manifest + beide Hüllen (§9) | 2 d |
| E2E-Harness Szenarien (§10) | 2–3 d |
| Doku-Sync (AGENTS.md §2), CHANGELOG, `docs/dev-book-*` (beide!) | 1 d |
| **Summe** | **≈ 11–13 Arbeitstage** |

*(Vorherige P3-Schätzung „in-place-Rollback + Zustandsmaschine" wäre ähnlich teuer gewesen
und hätte die Kill-Choreografie behalten — dieser Plan verschiebt Budget vom Rückbau-Risiko
in die Layout-Wartbarkeit.)*

---

## 12. Abhängigkeiten & Reihenfolge im Roadmap

```
P0 Baseline-Tests  →  P1 Single-Source-of-Truth  →  **P3a (dieses Dokument)**
                                                          ↓
                              P2 Stabilität (EventBus, Restart-Policy …) — parallel möglich
                                                          ↓
                              P4 Doku-Implementierung
```

P3a berührt `paths.py` → muss nach P1-Config-Home-Definition (= beide sind die gleiche
Wurzelarbeit) kommen. Danach ist der Updater-Freeze aufgehoben und die historisch größte Commit-Kategorie
(≈19 % „update"-Commits) schaltet von Fix-Reparatur auf stabile Pflege um.
