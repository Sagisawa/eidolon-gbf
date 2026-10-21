$Host.UI.RawUI.WindowTitle = "Eidolon-GBF 启动器"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "             Eidolon-GBF 一键启动器" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $PSScriptRoot
Set-Location $rootDir

# 0. 自动清理可能残留的旧进程，防止端口冲突
Write-Host "正在检测并清理旧端口占用 (3000 / 8000)..." -ForegroundColor Gray
& (Join-Path $PSScriptRoot "stop-services.ps1")
Start-Sleep -Milliseconds 800
Write-Host ""

# 1. 检查后端虚拟环境
$backendExe = Join-Path $rootDir ".venv\Scripts\eidolon.exe"
if (-not (Test-Path $backendExe)) {
    Write-Host "[错误] 未找到后端环境: $backendExe" -ForegroundColor Red
    Write-Host "请确认已创建虚拟环境并安装后端依赖。"
    Write-Host ""
    Read-Host "按 Enter 键退出..."
    exit 1
}

# 2. 检查前端依赖与构建
$frontendDir = Join-Path $rootDir "frontend"
$nodeModules = Join-Path $frontendDir "node_modules"
$nextBuild = Join-Path $frontendDir ".next"

if (-not (Test-Path $nodeModules)) {
    Write-Host "[提示] 正在安装前端依赖 (npm install)..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm install
    Pop-Location
}

if (-not (Test-Path $nextBuild)) {
    Write-Host "[提示] 前端尚未构建，正在执行构建 (npm run build)..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm run build
    Pop-Location
}

# 3. 启动后端 (端口 8000)
Write-Host "[1/2] 正在启动后端服务 (FastAPI :8000)..." -ForegroundColor Green
Start-Process cmd.exe -ArgumentList "/k", "`"$backendExe`" serve" -WorkingDirectory $rootDir

# 4. 启动前端 (端口 3000)
Write-Host "[2/2] 正在启动前端服务 (Next.js :3000)..." -ForegroundColor Green
Start-Process cmd.exe -ArgumentList "/k", "npm run start" -WorkingDirectory $frontendDir

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "服务正在启动中，3 秒后将自动在浏览器中打开主页..." -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Start-Sleep -Seconds 3

Start-Process "http://127.0.0.1:3000"

Write-Host ""
Write-Host "前后端已分别在独立窗口中启动！" -ForegroundColor Green
Write-Host "如需关闭服务，可直接关闭对应的窗口，或双击运行 stop.bat。" -ForegroundColor Yellow
Write-Host ""
Read-Host "按 Enter 键关闭本启动窗口 (服务将继续在后台运行)..."
