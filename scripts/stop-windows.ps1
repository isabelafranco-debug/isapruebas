$root=Split-Path -Parent $PSScriptRoot
$patterns=@{api='jupiter\.api:app';worker='jupiter\.worker';pglite='db\.mjs'}
foreach($name in @('worker','api','pglite')){
    $pidFile="$root/.local/$name.pid"
    if (!(Test-Path -LiteralPath $pidFile)) {continue}
    $expectedId=[int](Get-Content -LiteralPath $pidFile)
    $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$expectedId" -ErrorAction SilentlyContinue
    if($proc -and $proc.CommandLine -match $patterns[$name]){
        Stop-Process -Id $expectedId -ErrorAction Stop
        Wait-Process -Id $expectedId -Timeout 8 -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile
}
