# ==========================================
# build.ps1 - TikTok-MC-Gift (Parallel & Optimized)
# ==========================================

$ErrorActionPreference = "Stop"

try {

# ----- Check PowerShell Version -----
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host "❌ ERROR: PowerShell 7 or higher is required!" -ForegroundColor Red
    Write-Host "You are currently using version: $($PSVersionTable.PSVersion.Major)" -ForegroundColor Yellow
    Write-Host "The '-Parallel' feature for fast builds only works in PS7." -ForegroundColor White
    Write-Host "Please install PowerShell 7: https://github.com/PowerShell/PowerShell" -ForegroundColor Cyan
    Write-Host "=========================================================="  -ForegroundColor Red
    Write-Host "`nPress any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit
}

$start = Get-Date
Set-Location -LiteralPath $PSScriptRoot

# ----- 0️⃣ Configuration -----
$MaxThreads = 8
$MaxCopyThreads = 16
$ToolVersion    = "v0.1.0-beta"
$UpdaterVersion = "v1.0.0"             
$OutDir         = Join-Path $PSScriptRoot "build\release"
$CacheDir       = Join-Path $PSScriptRoot "build\cache"
$ExeCacheDir    = Join-Path $CacheDir "exes"
$HashCacheDir   = Join-Path $CacheDir "hashes"

# A central, clean temp folder for all parallel threads
$ParallelTempDir = Join-Path $PSScriptRoot "build\temp_parallel"

# Definition of main files
$CoreExecutables = @(
    @{ Name = "app.exe";           Src = "src\python\main.py";       Dest = "core"      }
    @{ Name = "update.exe";        Src = "src\python\update.py";     Dest = ""          }
    @{ Name = "gui.exe";           Src = "src\python\gui.py";        Dest = "core"      }
    @{ Name = "server.exe";        Src = "src\python\server.py";     Dest = ""          }
    @{ Name = "start.exe";         Src = "src\python\start.py";      Dest = ""          }
    @{ Name = "registry.exe";      Src = "src\python\registry.py";   Dest = "plugins"   }
    @{ Name = "test_trigger.exe";   Src = "tests\send_trigger.py";    Dest = "test"      }
)

# ----- 1️⃣ Preparation & Directory Structure -----
Write-Host "📂 Preparing build environment..." -ForegroundColor Cyan

if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }

$RequiredDirs = @(
    $ExeCacheDir, $HashCacheDir, $OutDir, $ParallelTempDir,
    "$OutDir\core", "$OutDir\plugins", "$OutDir\core\runtime", "$OutDir\core\lib", 
    "$OutDir\core\templates", "$OutDir\core\static\css", "$OutDir\server\java", 
    "$OutDir\server\mc", "$OutDir\config", "$OutDir\data", "$OutDir\test", 
    "$OutDir\logs", "$OutDir\server\mc\plugins\MinecraftServerAPI", 
    "$OutDir\server\mc\world\datapacks\StreamingTool\data\streamingtool\function", 
    "$OutDir\server\mc\plugins\DelayedTNT", "$OutDir\event_hooks"
)

foreach ($d in $RequiredDirs) {
    if (!(Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# ----- 2️⃣ Collect Build Tasks -----
Write-Host "🔍 Collecting all files to compile..." -ForegroundColor Cyan
$AllBuildTasks = @()

# Add main EXEs
foreach ($Item in $CoreExecutables) {
    $AllBuildTasks += [PSCustomObject]@{ Name = $Item.Name; Src = $Item.Src; Dest = $Item.Dest }
}

# Find and add modules
$SrcPluginsRoot = Join-Path $PSScriptRoot "src\plugins"
if (Test-Path $SrcPluginsRoot) {
    $PythonPlugins = Get-ChildItem -LiteralPath $SrcPluginsRoot -Recurse -Filter "*.py" -File | Where-Object {
        $_.FullName -notmatch "[\\/](hash|exe_cache|__pycache__)([\\/]|$)"
    }
    
    foreach ($File in $PythonPlugins) {
        $Rel = ""
        if ($File.DirectoryName.Length -gt $SrcPluginsRoot.Length) { 
            $Rel = $File.DirectoryName.Substring($SrcPluginsRoot.Length).TrimStart('\') 
        }
        $AllBuildTasks += [PSCustomObject]@{ 
            Name = "$($File.BaseName).exe"
            Src  = $File.FullName
            Dest = (Join-Path "plugins" $Rel) 
        }
    }
}

# ----- 3️⃣ Execution: Parallel Build -----
Write-Host "`n🚀 Starting parallel build with $MaxThreads threads for $($AllBuildTasks.Count) files..." -ForegroundColor Cyan

$AllBuildTasks | ForEach-Object -Parallel {
    # Safely load variables from the main script into the thread
    $Item = $_
    $RootBase = $using:PSScriptRoot
    $TargetOut = $using:OutDir
    $HashDir = $using:HashCacheDir
    $CacheDir = $using:ExeCacheDir
    $TempBase = $using:ParallelTempDir

    $FullSrc = [System.IO.Path]::GetFullPath($Item.Src)
    
    # Unique name for cache/hash
    $SafeName = $FullSrc.Replace($RootBase, "").Replace("\", "_").TrimStart('_')
    $HashFile = Join-Path $HashDir ("${SafeName}.sha256")
    $CacheExe = Join-Path $CacheDir ($SafeName.Replace(".py", ".exe"))
    
    $CurrentHash = (Get-FileHash -LiteralPath $FullSrc -Algorithm SHA256).Hash
    $NeedBuild = $true

    if ((Test-Path $HashFile) -and (Test-Path $CacheExe)) {
        if ((Get-Content $HashFile -Raw).Trim() -eq $CurrentHash) { $NeedBuild = $false }
    }

    $TargetDir = if ([string]::IsNullOrWhiteSpace($Item.Dest)) { $TargetOut } else { Join-Path $TargetOut $Item.Dest }
    if (!(Test-Path $TargetDir)) { New-Item $TargetDir -ItemType Directory -Force | Out-Null }
    $FinalPath = Join-Path $TargetDir $Item.Name

    if ($NeedBuild) {
        Write-Host "🔨 [Parallel] Compiling: $($Item.Name)..." -ForegroundColor Yellow
        
        $UniqueId = [Guid]::NewGuid().Guid.Substring(0,8)
        $T_Dist = Join-Path $TempBase "dist_$UniqueId"
        $T_Work = Join-Path $TempBase "work_$UniqueId"
        $T_Spec = Join-Path $TempBase "spec_$UniqueId"

        # Silent build
        python -m PyInstaller --onefile --path="src" $FullSrc --name $($Item.Name) `
            --distpath $T_Dist --workpath $T_Work --specpath $T_Spec `
            --noconfirm --log-level ERROR 2>&1 > $null

        $Fresh = Join-Path $T_Dist $Item.Name
        if (Test-Path $Fresh) {
            Copy-Item $Fresh $FinalPath -Force
            Copy-Item $Fresh $CacheExe -Force
            Set-Content -Path $HashFile -Value $CurrentHash -NoNewline
            Write-Host "✅ Done: $($Item.Name)" -ForegroundColor Green
        } else {
            Write-Error "❌ Failed to compile $($Item.Name)"
        }
        
        # Clean up temp files for this thread
        Remove-Item $T_Dist, $T_Work, $T_Spec -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "📦 Cache hit: $($Item.Name)" -ForegroundColor Gray
        if (!(Test-Path $FinalPath)) { Copy-Item $CacheExe $FinalPath -Force }
    }
} -ThrottleLimit $MaxThreads

# ----- 4️⃣ Assets & Resources (Ultra-Fast with Robocopy) -----
Write-Host "`n📂 Synchronizing assets and resources with $MaxCopyThreads threads" -ForegroundColor Cyan

# Robocopy function with variable thread count
function Sync-Folder {
    param(
        [string]$Source, 
        [string]$Destination,
        [int]$Threads = 8
    )
    if (Test-Path $Source) {
        # /MT:$Threads uses your variable
        robocopy $Source $Destination /E /MT:$Threads /XO /NJH /NJS /NFL /NDL /NC /NS /NP | Out-Null
    }
}

# Calls with the new variable
Sync-Folder "assets" "$OutDir\core\assets" $MaxCopyThreads
Sync-Folder "templates" "$OutDir\core\templates" $MaxCopyThreads
Sync-Folder "tools\Java" "$OutDir\server\java" $MaxCopyThreads
Sync-Folder "src\event_hooks" "$OutDir\event_hooks" $MaxCopyThreads

$Files = @(
    @{ S = "static\css\style.css"; D = "core\static\css\style.css" }
    @{ S = "defaults\config.yaml"; D = "config\config.yaml" }
    @{ S = "defaults\config.default.yaml"; D = "config\config.default.yaml" }
    @{ S = "defaults\gifts.json"; D = "core\gifts.json" }
    @{ S = "LICENSE"; D = "LICENSE" }
    @{ S = "README.md"; D = "README.md" }
    @{ S = "defaults\actions.mca"; D = "data\actions.mca" }
    @{ S = "defaults\http_actions.txt"; D = "data\http_actions.txt" }
    @{ S = "defaults\configServerAPI.yml"; D = "server\mc\plugins\MinecraftServerAPI\config.yml" }
    @{ S = "defaults\DelayedTNTconfig.yml"; D = "server\mc\plugins\DelayedTNT\config.yml" }
    @{ S = "tools\MinecraftServerAPI-1.21.x.jar"; D = "server\mc\plugins" }
    @{ S = "tools\DelayedTNT.jar"; D = "server\mc\plugins" }
    @{ S = "tools\server.jar"; D = "server\mc" }
)

foreach ($f in $Files) {
    if (Test-Path $f.S) {
        $target = Join-Path $OutDir $f.D
        $dir = Split-Path $target -Parent
        if (!(Test-Path $dir)) { New-Item $dir -ItemType Directory -Force | Out-Null }
        Copy-Item $f.S $target -Force
    }
}

# ----- 5️⃣ Metadata & Cleanup -----
Write-Host "🧹 Cleaning up temporary files..." -ForegroundColor Cyan
"ToolVersion: $ToolVersion`nUpdaterVersion: $UpdaterVersion" | Out-File "$OutDir\version.txt" -Encoding UTF8
if (Test-Path $ParallelTempDir) { Remove-Item $ParallelTempDir -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path "src/core/__pycache__") {
    Remove-Item "src/core/__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path "src/python/__pycache__") {
    Remove-Item "src/python/__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
}

# ----- 6️⃣ Release Script -----
Write-Host "📜 Creating upload.ps1..." -ForegroundColor Cyan
$ReleaseZip = "./build/$ToolVersion.zip"
$ReleaseContent = @"
if (!(Test-Path "$ReleaseZip")) {
    Write-Host "📦 Creating ZIP..." -ForegroundColor Cyan
    Compress-Archive -Path "$OutDir" -DestinationPath "$ReleaseZip" -Force
}
if (gh release view $ToolVersion 2>`$null) {
    gh release delete $ToolVersion --yes
    Start-Sleep -Seconds 2
}
gh release create $ToolVersion "$ReleaseZip" --title "$ToolVersion" --notes "Release $ToolVersion"
pause
"@
$ReleaseContent | Out-File "upload.ps1" -Encoding UTF8

# --- Finish ---
$duration = (Get-Date).Subtract($start)
Write-Host "`n======================================" -ForegroundColor Green
Write-Host ("✅ Build completed in {0:mm\:ss\.fff}" -f $duration) -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green

Write-Host "`nPress any key to close this window..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
catch {
    $duration = (Get-Date).Subtract($start)
    Write-Host "`n======================================" -ForegroundColor Red
    Write-Host ("❌ Build FAILED in {0:mm\:ss\.fff}" -f $duration) -ForegroundColor Red
    Write-Host "======================================" -ForegroundColor Red
    Write-Host "\nError message:" -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "======================================" -ForegroundColor Red
    Write-Host "`nPress any key to close this window..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}