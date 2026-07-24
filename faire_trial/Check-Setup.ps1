$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "Faire Windows Trial - Setup Check" -ForegroundColor Cyan
Write-Host "================================"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama is not installed or is not on PATH." -ForegroundColor Yellow
    Write-Host "Install it from: https://ollama.com/download/windows"
    Write-Host "Then open a new terminal and run: ollama pull llama3.2:3b"
    exit 1
}

Write-Host "Ollama command found." -ForegroundColor Green
try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 4
    Write-Host "Ollama service is running." -ForegroundColor Green
    if ($models.models.Count -eq 0) {
        Write-Host "No local models found. Run: ollama pull llama3.2:3b" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Local models:" -ForegroundColor Cyan
    $models.models | ForEach-Object { Write-Host (" - " + $_.name) }
    Write-Host ""
    Write-Host "Setup is ready. Double-click Start-Faire.cmd." -ForegroundColor Green
} catch {
    Write-Host "Ollama is installed but its local service did not answer." -ForegroundColor Yellow
    Write-Host "Start Ollama from the Windows Start menu, then run this check again."
    exit 1
}
