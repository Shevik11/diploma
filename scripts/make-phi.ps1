param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    [string]$ContainerName = "ollama-phi",
    [int]$Port = 11437
)

# Preconfigured for Phi
$ModelName = "phi"

function Start-Container {
    $existing = docker ps -a --filter "name=$ContainerName" --format "{{.Names}}" 2>$null
    if ($existing -eq $ContainerName) {
        Write-Host "Container exists, starting..." -ForegroundColor Yellow
        docker start $ContainerName | Out-Null
    } else {
        Write-Host "[1/2] Starting Phi..." -ForegroundColor Cyan
        docker run -d --name $ContainerName -p "$Port`:11434" -v ollama-data:/root/.ollama ollama/ollama | Out-Null
    }
    Write-Host "[OK] Container started" -ForegroundColor Green
    Write-Host "[2/2] Waiting 10 seconds..." -ForegroundColor Cyan
    Start-Sleep 10
    Write-Host "[OK] Ready" -ForegroundColor Green
}

function Stop-Container {
    Write-Host "Stopping container..." -ForegroundColor Cyan
    docker stop $ContainerName 2>$null | Out-Null
    Write-Host "[OK] Stopped" -ForegroundColor Green
}

function Pull-OllamaModel {
    Write-Host "Pulling Phi..." -ForegroundColor Cyan
    docker exec $ContainerName ollama pull $ModelName
    Write-Host "[OK] Phi ready" -ForegroundColor Green
}

function Test-Quick {
    Write-Host "Quick test with Phi..." -ForegroundColor Cyan
    $body = '{"model":"' + $ModelName + '","prompt":"What is 2+2?","stream":false}'
    $response = Invoke-RestMethod -Uri "http://localhost:$Port/api/generate" -Method Post -ContentType "application/json" -Body $body
    Write-Host ""
    Write-Host $response.response -ForegroundColor White
    Write-Host ""
    Write-Host "[OK] Test complete" -ForegroundColor Green
}

function Test-Model {
    Start-Container
    Pull-OllamaModel
    Test-Quick
}

function Show-Status {
    Write-Host "`n=== Phi Status ===" -ForegroundColor Cyan
    $running = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>$null
    if ($running -eq $ContainerName) {
        Write-Host "[OK] Running" -ForegroundColor Green
        docker ps --filter "name=$ContainerName" --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}"
    } else {
        Write-Host "[X] Not running" -ForegroundColor Red
    }
}

function Clean-Container {
    Stop-Container
    Write-Host "Removing container..." -ForegroundColor Cyan
    docker rm $ContainerName 2>$null | Out-Null
    Write-Host "[OK] Removed" -ForegroundColor Green
}

function List-Models {
    Write-Host "`n=== Available Models ===" -ForegroundColor Cyan
    docker exec $ContainerName ollama list
}

function Show-Help {
    Write-Host "`n=== Phi 2.7B - PowerShell Script ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Configuration:" -ForegroundColor Yellow
    Write-Host "  Model: $ModelName"
    Write-Host "  Container: $ContainerName"
    Write-Host "  Port: $Port"
    Write-Host ""
    Write-Host "Available commands:" -ForegroundColor Yellow
    Write-Host "  help        - Show this help"
    Write-Host "  start       - Start container"
    Write-Host "  stop        - Stop container"
    Write-Host "  pull        - Pull Phi model"
    Write-Host "  test        - Full test (start + pull + test)"
    Write-Host "  test-quick  - Quick test (no pull)"
    Write-Host "  status      - Show container status"
    Write-Host "  logs        - Show container logs"
    Write-Host "  clean       - Stop and remove container"
    Write-Host "  list-models - Show available models"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\make.ps1 start"
    Write-Host "  .\make.ps1 test"
    Write-Host "  .\make.ps1 test-quick"
    Write-Host ""
}

# Main command router
switch ($Command.ToLower()) {
    "start" { Start-Container }
    "stop" { Stop-Container }
    "pull" { Start-Container; Pull-OllamaModel }
    "test" { Test-Model }
    "test-quick" { Test-Quick }
    "status" { Show-Status }
    "logs" { docker logs $ContainerName }
    "clean" { Clean-Container }
    "list-models" { List-Models }
    "help" { Show-Help }
    default { 
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
    }
}
