param(
  [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$py = ".\\.venv\\Scripts\\python.exe"
if (-not (Test-Path $py)) {
  throw "venv not found. Run scripts\\run_local.ps1 once first."
}

$args = @("-m", "app.crawl", "seed-official")
if ($Proxy) {
  $args += @("--proxy", $Proxy)
}

& $py @args

