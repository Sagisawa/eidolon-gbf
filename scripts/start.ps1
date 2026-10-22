# Eidolon-GBF 一键启动器
$Host.UI.RawUI.WindowTitle = "Eidolon-GBF 启动器"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "             Eidolon-GBF 一键启动器" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $PSScriptRoot
Set-Location $rootDir

# 0. 清理端口占用
Write-Host "[1/4] 检查端口占用 (3000 / 8000)..." -ForegroundColor Gray
& (Join-Path $PSScriptRoot "stop-services.ps1")
Start-Sleep -Milliseconds 600

# 0.1 检查 .env
$envFile = Join-Path $rootDir ".env"
$envExample = Join-Path $rootDir ".env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Write-Host "[提示] 未检测到 .env，已自动从 .env.example 复制创建。" -ForegroundColor Yellow
        $exampleText = [System.IO.File]::ReadAllText($envExample, [System.Text.Encoding]::UTF8)
        $exampleText = $exampleText -replace '(?m)^EIDOLON_DEV_LOGIN=.*$', 'EIDOLON_DEV_LOGIN=1'
        [System.IO.File]::WriteAllText($envFile, $exampleText, [System.Text.Encoding]::UTF8)
        Write-Host "[提示] 已为您默认开启 EIDOLON_DEV_LOGIN=1（本地快速登录模式）。" -ForegroundColor Green
        Write-Host "[注意] 请在启动后打开 .env 填写您的模型 API Key！" -ForegroundColor Magenta
        Write-Host ""
    }
}

if (Test-Path $envFile) {
    $currentEnv = [System.IO.File]::ReadAllText($envFile, [System.Text.Encoding]::UTF8)
    if ($currentEnv -match "(?m)^CHAT_LLM_API_KEY=\s*$" -or -not ($currentEnv -match "(?m)^CHAT_LLM_API_KEY=\S+")) {
        Write-Host "=========================================================" -ForegroundColor Yellow
        Write-Host "[提醒] 检测到 .env 中的 CHAT_LLM_API_KEY 尚未填写！" -ForegroundColor Yellow
        Write-Host "系统可启动前端界面，但对话需要有效模型密钥才能响应。" -ForegroundColor Gray
        Write-Host "请记得用记事本或编辑器打开 .env 填写 CHAT_LLM_API_KEY。" -ForegroundColor Gray
        Write-Host "=========================================================" -ForegroundColor Yellow
        Write-Host ""
    }
}

# 1. 检查后端 Python 虚拟环境与依赖
$venvDir = Join-Path $rootDir ".venv"
$backendExe = Join-Path $venvDir "Scripts\eidolon.exe"
if (-not (Test-Path $backendExe)) {
    Write-Host "[2/4] 首次运行，正在自动配置后端环境..." -ForegroundColor Yellow
    if (-not (Test-Path $venvDir)) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCmd) {
            Write-Host "[错误] 未检测到系统的 Python，请先安装 Python (>= 3.11) 并勾选加入 PATH。" -ForegroundColor Red
            Read-Host "按 Enter 键退出..."
            exit 1
        }
        Write-Host "正在创建 Python 虚拟环境 (.venv)..." -ForegroundColor Gray
        python -m venv $venvDir
    }

    $pipExe = Join-Path $venvDir "Scripts\pip.exe"
    if (Test-Path $pipExe) {
        Write-Host "正在安装后端依赖 (pip install -e backend)..." -ForegroundColor Gray
        & $pipExe install -e (Join-Path $rootDir "backend")
    }

    if (-not (Test-Path $backendExe)) {
        Write-Host "[错误] 后端依赖安装未能生成: $backendExe" -ForegroundColor Red
        Read-Host "按 Enter 键退出..."
        exit 1
    }
    Write-Host "[成功] 后端环境配置完成！" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "[2/4] 后端虚拟环境检查通过。" -ForegroundColor Gray
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
    Write-Host "[3/4] 正在安装前端依赖 (npm install)..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm install
    Pop-Location
} else {
    Write-Host "[3/4] 前端 node_modules 检查通过。" -ForegroundColor Gray
}

$needsBuild = -not (Test-Path $nextBuild)
if (-not $needsBuild) {
    $buildTime = (Get-Item $nextBuild).LastWriteTime
    $srcDir = Join-Path $frontendDir "src"
    if (Test-Path $srcDir) {
        $newer = Get-ChildItem -Path $srcDir -Recurse -File | Where-Object { $_.LastWriteTime -gt $buildTime } | Select-Object -First 1
        if ($newer) {
            Write-Host "[提示] 检测到前端源码变动，正在重新构建 (npm run build)..." -ForegroundColor Yellow
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
Write-Host "[4/4] 正在启动后端服务 (FastAPI :8000)..." -ForegroundColor Green
Start-Process cmd.exe -ArgumentList "/k", "`"$backendExe`" serve" -WorkingDirectory $rootDir

# 4. 启动前端 (端口 3000)
Write-Host "正在启动前端服务 (Next.js :3000)..." -ForegroundColor Green
Start-Process cmd.exe -ArgumentList "/k", "npm run start" -WorkingDirectory $frontendDir

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "服务已在独立窗口中启动，3 秒后自动打开浏览器..." -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Start-Sleep -Seconds 3

Start-Process "http://127.0.0.1:3000"

Write-Host ""
Write-Host "前后端已就绪！如需关闭服务，可双击运行 stop.bat。" -ForegroundColor Yellow
Write-Host ""
