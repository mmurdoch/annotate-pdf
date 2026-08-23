param(
    [switch]$InstallDeps
)

if ($InstallDeps) {
    $pipScope = @("--user")
    if ($env:VIRTUAL_ENV) {
        $pipScope = @()
    }
    Write-Host "Installing dev dependencies..."
    python -m pip install @pipScope --upgrade pip
    python -m pip install @pipScope -r requirements.txt flake8 pylint black pytest pyright
}

$errors = $false

Write-Host "Running black (check mode)..."
python -m black --check .
if ($LASTEXITCODE -ne 0) { $errors = $true }

Write-Host "Running pyright..."
python -m pyright --warnings .
if ($LASTEXITCODE -ne 0) { $errors = $true }

Write-Host "Running flake8..."
python -m flake8 --max-line-length=120 --exclude=.venv .
if ($LASTEXITCODE -ne 0) { $errors = $true }

Write-Host "Running pylint..."
python -m pylint --init-hook="import sys; sys.path.insert(0, '.')" src/cli.py src/pdf_utils.py src/web_ui.py examples/annotate_example.py --score=no
if ($LASTEXITCODE -ne 0) { $errors = $true }

if (Test-Path "./test") {
    Write-Host "Running pytest..."
    python -m pytest -q -W error
    if ($LASTEXITCODE -ne 0) { $errors = $true }
} else {
    Write-Host 'No tests found in ./test - skipping pytest.'
}

if ($errors) {
    Write-Host "Build failed: one or more tools reported issues." -ForegroundColor Red
    exit 1
} else {
    Write-Host "Build succeeded." -ForegroundColor Green
    exit 0
}
