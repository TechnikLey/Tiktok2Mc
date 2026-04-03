# Ordner für Plugins
$pluginsDir = "src/plugins"
$version = "v1.0.0"

# Funktion zum Abfragen eines gültigen Plugin-Namens
function Get-ValidPluginName {
    param([string]$prompt)
    do {
        $pluginName = Read-Host $prompt

        if ($pluginName -notmatch '^[a-z0-9]+$') {
            Write-Host "Ungültiger Name! Nur a-z und 0-9 erlaubt." -ForegroundColor Red
            $valid = $false
        } elseif (Test-Path (Join-Path $pluginsDir $pluginName)) {
            Write-Host "Ordner existiert bereits! Bitte anderen Namen wählen." -ForegroundColor Red
            $valid = $false
        } else {
            $valid = $true
        }
    } while (-not $valid)
    return $pluginName
}

# Modulname abfragen
$pluginName = Get-ValidPluginName "Bitte Modulname eingeben (nur a-z und 0-9)"

# Pfad erstellen
$pluginPath = Join-Path $pluginsDir $pluginName
New-Item -ItemType Directory -Path $pluginPath | Out-Null
Write-Host "Ordner '$pluginName' erstellt."

# main.py erstellen mit Template
$mainFile = Join-Path $pluginPath "main.py"
@"
from core import load_config, parse_args, get_root_dir, get_base_dir, get_base_file, register_plugin, AppConfig
import sys

BASE_DIR = get_base_dir()
ROOT_DIR = get_root_dir()
CONFIG_FILE = (ROOT_DIR / "config" / "config.yaml").resolve()
DATA_DIR = (ROOT_DIR / "data").resolve()
MAIN_FILE = get_base_file()
args = parse_args()

cfg = load_config(CONFIG_FILE)

gui_hidden = args.gui_hidden
register_only = args.register_only

if register_only:
    register_plugin(AppConfig(
        name="test",
        path=MAIN_FILE,
        enable=True,
        level=4,
        ics=False
    ))
    sys.exit(0)
"@ | Out-File -FilePath $mainFile -Encoding UTF8
Write-Host "Datei 'main.py' erstellt."

# version.txt erstellen
$versionFile = Join-Path $pluginPath "version.txt"
$version | Out-File -FilePath $versionFile -Encoding UTF8
Write-Host "Datei 'version.txt' mit Inhalt '$version' erstellt."

# README.md erstellen
$readmeFile = Join-Path $pluginPath "README.md"
"# $pluginName

Version: $version

Beschreibung: " | Out-File -FilePath $readmeFile -Encoding UTF8
Write-Host "Datei 'README.md' erstellt."

pause