# =============================================================================
# FOXFINDER - STATUS DASHBOARD v1.0.0
# =============================================================================
# Simple status display for FoxFinder eBay deal notification service
# Shows: Running status, heartbeat, rate limits, recent activity
# =============================================================================

$VERSION = "1.0.0"
$ErrorActionPreference = "Continue"

# --- WINDOW SETUP ---
$host.UI.RawUI.WindowTitle = "FoxFinder Status Dashboard v$VERSION"
try {
    $null = cmd /c "mode con: cols=70 lines=30" 2>&1
} catch {}

# --- CONFIGURATION ---
$refreshInterval = 30
$scriptRoot = $PSScriptRoot

# File paths (same directory)
$heartbeatFile = Join-Path $scriptRoot ".heartbeat"
$logFile = Join-Path $scriptRoot "foxfinder.log"
$rateFile = Join-Path $scriptRoot "ebay_rate_limit.json"
$configFile = Join-Path $scriptRoot "ebay_config.json"
$seenFile = Join-Path $scriptRoot "ebay_seen_api.json"

# --- HELPER FUNCTIONS ---

function Get-HeartbeatStatus {
    if (-not (Test-Path $heartbeatFile)) {
        return @{ Status = "STOPPED"; Age = -1; Color = "Red" }
    }

    try {
        $content = Get-Content $heartbeatFile -Raw | ConvertFrom-Json
        $timestamp = $content.timestamp
        $age = [int]((Get-Date) - (Get-Date "1970-01-01 00:00:00").AddSeconds($timestamp)).TotalSeconds

        if ($age -lt 120) {
            return @{ Status = "RUNNING"; Age = $age; Color = "Green"; Version = $content.version }
        } elseif ($age -lt 300) {
            return @{ Status = "SLOW"; Age = $age; Color = "Yellow"; Version = $content.version }
        } else {
            return @{ Status = "STALE"; Age = $age; Color = "Red"; Version = $content.version }
        }
    } catch {
        return @{ Status = "ERROR"; Age = -1; Color = "Red" }
    }
}

function Get-RateLimitStatus {
    if (-not (Test-Path $rateFile)) {
        return @{ Calls = 0; Remaining = 5000; Date = "Unknown" }
    }

    try {
        $rate = Get-Content $rateFile -Raw | ConvertFrom-Json
        return @{
            Calls = $rate.calls
            Remaining = $rate.api_remaining
            Date = $rate.date
            ResetTime = $rate.reset_time_utc
        }
    } catch {
        return @{ Calls = 0; Remaining = 5000; Date = "Error" }
    }
}

function Get-SearchCount {
    if (-not (Test-Path $configFile)) {
        return @{ Total = 0; Enabled = 0 }
    }

    try {
        $config = Get-Content $configFile -Raw | ConvertFrom-Json
        $searches = $config.searches
        $enabled = ($searches | Where-Object { $_.enabled -ne $false }).Count
        return @{ Total = $searches.Count; Enabled = $enabled }
    } catch {
        return @{ Total = 0; Enabled = 0 }
    }
}

function Get-SeenCount {
    if (-not (Test-Path $seenFile)) {
        return 0
    }

    try {
        $seen = Get-Content $seenFile -Raw | ConvertFrom-Json
        return ($seen.PSObject.Properties | Measure-Object).Count
    } catch {
        return 0
    }
}

function Get-RecentLogLines {
    param([int]$Lines = 10)

    if (-not (Test-Path $logFile)) {
        return @("No log file found")
    }

    try {
        return Get-Content $logFile -Tail $Lines
    } catch {
        return @("Error reading log")
    }
}

function Format-Duration {
    param([int]$Seconds)

    if ($Seconds -lt 0) { return "?" }
    if ($Seconds -lt 60) { return "${Seconds}s" }
    if ($Seconds -lt 3600) { return "$([int]($Seconds / 60))m" }
    if ($Seconds -lt 86400) {
        $h = [int]($Seconds / 3600)
        $m = [int](($Seconds % 3600) / 60)
        return "${h}h ${m}m"
    }
    $d = [int]($Seconds / 86400)
    $h = [int](($Seconds % 86400) / 3600)
    return "${d}d ${h}h"
}

function Draw-Dashboard {
    Clear-Host

    $hb = Get-HeartbeatStatus
    $rate = Get-RateLimitStatus
    $searches = Get-SearchCount
    $seenCount = Get-SeenCount
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    # Header
    Write-Host ""
    Write-Host "  =====================================================================" -ForegroundColor Cyan
    Write-Host "   FOXFINDER STATUS DASHBOARD                              v$VERSION" -ForegroundColor Cyan
    Write-Host "  =====================================================================" -ForegroundColor Cyan
    Write-Host ""

    # Status Box
    Write-Host "   STATUS" -ForegroundColor White
    Write-Host "   ------" -ForegroundColor DarkGray

    $statusIcon = if ($hb.Status -eq "RUNNING") { "[*]" } else { "[ ]" }
    Write-Host -NoNewline "   $statusIcon FoxFinder: "
    Write-Host -NoNewline $hb.Status -ForegroundColor $hb.Color
    if ($hb.Age -ge 0) {
        Write-Host -NoNewline " ($(Format-Duration $hb.Age) ago)"
    }
    if ($hb.Version) {
        Write-Host " v$($hb.Version)" -ForegroundColor DarkGray
    } else {
        Write-Host ""
    }

    Write-Host ""

    # Rate Limits
    Write-Host "   RATE LIMITS (Pacific Date: $($rate.Date))" -ForegroundColor White
    Write-Host "   ------" -ForegroundColor DarkGray

    $usedPercent = if ($rate.Remaining -gt 0) { [int](($rate.Calls / 5000) * 100) } else { 100 }
    $barLength = 40
    $filledLength = [int]($usedPercent / 100 * $barLength)
    $bar = ("=" * $filledLength) + ("-" * ($barLength - $filledLength))

    $barColor = if ($usedPercent -lt 50) { "Green" } elseif ($usedPercent -lt 80) { "Yellow" } else { "Red" }

    Write-Host -NoNewline "   Calls Today: "
    Write-Host -NoNewline "$($rate.Calls)" -ForegroundColor $barColor
    Write-Host " / 5000 ($usedPercent%)"

    Write-Host -NoNewline "   [$bar] " -ForegroundColor $barColor
    Write-Host "$($rate.Remaining) remaining" -ForegroundColor DarkGray

    Write-Host ""

    # Searches
    Write-Host "   SEARCHES" -ForegroundColor White
    Write-Host "   ------" -ForegroundColor DarkGray
    Write-Host "   Searches: $($searches.Enabled)/$($searches.Total) enabled"
    Write-Host "   Seen Items: $seenCount cached"

    Write-Host ""

    # Recent Activity
    Write-Host "   RECENT ACTIVITY" -ForegroundColor White
    Write-Host "   ------" -ForegroundColor DarkGray

    $recentLines = Get-RecentLogLines -Lines 8
    foreach ($line in $recentLines) {
        $truncated = if ($line.Length -gt 65) { $line.Substring(0, 62) + "..." } else { $line }

        # Color based on content
        if ($line -match "ERROR|FAIL") {
            Write-Host "   $truncated" -ForegroundColor Red
        } elseif ($line -match "Found:|new listings") {
            Write-Host "   $truncated" -ForegroundColor Green
        } elseif ($line -match "WARNING") {
            Write-Host "   $truncated" -ForegroundColor Yellow
        } else {
            Write-Host "   $truncated" -ForegroundColor DarkGray
        }
    }

    Write-Host ""
    Write-Host "  =====================================================================" -ForegroundColor DarkGray
    Write-Host "   Last refresh: $now | Next in ${refreshInterval}s | Press Q to quit" -ForegroundColor DarkGray
    Write-Host "  =====================================================================" -ForegroundColor DarkGray
}

# --- MAIN LOOP ---

Write-Host "Starting FoxFinder Status Dashboard..." -ForegroundColor Cyan
Start-Sleep -Milliseconds 500

while ($true) {
    Draw-Dashboard

    # Wait with keyboard check
    $waited = 0
    while ($waited -lt $refreshInterval) {
        Start-Sleep -Milliseconds 500
        $waited += 0.5

        # Check for keypress
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq 'Q') {
                Write-Host "`n   Exiting dashboard..." -ForegroundColor Yellow
                exit 0
            }
            if ($key.Key -eq 'R') {
                # Force refresh
                break
            }
        }
    }
}
