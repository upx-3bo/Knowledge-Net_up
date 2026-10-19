@echo off
REM ============================================================
REM AI4KnowledgeNet 新版统一启动脚本（服务端口 8001）
REM 用法：双击运行，或在命令行执行 run.bat
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/3] 检查本地 Python 依赖环境 (venv\Scripts\python.exe) ...
if not exist "venv\Scripts\python.exe" (
    echo [错误] 未找到 venv。请先执行 setup.bat 或把 venv 放到本项目目录。
    pause
    exit /b 1
)

echo [2/3] 拼装前端第三方库（vendor/parts -> 完整 js，缺失时）...
venv\Scripts\python.exe scripts\assemble_vendor.py

echo [3/3] 启动后端服务：http://127.0.0.1:8001  （局域网: http://<本机IP>:8001）
echo 按 Ctrl+C 停止。
venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --log-level info

endlocal
