@echo off
REM ============================================================
REM AI4KnowledgeNet 初始化脚本（首次/重建 Python 依赖环境）
REM 需要 Python 3.11+ 已安装。完成后用 run.bat 启动。
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/4] 创建虚拟环境 venv ...
if exist "venv\Scripts\python.exe" (
    echo venv 已存在，跳过创建。
) else (
    py -3.11 -m venv venv
    if errorlevel 1 (
        echo [错误] 创建 venv 失败，请确认已安装 Python 3.11。
        pause
        exit /b 1
    )
)

echo [2/4] 安装依赖 (requirements.txt) ...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络。
    pause
    exit /b 1
)

echo [3/4] 拼装前端第三方库（vendor/parts -> 完整 js）...
venv\Scripts\python.exe scripts\assemble_vendor.py

echo [4/4] 完成。请确认 .env 存在（复制 .env.example 或本机配置），然后运行 run.bat 启动。
pause
endlocal
