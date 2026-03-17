param(
  [string]$HostAddress = "0.0.0.0",
  [int]$Port = 8000,
  [string]$AdminUser = "admin",
  [string]$AdminPass = "change-me",
  [string]$Proxy = "",
  [int]$InitSinceDays = 180,
  [switch]$InitCrawl,
  [int]$CrawlIntervalHours = 48
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  python -m venv .venv
}

$py = ".\\.venv\\Scripts\\python.exe"

try {
  & $py -m pip --version | Out-Null
} catch {
  & $py -m ensurepip --upgrade | Out-Null
  & $py -m pip install --upgrade pip | Out-Null
}

& $py -m pip install -r requirements.txt

$alembicExe = ".\\.venv\\Scripts\\alembic.exe"
if (Test-Path $alembicExe) {
  & $alembicExe upgrade head
} else {
  alembic upgrade head
}

& $py -m app.manage ensure-user --username $AdminUser --password $AdminPass --admin

if ($Proxy) {
  $env:HTTP_PROXY = $Proxy
  $env:HTTPS_PROXY = $Proxy
}

# In-process scheduler for VM/container usage. For Cloud Run, prefer Cloud Scheduler + HTTP trigger.
if ($CrawlIntervalHours -gt 0) {
  $env:CRAWL_INTERVAL_HOURS = "$CrawlIntervalHours"
  $env:CRAWL_SINCE_DAYS = "$InitSinceDays"
  $env:CRAWL_INITIAL_DELAY_SEC = "15"
  $env:CRAWL_JITTER_SEC = "30"
}

if ($InitCrawl) {
  $hasJobs = @"
import sqlite3
con=sqlite3.connect('recruit_tracker.db')
try:
    n = con.execute('select count(*) from job_postings').fetchone()[0]
    print(n)
finally:
    con.close()
"@ | & $py -

  if ([int]$hasJobs -eq 0) {
    & $py -m app.crawl seed-default --proxy $Proxy
    & $py -m app.crawl run --since-days $InitSinceDays
  }
}

& $py -m uvicorn main:app --host $HostAddress --port $Port
