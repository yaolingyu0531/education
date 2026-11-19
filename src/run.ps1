# 启动脚本：首次运行自动准备环境、装依赖、构建索引（自带 Python 运行时，无需外部安装）
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvPy = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPy)) {
    Write-Host '[1/4] 准备 Python 运行时…' -ForegroundColor Cyan
    $basePy = Join-Path $root 'runtime\python\python.exe'
    if (-not (Test-Path $basePy)) {
        $sysPy = Get-Command python -ErrorAction SilentlyContinue
        if (-not $sysPy) { throw '找不到 Python：既没有 runtime\python，也没有系统 python' }
        $basePy = $sysPy.Source
    }
    & $basePy -m venv .venv
    if (-not (Test-Path $venvPy)) { throw '创建虚拟环境失败' }
    Write-Host '[2/4] 安装依赖…' -ForegroundColor Cyan
    & $venvPy -m pip install --disable-pip-version-check -q -r requirements.txt
}

if (-not (Test-Path 'data\runtime\index.json')) {
    Write-Host '[3/4] 构建知识库索引与图谱…' -ForegroundColor Cyan
    & $venvPy 'scripts\build_index.py'
}

$port = if ($args.Count -ge 1) { $args[0] } else { '8010' }
Write-Host '[4/4] 启动服务' -ForegroundColor Cyan
Write-Host ''
Write-Host "  地址： http://127.0.0.1:$port" -ForegroundColor Green
Write-Host '  账号： teacher/teacher123 · reviewer/review123 · coordinator/coord123 · admin/admin123 · student/student123' -ForegroundColor DarkGray
Write-Host ''
Start-Process "http://127.0.0.1:$port"
& $venvPy -m uvicorn app.main:app --host 127.0.0.1 --port $port
