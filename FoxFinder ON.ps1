# FoxFinder ON - Start the eBay deal notification service
$scriptDir = $PSScriptRoot
$pythonScript = Join-Path $scriptDir "foxfinder.py"
$shutdownFile = Join-Path $scriptDir ".shutdown_requested"

# Clear any shutdown signal
if (Test-Path $shutdownFile) {
    Remove-Item $shutdownFile -Force
    Write-Host "Cleared previous shutdown signal" -ForegroundColor Yellow
}

# Check if already running
$existingProcess = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*foxfinder*" }

if ($existingProcess) {
    Write-Host "FoxFinder is already running (PID: $($existingProcess.Id))" -ForegroundColor Yellow
    Write-Host "Use 'FoxFinder OFF' to stop it first." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    exit 0
}

# Start the notification service
Write-Host "Starting FoxFinder..." -ForegroundColor Green
Start-Process -FilePath "python" -ArgumentList $pythonScript -WindowStyle Normal

Write-Host "FoxFinder started!" -ForegroundColor Green
Write-Host "Use 'Status Dashboard' to view status, 'FoxFinder OFF' to stop." -ForegroundColor Cyan
Start-Sleep -Seconds 2
