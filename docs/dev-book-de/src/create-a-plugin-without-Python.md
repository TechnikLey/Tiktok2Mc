# Plugin erstellen ohne Python

> [!WARNING]
> **Keine Garantie für die Codebeispiele.**  
> Die Code-Beispiele in diesem Kapitel (Rust, C++) wurden von einer KI generiert.
> Ich habe selbst wenig Kenntnisse in diesen Sprachen und kann nicht garantieren, dass sie korrekt, vollständig oder fehlerfrei sind.
> Nutze sie als Ausgangspunkt und prüfe sie sorgfältig, bevor du sie produktiv einsetzt.

## Überblick

Du kannst ein Plugin in jeder Sprache schreiben, die eine native Windows-`.exe` erzeugt. Das System startet ausschließlich die Datei `main.exe` in deinem Plugin-Ordner – wie diese erzeugt wird (MSVC-Compiler, Rust/Cargo, MinGW, etc.) ist irrelevant.

> [!IMPORTANT]
> **`main.exe` ist die einzige Pflichtdatei** des Plugin-Systems.  
> Python-Plugins funktionieren übrigens genauso: `main.py` wird über PyInstaller zu `main.exe` kompiliert. Aus Sicht des Systems gibt es keinen Unterschied.

**Was du selbst implementieren musst** (Python erledigt das per `core`-Modul automatisch):
- Registrierungsprotokoll (`--register-only`)
- Argument-Parsing (`--gui-hidden`)
- HTTP-Server für `/webhook`
- Konfiguration lesen (YAML / JSON)
- Datenspeicherung

---

## Ordnerstruktur

```
src/plugins/
└── myplugin/
    ├── main.exe        ← vom System gestartet (kompiliert aus deinem Code)
    ├── README.md
    └── version.txt
```

Beim Build wird der gesamte `src/plugins/myplugin/`-Ordner nach `build/release/plugins/myplugin/` kopiert.

---

## Wie der Registry-Scanner funktioniert

Bevor das Hauptprogramm Plugins startet, läuft `registry.exe`. Sie sucht **alle** `main.exe`-Dateien im `plugins/`-Ordner und führt jede mit `--register-only` aus:

```
registry.exe
  ├── findet: plugins/myplugin/main.exe
  ├── ruft auf: main.exe --register-only   (cwd = plugins/myplugin/)
  ├── liest stdout, parst erstes gültiges JSON-Objekt
  └── speichert Metadaten in PLUGIN_REGISTRY.json
```

Danach liest `start.py` die `PLUGIN_REGISTRY.json` und startet jede aktivierte `main.exe` (diesmal **ohne** `--register-only`).

> [!NOTE]
> Der Scanner cached Registrierungsergebnisse anhand von Dateigröße und Änderungszeit.
> Wenn du die `main.exe` neu kompilierst, wird sie beim nächsten Start automatisch neu gescannt.

---

## Das Registrierungsprotokoll

### Pflichtformat

Wenn dein Plugin mit `--register-only` gestartet wird, muss es auf **stdout** eine Zeile im folgenden Format ausgeben und dann mit Exit-Code `0` beenden:

```
REGISTER_PLUGIN: {"name":"MeinPlugin","path":"C:\\absoluter\\pfad\\zu\\main.exe","enable":true,"level":4,"ics":false}
```

Das Präfix `REGISTER_PLUGIN:` ist empfohlen (genau wie es Python ausgibt), aber der Scanner akzeptiert auch eine Zeile, die direkt als JSON-Objekt parsebar ist.

### Pflichtfelder

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `name` | `string` | Eindeutiger Name des Plugins |
| `path` | `string` | **Absoluter** Pfad zur `main.exe` |
| `enable` | `bool` | Ob das Plugin beim Start gestartet wird |
| `level` | `int` | Sichtbarkeitslevel (siehe unten) |
| `ics` | `bool` | Hat das Plugin ein GUI-Fenster? |

### Sichtbarkeitslevel (`level`)

Steuert, ob das Konsolenfenster des Plugins angezeigt wird, abhängig vom `log_level` in der `config.yaml`:

| Level | Bedeutung |
|-------|-----------|
| 0 | Verboten – überschreibt alle Sichtbarkeitsregeln, nie verwenden! |
| 1 | Für sehr sehr wichtige Ausgaben |
| 2 | Hauptprogramme |
| 3 | Hintergrunddienste |
| 4 | Debug/Entwicklung ← für eigene Plugins empfohlen |
| 5 | Verboten – überschreibt alle Sichtbarkeitsregeln, nie verwenden! |

> [!NOTE]
> **Level 0 und 5 dürfen nicht verwendet werden.**
> Wenn in der `config.yaml` `log_level = 0` oder `log_level = 5` gesetzt ist, überschreiben diese Werte sämtliche Sichtbarkeitsregeln für alle Programme und Plugins.
> Kein Plugin oder Programm darf Level 0 oder 5 als Wert setzen.

### ICS vs. DCS

- `ics: false` → Plugin ohne GUI (nur HTTP-Server im Hintergrund). Das ist der Standardfall.
- `ics: true` → Plugin öffnet ein Fenster. Wenn `control_method` in der `config.yaml` auf `DCS` steht, wird dein Plugin mit `--gui-hidden` gestartet (kein Fenster öffnen).

### Der `path`-Wert

Der `path`-Wert muss der **absolute Pfad** zur `main.exe` sein. Da der Scanner dein Plugin mit dem vollen absoluten Pfad aufruft, kannst du `argv[0]` nutzen:

- **Rust:** `std::env::current_exe()` – die zuverlässigste Methode
- **C++:** Win32-API `GetModuleFileNameA(NULL, buf, MAX_PATH)` oder `std::filesystem::absolute(argv[0])`

---

## Argument-Handling

Dein Plugin muss mindestens zwei Argumente kennen:

| Argument | Verhalten |
|----------|-----------|
| `--register-only` | JSON ausgeben, sofort beenden |
| `--gui-hidden` | Fenster **nicht** öffnen (nur relevant wenn `ics: true`) |

---

## Den Webhook-Server implementieren

Das Minecraft-Plugin sendet bei Ereignissen HTTP-POST-Requests an alle konfigurierten URLs. Dein Plugin kann einen HTTP-Server starten und den Endpunkt `/webhook` bereitstellen.

### Event-Payload

```json
{
    "load_type": "INGAME_GAMEPLAY",
    "event": "player_death",
    "message": "Player died from fall damage"
}
```

`load_type` kann u.a. `INGAME_GAMEPLAY` oder `STARTUP` sein. `event` entspricht dem Ereignisnamen aus der `configServerAPI.yml`.

### Häufige Events

| Event | Standardmäßig aktiv |
|-------|---------------------|
| `player_death` | ✓ |
| `player_respawn` | ✓ |
| `player_join` | – |
| `player_quit` | – |
| `block_break` | – |
| `entity_death` | – |

Die vollständige Liste findest du in `configServerAPI.yml`.

### Port konfigurieren

Lege in der `config.yaml` einen Port für dein Plugin an:

```yaml
MeinPlugin:
  Enable: true
  WebServerPort: 8888
```

Füge die Webhook-URL dann in `configServerAPI.yml` (Minecraft-Plugin-Config) ein:

```yaml
webhooks:
  urls:
    - "http://localhost:7777/webhook"
    - "http://localhost:7878/webhook"
    - "http://localhost:7979/webhook"
    - "http://localhost:8080/webhook"
    - "http://localhost:8888/webhook"   # dein Plugin
```

> [!IMPORTANT]
> Jede Portnummer im System muss **eindeutig** sein. Nutze niemals einen bereits belegten Port.

---

## Pfade zur Laufzeit

Wenn `main.exe` läuft, lassen sich alle wichtigen Verzeichnisse aus dem eigenen Pfad ableiten:

```
build/release/
├── config/
│   └── config.yaml       ← Konfiguration
├── data/                 ← persistente Daten
├── logs/                 ← Log-Dateien
└── plugins/
    └── myplugin/
        └── main.exe      ← dein Plugin
```

| Variable | Berechnung | Beispiel |
|----------|-----------|---------|
| `BASE_DIR` | Verzeichnis von `main.exe` | `…/plugins/myplugin/` |
| `ROOT_DIR` | `BASE_DIR/../..` | `…/build/release/` |
| `CONFIG_FILE` | `ROOT_DIR/config/config.yaml` | |
| `DATA_DIR` | `ROOT_DIR/data/` | |
| `LOGS_DIR` | `ROOT_DIR/logs/` | |

**Rust:**
```rust
let exe_path = std::env::current_exe().unwrap();
let base_dir = exe_path.parent().unwrap();        // plugins/myplugin/
let root_dir = base_dir.parent().unwrap()
                        .parent().unwrap();        // build/release/
let config_file = root_dir.join("config").join("config.yaml");
let data_dir    = root_dir.join("data");
let logs_dir    = root_dir.join("logs");
```

**C++:**
```cpp
#include <filesystem>
namespace fs = std::filesystem;

char buf[MAX_PATH];
GetModuleFileNameA(NULL, buf, MAX_PATH);
fs::path base_dir   = fs::path(buf).parent_path();       // plugins/myplugin/
fs::path root_dir   = base_dir.parent_path().parent_path(); // build/release/
fs::path config_file = root_dir / "config" / "config.yaml";
fs::path data_dir    = root_dir / "data";
fs::path logs_dir    = root_dir / "logs";
```

---

## Konfiguration lesen

Die `config.yaml` ist eine YAML-Datei. Lies sie beim Start deines Plugins:

**Rust** (mit [`serde_yaml`](https://crates.io/crates/serde_yaml)):
```rust
let content = std::fs::read_to_string(&config_file).unwrap_or_default();
let cfg: serde_yaml::Value = serde_yaml::from_str(&content).unwrap_or(serde_yaml::Value::Null);
let port = cfg["MeinPlugin"]["WebServerPort"].as_u64().unwrap_or(8888) as u16;
let enabled = cfg["MeinPlugin"]["Enable"].as_bool().unwrap_or(true);
```

**C++** (mit [`yaml-cpp`](https://github.com/jbeder/yaml-cpp)):
```cpp
YAML::Node cfg = YAML::LoadFile(config_file.string());
int port    = cfg["MeinPlugin"]["WebServerPort"].as<int>(8888);
bool enabled = cfg["MeinPlugin"]["Enable"].as<bool>(true);
```

Wenn die Datei fehlt oder ein Schlüssel nicht vorhanden ist, verwende immer einen **Default-Wert** – das Plugin soll nie wegen einer fehlenden Config-Zeile abstürzen.

---

## Datenspeicherung

Persistente Daten (Zähler, Zustände, Fenstergröße) speicherst du als JSON-Datei im `DATA_DIR`:

```
build/release/data/myplugin_state.json
```

Schreibe atomar (erst in `.tmp`, dann umbenennen), um Datenverlust bei unerwartetem Beenden zu vermeiden.

---

## Kommunikation mit anderen Plugins

Plugins kommunizieren per HTTP auf `localhost`. Die Ports stehen in `config.yaml`:

```yaml
WinCounter:
  WebServerPort: 8080
```

**Rust** (mit [`ureq`](https://crates.io/crates/ureq)):
```rust
// Fire-and-forget (kein Warten auf Antwort)
std::thread::spawn(|| {
    let _ = ureq::post("http://localhost:8080/add?amount=1").call();
});
```

**C++** (mit [cpp-httplib](https://github.com/yhirose/cpp-httplib)):
```cpp
httplib::Client cli("localhost", 8080);
cli.set_connection_timeout(2);
auto res = cli.Post("/add?amount=1");
if (!res || res->status != 200) {
    // Plugin nicht erreichbar – Fehler loggen, nicht abstürzen
}
```

> [!NOTE]
> Das andere Plugin kann offline oder noch nicht gestartet sein.
> **Immer Timeout setzen und Fehler abfangen.**

---

## Vollständiges Beispiel – Rust

Demonstriert alle Pflichtbestandteile: Registrierung, Webhook-Server, Config-Lesen, Datenspeicherung.

Abhängigkeiten (`Cargo.toml`):
```toml
[dependencies]
tiny_http   = "0.12"
serde       = { version = "1", features = ["derive"] }
serde_json  = "1"
serde_yaml  = "0.9"
```

`src/main.rs`:
```rust
use std::env;
use std::fs;
use std::io::Read;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tiny_http::{Response, Server};

// ---------------------------------------------------------------------------
// Pfade
// ---------------------------------------------------------------------------
fn exe_path() -> PathBuf {
    env::current_exe().expect("Kann Exe-Pfad nicht bestimmen")
}

fn base_dir() -> PathBuf {
    exe_path().parent().unwrap().to_path_buf()
}

fn root_dir() -> PathBuf {
    base_dir().parent().unwrap().parent().unwrap().to_path_buf()
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
#[derive(serde::Serialize, serde::Deserialize, Default)]
struct State {
    count: u64,
}

fn load_state(path: &PathBuf) -> State {
    if path.exists() {
        let s = fs::read_to_string(path).unwrap_or_default();
        serde_json::from_str(&s).unwrap_or_default()
    } else {
        State::default()
    }
}

fn save_state(path: &PathBuf, state: &State) {
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, serde_json::to_string_pretty(state).unwrap()).ok();
    fs::rename(&tmp, path).ok();
}

// ---------------------------------------------------------------------------
// Hauptprogramm
// ---------------------------------------------------------------------------
fn main() {
    let args: Vec<String> = env::args().collect();

    // --- Registrierung ---
    if args.iter().any(|a| a == "--register-only") {
        // Absoluten Pfad zur eigenen main.exe bestimmen
        let exe = exe_path().to_string_lossy().replace('\\', "\\\\");

        // Config lesen um enable-Flag dynamisch zu setzen
        let root = root_dir();
        let config_file = root.join("config").join("config.yaml");
        let content = fs::read_to_string(&config_file).unwrap_or_default();
        let cfg: serde_yaml::Value =
            serde_yaml::from_str(&content).unwrap_or(serde_yaml::Value::Null);
        let enabled = cfg["MeinPlugin"]["Enable"].as_bool().unwrap_or(true);

        println!(
            r#"REGISTER_PLUGIN: {{"name":"MeinPlugin","path":"{exe}","enable":{enabled},"level":4,"ics":false}}"#
        );
        std::process::exit(0);
    }

    let gui_hidden = args.iter().any(|a| a == "--gui-hidden");
    // gui_hidden wird hier nicht benötigt, da ics=false (kein Fenster)
    let _ = gui_hidden;

    // --- Konfiguration laden ---
    let root = root_dir();
    let config_file = root.join("config").join("config.yaml");
    let content = fs::read_to_string(&config_file).unwrap_or_default();
    let cfg: serde_yaml::Value =
        serde_yaml::from_str(&content).unwrap_or(serde_yaml::Value::Null);

    let port: u16 = cfg["MeinPlugin"]["WebServerPort"]
        .as_u64()
        .unwrap_or(8888) as u16;

    // --- State laden ---
    let data_dir = root.join("data");
    fs::create_dir_all(&data_dir).ok();
    let state_file = data_dir.join("meinplugin_state.json");
    let state = Arc::new(Mutex::new(load_state(&state_file)));

    // --- HTTP-Server starten ---
    let server = Server::http(format!("127.0.0.1:{port}"))
        .expect("HTTP-Server konnte nicht gestartet werden");

    println!("[MeinPlugin] läuft auf Port {port}");

    for mut request in server.incoming_requests() {
        let url = request.url().to_string();
        let method = request.method().as_str().to_string();

        if url == "/webhook" && method == "POST" {
            let mut body = String::new();
            request.as_reader().read_to_string(&mut body).ok();

            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&body) {
                let event = json["event"].as_str().unwrap_or("");

                if event == "player_death" {
                    let mut s = state.lock().unwrap();
                    s.count += 1;
                    println!("[MeinPlugin] Tode: {}", s.count);
                    save_state(&state_file, &s);
                }
            }

            let response = Response::from_string(r#"{"status":"ok"}"#)
                .with_header("Content-Type: application/json".parse().unwrap());
            request.respond(response).ok();

        } else if url == "/" && method == "GET" {
            let s = state.lock().unwrap();
            let body = format!(r#"{{"count":{}}}"#, s.count);
            let response = Response::from_string(body)
                .with_header("Content-Type: application/json".parse().unwrap());
            request.respond(response).ok();

        } else {
            request.respond(Response::from_string("Not Found").with_status_code(404)).ok();
        }
    }
}
```

---

## Vollständiges Beispiel – C++

Verwendet [cpp-httplib](https://github.com/yhirose/cpp-httplib) (single-header) und [nlohmann/json](https://github.com/nlohmann/json) (single-header).

```cpp
// Kompilierung (MSVC):
//   cl /std:c++17 /EHsc main.cpp /Fe:main.exe
// Kompilierung (MinGW):
//   g++ -std=c++17 -O2 main.cpp -o main.exe -lws2_32

#define CPPHTTPLIB_OPENSSL_SUPPORT 0
#include "httplib.h"       // https://github.com/yhirose/cpp-httplib
#include "json.hpp"        // https://github.com/nlohmann/json

#include <windows.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <string>

namespace fs = std::filesystem;
using json   = nlohmann::json;

// ---------------------------------------------------------------------------
// Pfade
// ---------------------------------------------------------------------------
fs::path get_exe_path() {
    char buf[MAX_PATH];
    GetModuleFileNameA(NULL, buf, MAX_PATH);
    return fs::path(buf);
}

fs::path base_dir() { return get_exe_path().parent_path(); }
fs::path root_dir() { return base_dir().parent_path().parent_path(); }

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
struct State { uint64_t count = 0; };
std::mutex state_mutex;
State g_state;

void save_state(const fs::path& path) {
    fs::path tmp = path;
    tmp.replace_extension(".tmp");
    std::ofstream f(tmp);
    f << json{{"count", g_state.count}}.dump(2);
    f.close();
    fs::rename(tmp, path);
}

void load_state(const fs::path& path) {
    if (!fs::exists(path)) return;
    std::ifstream f(path);
    try {
        json j; f >> j;
        g_state.count = j.value("count", 0ULL);
    } catch (...) {}
}

// ---------------------------------------------------------------------------
// Config lesen (vereinfacht – keine yaml-cpp-Abhängigkeit benötigt)
// Für YAML empfiehlt sich yaml-cpp: https://github.com/jbeder/yaml-cpp
// Hier wird der Port aus der config.yaml per einfachem Scan extrahiert.
// ---------------------------------------------------------------------------
uint16_t read_port(const fs::path& config_file, uint16_t default_port) {
    if (!fs::exists(config_file)) return default_port;
    std::ifstream f(config_file);
    std::string line, section;
    bool in_section = false;
    while (std::getline(f, line)) {
        if (!line.empty() && line[0] != ' ' && line[0] != '#') {
            in_section = (line.find("MeinPlugin:") != std::string::npos);
        }
        if (in_section) {
            auto pos = line.find("WebServerPort:");
            if (pos != std::string::npos) {
                try { return static_cast<uint16_t>(std::stoi(line.substr(pos + 14))); }
                catch (...) {}
            }
        }
    }
    return default_port;
}

// ---------------------------------------------------------------------------
// Hauptprogramm
// ---------------------------------------------------------------------------
int main(int argc, char* argv[]) {
    // --- Registrierung ---
    for (int i = 1; i < argc; ++i) {
        if (std::string(argv[i]) == "--register-only") {
            std::string exe = get_exe_path().string();
            // Backslashes für JSON escapen
            std::string escaped;
            for (char c : exe) {
                if (c == '\\') escaped += "\\\\";
                else escaped += c;
            }

            // enable-Flag aus Config lesen (vereinfacht: immer true)
            std::cout << "REGISTER_PLUGIN: "
                      << "{\"name\":\"MeinPlugin\","
                      << "\"path\":\"" << escaped << "\","
                      << "\"enable\":true,"
                      << "\"level\":4,"
                      << "\"ics\":false}"
                      << std::endl;
            return 0;
        }
    }

    bool gui_hidden = false;
    for (int i = 1; i < argc; ++i)
        if (std::string(argv[i]) == "--gui-hidden") gui_hidden = true;
    (void)gui_hidden; // ics=false, daher nicht relevant

    // --- Pfade & Konfiguration ---
    fs::path root       = root_dir();
    fs::path config_file = root / "config" / "config.yaml";
    fs::path data_dir   = root / "data";
    fs::create_directories(data_dir);
    fs::path state_file = data_dir / "meinplugin_state.json";

    uint16_t port = read_port(config_file, 8888);

    // --- State laden ---
    load_state(state_file);

    // --- HTTP-Server ---
    httplib::Server svr;
    svr.set_error_handler([](const auto&, auto& res) {
        res.set_content(R"({"status":"error"})", "application/json");
        res.status = 500;
    });

    // GET / – Status abfragen
    svr.Get("/", [&](const httplib::Request&, httplib::Response& res) {
        std::lock_guard<std::mutex> lock(state_mutex);
        res.set_content("{\"count\":" + std::to_string(g_state.count) + "}", "application/json");
    });

    // POST /webhook – Events empfangen
    svr.Post("/webhook", [&](const httplib::Request& req, httplib::Response& res) {
        try {
            auto j = json::parse(req.body);
            std::string event = j.value("event", "");

            if (event == "player_death") {
                std::lock_guard<std::mutex> lock(state_mutex);
                g_state.count++;
                std::cout << "[MeinPlugin] Tode: " << g_state.count << "\n";
                save_state(state_file);
            }
        } catch (const std::exception& e) {
            std::cerr << "[MeinPlugin] Webhook-Fehler: " << e.what() << "\n";
        }
        res.set_content(R"({"status":"ok"})", "application/json");
    });

    std::cout << "[MeinPlugin] läuft auf Port " << port << "\n";
    svr.listen("127.0.0.1", port);   // blockierend
    return 0;
}
```

---

## Fehlerbehandlung & Best Practices

> [!WARNING]
> Das System startet ein abgestürztes Plugin **nicht** automatisch neu.

| Situation | Was tun |
|-----------|---------|
| Config-Datei fehlt | Default-Wert nutzen, **nicht** abstürzen |
| Port bereits belegt | Fehlermeldung ausgeben, cleanly exit |
| HTTP-Request kehrt nicht zurück | **Immer Timeout setzen** |
| Unbehandelter Absturz | Top-level Exception-Handler mit Log-Ausgabe |
| JSON-Parsefehler im Webhook | `try/catch`, 200 OK trotzdem zurückgeben |

### Logging

Schreibe Logs nach `ROOT_DIR/logs/meinplugin.log`. Nutze atomares Schreiben (anhängen) und logge mindestens:
- Plugin-Start mit Port
- Jeden empfangenen Event-Typ
- Jeden Fehler mit Zeitstempel