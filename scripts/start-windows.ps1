[CmdletBinding()]
param([switch]$Rebuild)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/dev-env.ps1"
Push-Location $ProjectRoot

function Run-Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Falló un comando de preparación. Código $LASTEXITCODE." }
}

function Fetch([string]$Url, [string]$Path) {
    if (!(Test-Path -LiteralPath $Path)) {
        Run-Checked { curl.exe --fail --location --silent --show-error --retry 2 $Url -o "$Path.part" }
        Move-Item -LiteralPath "$Path.part" -Destination $Path
    }
}

function Listening([int]$Port) {
    $client=[Net.Sockets.TcpClient]::new()
    try { $client.Connect('127.0.0.1',$Port); return $true }
    catch { return $false }
    finally { $client.Dispose() }
}

function Start-Local([string]$Exe,[string]$Arguments,[string]$Working,[string]$Name) {
    $proc = Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory $Working -WindowStyle Hidden -PassThru `
       -RedirectStandardOutput "$ProjectRoot/.local/$Name.out" -RedirectStandardError "$ProjectRoot/.local/$Name.err"
    $proc.Id | Set-Content -Encoding ascii "$ProjectRoot/.local/$Name.pid"
}

function Live-Pid([string]$Name) {
    $status="$ProjectRoot/.local/$Name.pid"
    if (!(Test-Path -LiteralPath $status)) {return $false}
    $idFromFile=[int](Get-Content -LiteralPath $status)
    $proc=Get-Process -Id $idFromFile -ErrorAction SilentlyContinue
    return ($null -ne $proc -and $proc.Path -eq $Python.Replace('/','\'))
}

try {
    if ((& node -p "typeof require('node:crypto').argon2Sync") -ne 'function') {throw 'El modo Windows requiere Node.js 24.7 o superior.'}
    if (!(Test-Path -LiteralPath $env:BROWSER_PATH)) {throw 'El modo Windows necesita Microsoft Edge para renderizar los informes.'}
    New-Item -ItemType Directory -Force .local, .local/py312, .local/pglite | Out-Null
    if (!(Test-Path -LiteralPath $Python)) {
        Fetch 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' '.local/python-embed.zip'
        Expand-Archive -LiteralPath .local/python-embed.zip -DestinationPath .local/py312 -Force
    }
    if (!(Test-Path .local/pgsql/bin/libpq.dll)) {
        Fetch 'https://get.enterprisedb.com/postgresql/postgresql-16.14-1-windows-x64-binaries.zip' '.local/postgresql.zip'
        Run-Checked { tar -xf .local/postgresql.zip -C .local pgsql/bin }
    }
    @('python312.zip','.','../../.venv/Lib/site-packages','../../backend','../../tests','import site') | Set-Content -Encoding ascii .local/py312/python312._pth
    if (!(Test-Path .venv/Lib/site-packages/fastapi) -or $Rebuild) {
        & python -m uv --version *> $null
        if ($LASTEXITCODE -ne 0) { Run-Checked { python -m pip install --user uv } }
        Run-Checked { python -m uv sync --locked --python 3.12 }
    }
    if (!(Test-Path web/dist/index.html) -or $Rebuild) {
        Run-Checked { npm --prefix web ci --no-audit --no-fund }
        Run-Checked { npm --prefix web run build }
    }
    if (!(Test-Path .local/pglite/node_modules/@electric-sql/pglite)) {
        Copy-Item -LiteralPath scripts/windows-db-package.json -Destination .local/pglite/package.json
        Copy-Item -LiteralPath scripts/windows-db-package-lock.json -Destination .local/pglite/package-lock.json
        Run-Checked { npm --prefix .local/pglite ci --no-audit --no-fund }
    }
    if (!(Listening 55433)) {
        Copy-Item -LiteralPath scripts/windows-db.mjs -Destination .local/pglite/db.mjs -Force
        Start-Local (Get-Command node.exe).Source 'db.mjs' "$ProjectRoot/.local/pglite" 'pglite'
        for($i=0;$i -lt 90 -and !(Listening 55433);$i++){Start-Sleep -Milliseconds 500}
        if (!(Listening 55433)) {throw 'La base local no arrancó. Consulta .local/pglite.err.'}
    }
    if (!(Listening 8080)) {
        Run-Checked { & $Python -m alembic -c backend/alembic.ini upgrade head }
        Run-Checked { & $Python -m jupiter.seed }
        Start-Local $Python '-m uvicorn jupiter.api:app --host 127.0.0.1 --port 8080 --no-access-log' $ProjectRoot 'api'
    }
    if (!(Live-Pid 'worker')) {Start-Local $Python '-m jupiter.worker' $ProjectRoot 'worker'}
    $healthy=$false
    for($i=0;$i -lt 20 -and !$healthy;$i++){
        try {$healthy=(Invoke-RestMethod 'http://127.0.0.1:8080/api/health' -TimeoutSec 2).status -eq 'ok'} catch {Start-Sleep -Milliseconds 500}
    }
    if (!$healthy) {throw 'La API no pasó el chequeo de salud. Consulta .local/api.err.'}
    Write-Host 'Júpiter Jr disponible en http://localhost:8080'
} finally {Pop-Location}
