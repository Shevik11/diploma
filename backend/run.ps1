# Start the FastAPI backend (Windows)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Create virtual environment if not exists
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

# Activate virtual environment
& .\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the server
Write-Host "Starting FastAPI backend on http://localhost:8000"
python main.py
