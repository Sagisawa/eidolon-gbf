# Eidolon-GBF 一键启动器 (含 Cloudflare 免费公网隧道)
$Host.UI.RawUI.WindowTitle = "Eidolon-GBF (带 Cloudflare 隧道)"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "   Eidolon-GBF 一键启动器 (本地模型 + Cloudflare 隧道)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $PSScriptRoot
Set-Location $rootDir

# 0. 清理旧进程与端口
Write-Host "[1/5] 清理旧进程与端口占用..." -ForegroundColor Gray
& (Join-Path $PSScriptRoot "stop-services.ps1")
Start-Sleep -Milliseconds 600

# 1. 检查后端
$venvDir = Join-Path $rootDir ".venv"
$backendExe = Join-Path $venvDir "Scripts\eidolon.exe"
if (-not (Test-Path $backendExe)) {
    Write-Host "[错误] 未检测到后端环境: $backendExe，请先运行 start.bat 完成初始化安装。" -ForegroundColor Red
    pause
    exit 1
}

# 2. 检查 cloudflared 工具
$cloudflaredExe = Join-Path $rootDir "tools\cloudflared.exe"
if (-not (Test-Path $cloudflaredExe)) {
    Write-Host "[错误] 未检测到 $cloudflaredExe" -ForegroundColor Red
    pause
    exit 1
}

# 3. 启动后端 (FastAPI :8000)
Write-Host "[2/5] 正在启动后端服务 (FastAPI :8000)..." -ForegroundColor Green
Start-Process cmd.exe -ArgumentList "/k", "`"$backendExe`" serve" -WorkingDirectory $rootDir

# 4. 启动前端 (Next.js :3000)
$frontendDir = Join-Path $rootDir "frontend"
Write-Host "[3/5] 正在启动前端服务 (Next.js :3000)..." -ForegroundColor Green
Start-Process cmd.exe -ArgumentList "/k", "npm run start" -WorkingDirectory $frontendDir

# 5. 等待前端与后端就绪
Write-Host "[4/5] 等待本地服务就绪..." -ForegroundColor Gray
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    $conn = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        $ready = $true
        break
    }
}

if (-not $ready) {
    Write-Host "[警告] 前端启动耗时稍长，继续启动 Cloudflare 隧道..." -ForegroundColor Yellow
} else {
    Write-Host "[成功] 本地服务已就绪！" -ForegroundColor Green
}

# 6. 启动 Cloudflare 免费临时隧道
Write-Host "[5/5] 正在启动 Cloudflare 临时隧道 (Quick Tunnel)..." -ForegroundColor Cyan
Write-Host ""
Write-Host "=================================================================" -ForegroundColor Yellow
Write-Host "提示：Cloudflare 会在弹出的专门窗口中打印您的公网专属临时链接：" -ForegroundColor Yellow
Write-Host "形如：https://xxxx-xxxx-xxxx.trycloudflare.com" -ForegroundColor Cyan
Write-Host "您可以在手机或外网浏览器中直接打开该链接访问！" -ForegroundColor Yellow
Write-Host "如需随时下线，直接关闭该窗口或双击运行 stop.bat 即可。" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Yellow
Write-Host ""

Start-Process cmd.exe -ArgumentList "/k", "`"$cloudflaredExe`" tunnel --url http://127.0.0.1:3000" -WorkingDirectory $rootDir

# 同时打开本地浏览器
Start-Process "http://127.0.0.1:3000"