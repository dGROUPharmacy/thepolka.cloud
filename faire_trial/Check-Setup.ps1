$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "Faire Standalone - Setup Check" -ForegroundColor Cyan
Write-Host "================================"

if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Host "Windows PowerShell 5.1 or newer is required." -ForegroundColor Yellow
    exit 1
}

try {
    Add-Type -AssemblyName PresentationFramework
    Write-Host "Windows desktop framework is available." -ForegroundColor Green
} catch {
    Write-Host "The Windows desktop framework could not be loaded." -ForegroundColor Yellow
    exit 1
}

$webViewRuntime = @(
    "C:\Program Files (x86)\Microsoft\EdgeWebView\Application",
    "C:\Program Files\Microsoft\EdgeWebView\Application",
    (Join-Path $env:LOCALAPPDATA "Microsoft\EdgeWebView\Application")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($webViewRuntime) {
    Write-Host "Modern Faire web runtime is available." -ForegroundColor Green
} else {
    Write-Host "Microsoft Edge WebView2 Runtime was not detected. Faire will use its legacy compatibility browser." -ForegroundColor Yellow
}

try {
    $localModels = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 1
    if ($localModels.models.Count -gt 0) {
        Write-Host "Private local intelligence is available: $($localModels.models[0].name)" -ForegroundColor Green
    } else {
        Write-Host "Local model runtime found, but no model is installed. Built-in Faire intelligence remains available." -ForegroundColor Yellow
    }
} catch {
    Write-Host "No local model detected. Built-in Faire intelligence remains available; no cloud API is required." -ForegroundColor Green
}

Write-Host "Internet is optional and used only for requested live web, weather, media, Drive, or Zoom features." -ForegroundColor Green
Write-Host ""
Write-Host "Faire is ready. Double-click Start-Faire.cmd." -ForegroundColor Green
