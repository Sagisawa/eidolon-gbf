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

# 0.1 检查配置文件 .env
$envFile = Join-Path $rootDir ".env"
$envExample = Join-Path $rootDir ".env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Write-Host "[提示] 未检测到 .env 配置文件，已为您自动从 .env.example 复制创建。" -ForegroundColor Yellow
        Copy-Item $envExample $envFile
        Write-Host "[注意] 请在启动后打开 .env 填写您的对话模型 API Key (如 CHAT_LLM_*)！" -ForegroundColor Magenta
        Write-Host ""
    }
}

# 1. 检查后端虚拟环境与依赖
$venvDir = Join-Path $rootDir ".venv"
$backendExe = Join-Path $venvDir "Scripts\eidolon.exe"
if (-not (Test-Path $backendExe)) {
    Write-Host "[提示] 检测到首次运行，正在自动配置后端环境..." -ForegroundColor Yellow
    if (-not (Test-Path $venvDir)) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCmd) {
            Write-Host "[错误] 未检测到系统的 Python，请先安装 Python (>= 3.11) 并勾选加入环境变量 PATH。" -ForegroundColor Red
            Read-Host "按 Enter 键退出..."
            exit 1
        }
        Write-Host "正在创建 Python 虚拟环境 (.venv)..." -ForegroundColor Gray
        python -m venv $venvDir
    }

    $pipExe = Join-Path $venvDir "Scripts\pip.exe"
    if (Test-Path $pipExe) {
        Write-Host "正在自动安装后端依赖 (pip install -e backend)..." -ForegroundColor Gray
        & $pipExe install -e (Join-Path $rootDir "backend")
    }

    if (-not (Test-Path $backendExe)) {
        Write-Host "[错误] 后端依赖安装未能成功生成: $backendExe" -ForegroundColor Red
        Write-Host "请检查网络或依赖报错信息。"
        Read-Host "按 Enter 键退出..."
        exit 1
    }
    Write-Host "[成功] 后端环境配置完成！" -ForegroundColor Green
    Write-Host ""
}

# 2. 检查前端依赖与构建
$frontendDir = Join-Path $rootDir "frontend"
$nodeModules = Join-Path $frontendDir "node_modules"
$nextBuild = Join-Path $frontendDir ".next"

$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    Write-Host "[错误] 未检测到系统的 Node.js / npm，请先安装 Node.js (>= 20)。" -ForegroundColor Red
    Read-Host "按 Enter 键退出..."
    exit 1
}

if (-not (Test-Path $nodeModules)) {
    Write-Host "[提示] 正在安装前端依赖 (npm install)..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm install
    Pop-Location
}

$needsBuild = -not (Test-Path $nextBuild)
if (-not $needsBuild) {
    $buildTime = (Get-Item $nextBuild).LastWriteTime
    $srcDir = Join-Path $frontendDir "src"
    if (Test-Path $srcDir) {
        $newer = Get-ChildItem -Path $srcDir -Recurse -File | Where-Object { $_.LastWriteTime -gt $buildTime } | Select-Object -First 1
        if ($newer) {
            Write-Host "[提示] 检测到前端代码有更新，正在重新构建 (npm run build)..." -ForegroundColor Yellow
            $needsBuild = $true
        }
    }
}

if ($needsBuild) {
    Write-Host "[提示] 正在执行前端构建 (npm run build)..." -ForegroundColor Yellow
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
