param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [string]$AdminUser = "admin",
  [string]$AdminPass = "change-me",
  [string]$Proxy = "",
  [int]$InitSinceDays = 180,
  [switch]$InitCrawl,
  [switch]$Reload,
  [int]$CrawlIntervalHours = 48
)

$ErrorActionPreference = "Stop"

$root = Join-Path $PSScriptRoot ".."
$runLocal = Join-Path $PSScriptRoot "run_local.ps1"

if (-not (Test-Path $runLocal)) {
  throw "run_local.ps1 not found: $runLocal"
}

Set-Location $root

$outLog = Join-Path $root "server.out.log"
$errLog = Join-Path $root "server.err.log"

$args = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", $runLocal,
  "-HostAddress", $HostAddress,
  "-Port", "$Port",
  "-AdminUser", $AdminUser,
  "-AdminPass", $AdminPass,
  "-InitSinceDays", "$InitSinceDays",
  "-CrawlIntervalHours", "$CrawlIntervalHours"
)

if ($Proxy) { $args += @("-Proxy", $Proxy) }
if ($InitCrawl) { $args += "-InitCrawl" }
if ($Reload) { $args += "-Reload" }

Start-Process -FilePath "powershell" -ArgumentList $args -WorkingDirectory $root -RedirectStandardOutput $outLog -RedirectStandardError $errLog

Write-Output "started: http://$HostAddress`:$Port"
Write-Output "logs: $outLog / $errLog"

