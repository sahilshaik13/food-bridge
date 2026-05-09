$targets = Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -ne 3000 -and $_.LocalPort -ne 8000 }
foreach ($t in $targets) {
    try {
        $p = Get-Process -Id $t.OwningProcess -ErrorAction SilentlyContinue
        if ($p -and ($p.Name -match "node|python|uvicorn")) {
            Write-Host "Killing process $($p.Name) (PID: $($p.Id)) listening on port $($t.LocalPort)"
            Stop-Process -Id $p.Id -Force
        }
    } catch {
        Write-Host "Failed to kill PID $($t.OwningProcess)"
    }
}
