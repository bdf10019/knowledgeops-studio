[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$NodeExecutable = "node"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    & $PythonExecutable -m pip check
    if ($LASTEXITCODE -ne 0) { throw "pip dependency check failed." }
    & $PythonExecutable -m compileall -q backend
    if ($LASTEXITCODE -ne 0) { throw "Python compilation failed." }
    & $PythonExecutable -m ruff check backend tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }
    & $PythonExecutable -m mypy backend
    if ($LASTEXITCODE -ne 0) { throw "Mypy failed." }
    & $PythonExecutable -m pytest --cov=knowledge_ops --cov-report=term-missing
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }

    Push-Location frontend
    try {
        & $NodeExecutable node_modules/typescript/bin/tsc -b --pretty false
        if ($LASTEXITCODE -ne 0) { throw "Frontend typecheck failed." }
        & $NodeExecutable node_modules/vitest/vitest.mjs run
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
        & $NodeExecutable node_modules/vite/bin/vite.js build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    }
    finally { Pop-Location }

    & $PythonExecutable -m knowledge_ops doctor
    if ($LASTEXITCODE -ne 0) { throw "Runtime diagnostics failed." }
    & (Join-Path $PSScriptRoot "privacy-check.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Privacy check failed." }
    Write-Host "All verification stages passed."
}
finally {
    Pop-Location
}
