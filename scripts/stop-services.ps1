[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 停止 cloudflared 隧道进程
$cf = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($cf) {
    Write-Host "[已停止] Cloudflare Tunnel 进程 (PID: $($cf.Id -join ', '))" -ForegroundColor Yellow
    $cf | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 停止监听端口 3000 和 8000 的进程
$ports = @(3000, 8000)
foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($connections) {
        $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $pids) {
            $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "[已停止] 端口 $port 上的进程: $($proc.ProcessName) (PID: $p)" -ForegroundColor Yellow
                Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            }
        }
    } else {
        Write-Host "[空闲] 端口 $port 当前未在监听" -ForegroundColor Green
    }
}