$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$scriptPath = Join-Path $PSScriptRoot 'apollo_gemma.py'
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Python script not found: $scriptPath"
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = 'py'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = 'python'
} else {
    throw 'Python is not installed or is not on PATH.'
}

& $pythonCommand -c 'import openai' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $pythonCommand -m pip install openai
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install openai.'
    }
}

& $pythonCommand -u $scriptPath
exit $LASTEXITCODE
