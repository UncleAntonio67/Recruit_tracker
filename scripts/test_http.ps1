param(
  [string]$Url = "https://example.com",
  [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$py = ".\\.venv\\Scripts\\python.exe"
if (-not (Test-Path $py)) {
  throw "venv not found. Run scripts\\run_local.ps1 once first."
}

if ($Proxy) {
  $env:HTTP_PROXY = $Proxy
  $env:HTTPS_PROXY = $Proxy
}

@"
import sys
import urllib.request

url = sys.argv[1]
req = urllib.request.Request(url, headers={"User-Agent": "recruit-tracker/0.1"})
with urllib.request.urlopen(req, timeout=20) as resp:
    print("status=", resp.status)
    data = resp.read(200)
    print("bytes=", len(data))
"@ | & $py - $Url
