$ProjectRoot = Split-Path -Parent $PSScriptRoot
$NodeDirectory = Join-Path $env:ProgramFiles 'nodejs'
if (Test-Path -LiteralPath (Join-Path $NodeDirectory 'node.exe')) {
    $env:PATH = "$NodeDirectory;$env:PATH"
}
$env:DATABASE_URL = 'postgresql+psycopg://postgres@127.0.0.1:55433/postgres?sslmode=disable'
$env:PSYCOPG_IMPL = 'python'
$env:PATH = "$ProjectRoot/.local/pgsql/bin;$env:PATH"
$env:JUPITER_WINDOWS_PORTABLE = '1'
$env:PLAYWRIGHT_CHANNEL = 'msedge'
$env:BROWSER_PATH = "${env:ProgramFiles(x86)}/Microsoft/Edge/Application/msedge.exe"
$env:APP_ORIGINS = 'http://localhost:8080,http://127.0.0.1:8080,http://127.0.0.1:5173,http://localhost:5173'
$env:SERVE_WEB = '1'
$Python = "$ProjectRoot/.local/py312/python.exe"
