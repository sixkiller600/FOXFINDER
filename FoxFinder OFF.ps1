# FoxFinder OFF - Gracefully stop the eBay deal notification service
$scriptDir = $PSScriptRoot
$shutdownFile = Join-Path $scriptDir ".shutdown_requested"

Write-Host "Requesting FoxFinder shutdown..." -ForegroundColor Yellow

# Create shutdown signal file
$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
Set-Content -Path $shutdownFile -Value $timestamp -Force

Write-Host "Shutdown signal sent." -ForegroundColor Green
Write-Host "FoxFinder will stop after completing current cycle (up to 2 minutes)." -ForegroundColor Cyan

# Wait for process to exit
$maxWait = 120
$waited = 0
while ($waited -lt $maxWait) {
    $process = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*foxfinder*" }

    if (-not $process) {
        Write-Host "FoxFinder stopped successfully!" -ForegroundColor Green
        Start-Sleep -Seconds 2
        exit 0
    }

    Start-Sleep -Seconds 2
    $waited += 2
    Write-Host "Waiting for graceful shutdown... ($waited/$maxWait seconds)" -ForegroundColor DarkGray
}

Write-Host "Graceful shutdown timed out. Force stopping process..." -ForegroundColor Red
Get-Process -Name "python*" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*foxfinder*" } |
    Stop-Process -Force

Write-Host "FoxFinder stopped." -ForegroundColor Yellow
Start-Sleep -Seconds 2
