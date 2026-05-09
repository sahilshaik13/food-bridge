Write-Host "🚀 Starting FoodBridge Stack..." -ForegroundColor Cyan

function Stop-PortProcess {
    param([int]$Port)
    $pidToKill = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
    if ($pidToKill) {
        Write-Host "Cleaning up port $Port (PID: $pidToKill)..." -ForegroundColor Gray
        Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
    }
}

# 1. Cleanup
Stop-PortProcess 8000
Stop-PortProcess 3000

# 2. Start Backend with Auto-Reload
# Uvicorn --reload watches for .py changes
Write-Host "Starting Backend on http://localhost:8000 (Auto-Reload active)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

# 3. Start Frontend with HMR
# Next.js dev watches for .tsx, .ts, .css changes and reloads browser
Write-Host "Starting Frontend on http://localhost:3000 (Hot Module Replacement active)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "pnpm dev"

Write-Host "✅ Services are active and watching for changes." -ForegroundColor Cyan
Write-Host "Backend: Watches backend/*.py" -ForegroundColor Gray
Write-Host "Frontend: Watches frontend/src/**/* and app/**/*" -ForegroundColor Gray
