[CmdletBinding()]
param([switch]$Recovery)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/dev-env.ps1"
Push-Location $ProjectRoot

function Run-Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Verification failed with exit code $LASTEXITCODE."
    }
}

try {
    & "$PSScriptRoot/start-windows.ps1"
    Run-Checked { npm.cmd --prefix web run build }
    Run-Checked { & $Python -X utf8 -m compileall -q backend scripts tests }
    Run-Checked { & $Python -X utf8 -m pytest -q }
    Run-Checked { & $Python -X utf8 tests/acceptance.py --channel msedge }
    if ($Recovery) {
        Run-Checked { & $Python -X utf8 tests/recovery.py --windows-worker }
    }
    $health = Invoke-RestMethod 'http://localhost:8080/api/health' -TimeoutSec 5
    if ($health.status -ne 'ok') {
        throw 'The application health check failed.'
    }
    Write-Host 'Verification completed. http://localhost:8080'
} finally {
    Pop-Location
}
