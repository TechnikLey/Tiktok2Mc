# Folder for plugins
$pluginsDir = "src/plugins"
$version = "v1.0.0"

# Function to prompt for a valid plugin name
function Get-ValidPluginName {
    param([string]$prompt)
    do {
        $pluginName = Read-Host $prompt

        if ($pluginName -notmatch '^[a-z0-9]+$') {
            Write-Host "Invalid name! Only a-z and 0-9 allowed." -ForegroundColor Red
            $valid = $false
        } elseif (Test-Path (Join-Path $pluginsDir $pluginName)) {
            Write-Host "Folder already exists! Please choose another name." -ForegroundColor Red
            $valid = $false
        } else {
            $valid = $true
        }
    } while (-not $valid)
    return $pluginName
}

# Prompt for module name
$pluginName = Get-ValidPluginName "Please enter module name (only a-z and 0-9)"

# Create path
$pluginPath = Join-Path $pluginsDir $pluginName
New-Item -ItemType Directory -Path $pluginPath | Out-Null
Write-Host "Folder '$pluginName' created."

# Create main.py with template
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
Write-Host "File 'main.py' created."

# Create version.txt
$versionFile = Join-Path $pluginPath "version.txt"
$version | Out-File -FilePath $versionFile -Encoding UTF8
Write-Host "File 'version.txt' with content '$version' created."

# Create README.md
$readmeFile = Join-Path $pluginPath "README.md"
"# $pluginName

Version: $version

Description: " | Out-File -FilePath $readmeFile -Encoding UTF8
Write-Host "File 'README.md' created."

pause