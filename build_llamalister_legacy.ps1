# Build script for LlamaLister
# Requires PyInstaller: pip install pyinstaller

$ErrorActionPreference = "Stop"

# Ensure we are running from the script's directory
Set-Location $PSScriptRoot

Write-Host "🚀 Starting LlamaLister Build Process..." -ForegroundColor Cyan

# 1. Install Requirements
Write-Host "📦 Checking dependencies..."
pip install -r requirements_llamalister.txt

# 2. Clean previous builds
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "llamalister.spec") { Remove-Item -Force "llamalister.spec" }

# 3. Run PyInstaller
Write-Host "🔨 Building Executable..."
# Note: We are adding --hidden-import for modules that might be missed
# We are also handling the memory_service path if possible, but for a standalone utility
# we might need to ensure it's self-contained or the user has the DB.
# For this build, we'll assume memory_service is optional or bundled if we add it to datas.

# We need to find where memory_service is to bundle it if we want it to work in the EXE
$RootDir = Split-Path $PSScriptRoot -Parent
$MemoryServicePath = Join-Path $RootDir "Core_AUA_System\src\memory_service.py"

# Ensure listings.csv exists for bundling (even if empty)
if (-not (Test-Path "listings.csv")) {
    Write-Host "   Creating empty listings.csv for bundling..."
    Set-Content -Path "listings.csv" -Value "Timestamp,Title,Description,Price,Category,Condition,Platforms,Images"
}

if (Test-Path $MemoryServicePath) {
    Write-Host "   Found memory_service.py, bundling..."
    # Copy to local for easier bundling or use --add-data
    # Simpler to just let the script handle the import check, but for EXE we want it.
    # We will use --paths to include the source dir
    $SourcePath = Join-Path $RootDir "Core_AUA_System\src"

    pyinstaller --noconfirm --onefile --windowed `
        --name "LlamaLister" `
        --paths "$SourcePath" `
        --hidden-import "memory_service" `
        --hidden-import "sqlite3" `
        --add-data "listings.csv;." `
        --icon "NONE" `
        --exclude-module "PyQt5" `
        --exclude-module "PyQt6" `
        --exclude-module "matplotlib" `
        --exclude-module "IPython" `
        llamalister.py
} else {
    Write-Host "⚠️ memory_service.py not found in expected location. Building without it."
    pyinstaller --noconfirm --onefile --windowed --name "LlamaLister" llamalister.py
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Build Complete! Executable is in 'dist/LlamaLister.exe'" -ForegroundColor Green
} else {
    Write-Host "❌ Build Failed!" -ForegroundColor Red
    exit 1
}
