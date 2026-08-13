<#
    Build script for PDF Logo Stamper (Windows, PowerShell).

    Usage:
        .\build.ps1              # run tests, then build dist\PDF Logo Stamper.exe
        .\build.ps1 -SkipTests   # build only
        .\build.ps1 -TestsOnly   # run the test-suite only
#>
param(
    [switch]$SkipTests,
    [switch]$TestsOnly
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Step($text) {
    Write-Host ""
    Write-Host "==> $text" -ForegroundColor Cyan
}

Write-Step "Checking Python"
python --version
if (-not $?) { throw "Python is not on PATH." }

Write-Step "Installing runtime dependencies"
python -m pip install --quiet --requirement requirements.txt

if (-not $SkipTests) {
    Write-Step "Running the test-suite"
    python -m unittest discover -s tests -t .
    if (-not $?) { throw "Tests failed - build stopped." }
}
if ($TestsOnly) {
    Write-Host ""
    Write-Host "Tests finished." -ForegroundColor Green
    exit 0
}

Write-Step "Installing PyInstaller"
python -m pip install --quiet "pyinstaller>=6.0"

Write-Step "Cleaning previous build output"
foreach ($path in @("build", "dist")) {
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}

Write-Step "Building the executable"
python -m PyInstaller --noconfirm pdf_logo_stamper.spec

$exe = Join-Path "dist" "PDF Logo Stamper.exe"
if (-not (Test-Path $exe)) { throw "Build did not produce $exe" }
$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)

Write-Host ""
Write-Host "Build complete: $exe ($sizeMb MB)" -ForegroundColor Green
Write-Host "Distribute that single file - the target PC does not need Python." -ForegroundColor Green
