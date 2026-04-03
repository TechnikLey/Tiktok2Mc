# Lokale Entwicklung einrichten

In diesem Kapitel richtest du deine lokale Entwicklungsumgebung ein. Das ist eine einmalige Aufgabe – danach kannst du direkt mit der Entwicklung starten.

---

## Anforderungen

### Windows

- **Windows 10 oder 11**
- **Python 3.12+** (empfohlen Python 3.12)
- **Git** (zum Repository klonen)
- **PowerShell 7**

### Java & Minecraft Server

- **Java-Laufzeitumgebung**: Der Ordner `tools/Java/` muss vorhanden sein (entweder mit Java-Dateien oder deiner eigenen Java-Installation).
- **Minecraft Server**: Die Datei `tools/server.jar` wird benötigt (Minecraft-Server-JAR-Datei).

> [!IMPORTANT]
> Stelle sicher, dass sich sowohl der Ordner `tools/Java/` als auch die Datei `tools/server.jar` im Projekt befinden. Ohne diese Komponenten funktionieren einige Features (z.B. Minecraft-Integration) nicht!

### macOS / Linux

- **Python 3.12+** (empfohlen Python 3.12)
- **Git**
- **Bash oder ähnliche Shell**

> [!WARNING]
> Das Projekt wird hauptsächlich auf **Windows** entwickelt. Auf macOS/Linux können einzelne Features eingeschränkt sein.
> In Zukünftigen Version soll allerdings macOS/Linux voll untersützt werden.

---

## Schritt 1: Python installieren

### Windows

1. Besuche [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. Lade die aktuelle **Python 3.X** herunter (Windows x86-64)
3. **Wichtig:** Beim Installer aktiviere die Option **"Add Python to PATH"**
4. Klicke "Install Now"

**Überprüfung:** Öffne PowerShell und tippe:

```powershell
python --version
```

Du solltest sehen: `Python 3.12.x` (oder deine Version)

### macOS

```bash
brew install python@3.X
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3.X python3.X-venv
```

---

## Schritt 2: Git installieren

### Windows

1. Besuche [https://git-scm.com/download/win](https://git-scm.com/download/win) oder [https://desktop.github.com/download/](https://desktop.github.com/download/)
2. Lade den Installer herunter
3. Führe den Installer aus (Standard-Einstellungen sind OK)

**Überprüfung:**

```powershell
git --version
```

### macOS

```bash
brew install git
```

### Linux

```bash
sudo apt install git
```

---

## Schritt 3: Repository klonen

Das Repository ist dein lokales Projekt. Du speicherst deine Arbeitung dort.

> [!TIP]
> Prüfe nach dem Klonen, ob der Ordner `tools/Java/` und die Datei `tools/server.jar` vorhanden sind. Falls nicht, musst du sie selbst hinzufügen.

Es gibt zwei Möglichkeiten:

### Option 1: Mit Git klonen (empfohlen)

```bash
git clone https://github.com/TechnikLey/Streaming_Tool.git
cd Streaming_Tool
```

Das braucht ein paar Sekunden. Danach solltest du alle Dateien lokal haben.

**Vorteil:** Du kannst später Updates mit `git pull` herunterladen.

---

### Option 2: Als ZIP-Datei herunterladen

Falls du Git nicht verwenden möchtest:

1. **Besuche das Repository:**
   [https://github.com/TechnikLey/Streaming_Tool](https://github.com/TechnikLey/Streaming_Tool)

2. **Klicke auf den grünen Button "Code"** (oben rechts)

3. **Wähle "Download ZIP"**

4. **Entpacke die ZIP-Datei** an einem geeigneten Ort (z.B. `C:\Users\dein_name\Streaming_Tool`)

5. **Öffne PowerShell und navigiere dorthin:**

```powershell
cd C:\Users\dein_name\Streaming_Tool
```

**Hinweis:** Mit ZIP-Methode musst du später Updates manuell herunterladen (nicht ideal für Entwicklung).

---

## Schritt 4: Virtuelle Python-Umgebung erstellen

Eine **virtuelle Umgebung** ist wie ein isolierter Python "Container" für dieses Projekt. Das verhindert Konflikte mit anderen Python-Projekten auf deinem System.

> [!NOTE]
> **Virtuelle Umgebung ist optional!**
> 
> Falls du anfängst, Fehler bekommst, oder es dir zu kompliziert ist: Du kannst auch **direkt ohne venv arbeiten** (siehe unten).
> Wir empfehlen venv für erfahrenere Entwickler, aber es ist nicht zwingend notwendig.

---

### Option A: Mit virtueller Umgebung (empfohlen)

#### Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### macOS / Linux

```bash
python3.12 -m venv venv
source venv/bin/activate
```

> [!NOTE]
> Falls die Aktivierung in PowerShell fehler macht, führe erst aus:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

**Überprüfung:** Deine Shell-Zeile sollte sich verändern und `(venv)` zeigen:

```
(venv) C:\Streaming_Tool>
```

Das bedeutet, du bist in der virtuellen Umgebung. ✓

**Vorteile:**
- ✓ Saubere Isolation (keine Konflikte mit anderen Projekten)
- ✓ Professionelle Entwicklung
- ✓ Einfache Deinstallation (einfach `venv`-Ordner löschen)

**Nachteile:**
- ✗ Ein paar Extra-Schritte beim Setup

---

### Option B: Ohne virtuelle Umgebung (schneller, aber weniger sauber)

Falls du venv überspringen möchtest, gehe direkt zu **Schritt 5: Abhängigkeiten installieren**.

Führe dann aus:

```bash
pip install -r requirements.txt
```

Die Pakete werden **global** auf deinem System installiert.

**Vorteile:**
- ✓ Schneller Setup
- ✓ Weniger zu verstehen

**Nachteile:**
- ✗ Pakete auch von anderen Projekten beeinflussen sich gegenseitig
- ✗ Schwerer zu deinstallieren/aufzuräumen
- ✗ Nicht ideal für mehrere Python-Projekte

---

## Schritt 5: Abhängigkeiten installieren

Jetzt installieren wir alle Python-Pakete, die das Projekt braucht:

> [!NOTE]
> Für die Minecraft-Integration wird zusätzlich eine Java-Laufzeitumgebung im Ordner `tools/Java/` und die Datei `tools/server.jar` benötigt.

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Das braucht ein paar Minuten. Beispiel-Output:

```
Collecting TikTokLive==0.8.0
  Using cached ...
Collecting Flask==3.0.0
  Using cached ...
...
Successfully installed TikTokLive-0.8.0 Flask-3.0.0 ...
```

**Was wird installiert?**

- **TikTokLive**: Die API zum Empfangen von TikTok-Events
- **Flask**: Ein Webframework (für Webhooks & GUIs)
- **pywebview**: Für GUIs (Desktop-Fenster)
- **PyYAML**: Für Config-Dateien
- Und mehr...

---

## Schritt 6: Konfiguration initialisieren

Das System braucht eine `config.yaml`, um zu starten.

### Falls sie noch nicht existiert:

```bash
cp defaults/config.default.yaml config/config.yaml
```

Das erstellt eine Standard-Konfiguration.

### Grundlegende Einstellungen

Öffne `config/config.yaml` in deinem Editor (z.B. VS Code) und passe an:

```yaml
# Dein TikTok Live-Account Name
tiktok_user: "dein_tiktok_name"

# Ports für verschiedene Plugins
MinecraftServerAPI:
  Enable: true
  WebServerPort: 8888
  
Timer:
  Enable: true
  StartTime: 10
  
WinCounter:
  Enable: true
  
DeathCounter:
  Enable: true
```

> [!TIP]
> Du musst nicht alles verstehen. Wichtig ist nur:
> 1. `tiktok_user`: Dein TikTok-Kanal-Name
> 2. Die Ports dürfen nicht in Benutzung sein

---

## Schritt 7: Erstes Plugin erstellen (Optional)

Falls du schnell ein kleines Test-Plugin erstellen möchtest:

```powershell
# Windows
.\create_plugin.ps1

# macOS / Linux
bash create_plugin.ps1
```

Das Skript fragt dich nach einer Plugin-ID. Gib z.B. `testplugin` ein.

Danach findest du unter `src/plugins/testplugin/` dein Plugin mit Boilerplate-Code.

---

## Virtuelle Umgebung aktivieren / deaktivieren

### Beim nächsten Mal (Virtual Environment reaktivieren)

**Windows:**
```powershell
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

### Wenn du fertig bist (Virtual Environment verlassen)

```bash
deactivate
```

---

## Häufige Probleme & Lösungen

| Problem | Lösung |
|---------|--------|
| `python: command not found` | Python nicht im PATH. Neu installieren und "Add Python to PATH" aktivieren |
| `ModuleNotFoundError: No module named 'TikTokLive'` | `pip install -r requirements.txt` noch nicht ausgeführt |
| `Port 8080 already in use` | Andere Anwendung nutzt den Port. In `config.yaml` einen anderen Port wählen |
| `Permission denied` (macOS/Linux) | `chmod +x create_plugin.ps1` ausführen |
| venv aktiviert sich nicht (PowerShell) | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` ausführen |
| `pip: The term 'pip' is not recognized as a name of a cmdlet, function, script file, or executable program.` | Führe `python -m pip` aus dies kann helfen |

---

## VS Code Setup (Empfohlen)

Falls du **VS Code** nutzt (kostenlos, sehr beliebt), kannst du es so konfigurieren:

1. Lade VS Code herunter: [https://code.visualstudio.com/](https://code.visualstudio.com/)
2. Öffne den Streaming_Tool-Ordner: `File → Open Folder`
3. Installiere diese Erweiterungen (Extensions):
   - **Python** (Microsoft)
   - **Pylance** (Microsoft)

4. Wende den Python-Interpreter auf deine `venv` an:
   - `Ctrl+Shift+P` → "Python: Select Interpreter"
   - Wähle `./venv/bin/python` (oder `.\venv\Scripts\python.exe` auf Windows)
   - Allternativ direkt Python auswählen wenn du kein `venv` nutzt

Das war's! Jetzt hast du Syntax-Highlighting, Autocomplete und Debugging.

> [!TIP]
> Solltest du bei einem der Schritte auf Probleme stoßen, dann schau im Internet oder auf YouTube nach einer Lösung.

---

## Nächste Schritte

Du hast jetzt:

✓ Python installiert  
✓ Das Repository geklont  
✓ Dependencies installiert  
✓ Die Config angepasst  
✓ Basis-Tests durchgeführt  

Du bist ready! 

**Nächstes Kapitel:** [Wie das System zusammenarbeitet](./ch01-00-How-the-System-Works-Together.md)

Dort lernen wir, wie die einzelnen Komponenten zusammenspielen.
