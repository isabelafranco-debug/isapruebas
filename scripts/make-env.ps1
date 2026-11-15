$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$target=Join-Path $root '.env'
if(Test-Path -LiteralPath $target){throw 'Ya existe .env. Conserva la contraseña que usa tu volumen.'}
$secret=python -c "import secrets; print(secrets.token_hex(28))"
if($LASTEXITCODE -ne 0 -or $secret -notmatch '^[a-f0-9]{56}$'){throw 'No se pudo generar el secreto.'}
$template=Get-Content -Raw -LiteralPath (Join-Path $root '.env.example')
$template.Replace('POSTGRES_PASSWORD=',"POSTGRES_PASSWORD=$secret") | Set-Content -Encoding ascii -LiteralPath $target
Write-Host '.env creado para Compose.'
