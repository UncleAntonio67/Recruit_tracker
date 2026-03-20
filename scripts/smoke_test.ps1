param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8011,
  [string]$AdminUser = "admin",
  [string]$AdminPass = "change-me",
  [int]$TimeoutSec = 25
)

$ErrorActionPreference = "Stop"

function Wait-HttpOk([string]$Url, [int]$TimeoutSec) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method GET -TimeoutSec 3
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $true }
    } catch {
      Start-Sleep -Milliseconds 250
    }
  }
  return $false
}

$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\\Scripts\\python.exe"
if (-not (Test-Path $python)) {
  throw "python not found: $python (please run scripts/run_local.ps1 once to create venv)"
}

$baseUrl = "http://$HostAddress`:$Port"

Write-Host "Starting server at $baseUrl ..."
$env:BOOTSTRAP_ADMIN_USERNAME = $AdminUser
$env:BOOTSTRAP_ADMIN_PASSWORD = $AdminPass
$env:CRAWL_INTERVAL_HOURS = "0"
$env:ENV = "dev"
$env:DATABASE_URL = "sqlite:///./smoke_test.db"

$dbPath = Join-Path $repo "smoke_test.db"
if (Test-Path $dbPath) { Remove-Item -Force $dbPath -ErrorAction SilentlyContinue }

Write-Host "Migrating database (smoke_test.db) ..."
& $python -m alembic upgrade head | Out-Null
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed" }

$p = Start-Process -FilePath $python -ArgumentList @(
  "-m", "uvicorn", "main:app",
  "--host", $HostAddress,
  "--port", "$Port"
) -WorkingDirectory $repo -PassThru -WindowStyle Hidden

try {
  if (-not (Wait-HttpOk "$baseUrl/login" $TimeoutSec)) {
    throw "server did not become ready within ${TimeoutSec}s"
  }

  $sess = New-Object Microsoft.PowerShell.Commands.WebRequestSession

  # Login
  $loginResp = Invoke-WebRequest -UseBasicParsing -WebSession $sess -Uri "$baseUrl/login" -Method POST -Body @{
    username = $AdminUser
    password = $AdminPass
  } -MaximumRedirection 0 -ErrorAction SilentlyContinue
  if ($loginResp.StatusCode -ne 302) {
    throw "login failed, status=$($loginResp.StatusCode)"
  }

  # Basic pages
  foreach ($path in @("/jobs", "/companies", "/applications", "/jobs/import", "/admin/sources")) {
    $r = Invoke-WebRequest -UseBasicParsing -WebSession $sess -Uri ($baseUrl + $path) -Method GET
    if ($r.StatusCode -ne 200) { throw "GET $path failed: $($r.StatusCode)" }
  }

  # Seed one job near Shanghai date boundary and verify date filter is Shanghai-based.
  @'
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Company, JobPosting, JobSource

UTC = timezone.utc
SH = timezone(timedelta(hours=8))

db = SessionLocal()
try:
    c = db.execute(select(Company).where(Company.name == "SmokeCo")).scalar_one_or_none()
    if not c:
        c = Company(name="SmokeCo", recruitment_url="https://example.com")
        db.add(c)
        db.commit()

    # 2026-03-20 00:30 in Shanghai => 2026-03-19 16:30 UTC.
    published_utc = datetime(2026, 3, 20, 0, 30, tzinfo=SH).astimezone(UTC)
    job = JobPosting(
        company_id=c.id,
        title="Smoke Engineer",
        city="北京/上海",
        published_at=published_utc,
        excerpt="smoke job",
        status="active",
    )
    db.add(job)
    db.commit()

    db.add(
        JobSource(
            job_posting_id=job.id,
            source_type="import",
            source_kind="url",
            source_name="smoke",
            source_url="https://example.com/smoke-job",
        )
    )
    db.commit()
finally:
    db.close()
'@ | & $python -
  if ($LASTEXITCODE -ne 0) { throw "failed seeding smoke job" }

  $jobsFiltered = Invoke-WebRequest -UseBasicParsing -WebSession $sess -Uri ($baseUrl + "/jobs?published_from=2026-03-20&published_to=2026-03-20") -Method GET
  if ($jobsFiltered.StatusCode -ne 200) { throw "GET /jobs date filter failed: $($jobsFiltered.StatusCode)" }
  if ($jobsFiltered.Content -notmatch "Smoke Engineer") {
    throw "job not found under Shanghai date filter (expected Smoke Engineer)"
  }

  # Create an application (ASCII-only payload to avoid terminal encoding pitfalls)
  $title = "smoke-test-" + ([Guid]::NewGuid().ToString("N").Substring(0, 8))
  $newResp = Invoke-WebRequest -UseBasicParsing -WebSession $sess -Uri "$baseUrl/applications/new" -Method POST -Body @{
    title_text = $title
    company_text = "TestCo"
    city_text = "Beijing"
    source_url = "https://example.com"
    channel_other = "smoke"
    stage = "applied"
    priority = "3"
    applied_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm")
  } -MaximumRedirection 0 -ErrorAction SilentlyContinue

  if ($newResp.StatusCode -ne 302) {
    throw "create application failed, status=$($newResp.StatusCode)"
  }

  $loc = $newResp.Headers["Location"]
  if (-not $loc) { throw "missing redirect location for new application" }
  $appUrl = if ($loc.StartsWith("http")) { $loc } else { $baseUrl + $loc }

  # Add an event
  $evResp = Invoke-WebRequest -UseBasicParsing -WebSession $sess -Uri ($appUrl + "/events") -Method POST -Body @{
    event_type = "Interview1"
    occurred_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm")
    result = "pass"
    note = "smoke test event"
  } -MaximumRedirection 0 -ErrorAction SilentlyContinue
  if ($evResp.StatusCode -ne 302) {
    throw "add event failed, status=$($evResp.StatusCode)"
  }

  $detail = Invoke-WebRequest -UseBasicParsing -WebSession $sess -Uri $appUrl -Method GET
  if ($detail.StatusCode -ne 200) { throw "GET application detail failed: $($detail.StatusCode)" }
  if ($detail.Content -notmatch "smoke test event") { throw "event note not found in detail page" }

  Write-Host "SMOKE TEST OK"
} finally {
  Write-Host "Stopping server pid=$($p.Id) ..."
  try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
  try {
    if (Test-Path $dbPath) { Remove-Item -Force $dbPath -ErrorAction SilentlyContinue }
  } catch {}
}
