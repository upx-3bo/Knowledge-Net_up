@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

echo ============================================
echo  AI4KnowledgeNet 后端重启脚本
echo  步骤：停旧服务 - 等待端口释放 - 启动新服务 - 自检
echo ============================================

echo [1/4] 停掉占用 8000 的旧服务 ...
set "KILLED="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1 && set "KILLED=%%a"
    if defined KILLED echo   已终止 PID !KILLED!
)

echo [2/4] 等待端口释放 ...
set /a TRY=0
:waitloop
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 goto portfree
set /a TRY+=1
if !TRY! geq 30 (
    echo   警告：端口 30 秒内仍未释放，可能还有残留进程。
    echo   请关闭旧后端窗口/任务管理器结束占用 8000 的进程后，再次运行本脚本。
    goto :eof
)
timeout /t 2 /nobreak >nul
goto waitloop
:portfree
echo   端口已空闲

echo [3/4] 启动新后端 (venv python + uvicorn) ...
set PYTHONPATH=C:\Users\x30085681\Desktop\up_X\AI4KnowledgeNet
start "AI4KnowledgeNet-API" "C:\Users\x30085681\Desktop\up_X\驱制一体\液冷高速端制动\ai-knowledge-base\venv\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

echo [4/4] 自检（8 秒超时）...
timeout /t 6 /nobreak >nul
powershell -NoProfile -Command "try{$r=Invoke-RestMethod 'http://127.0.0.1:8000/review/pending' -TimeoutSec 8; Write-Host ('OK  待校核=' + $r.count + ' 基线=' + $r.checkpoint)}catch{Write-Host ('FAIL ' + $_.Exception.Message)}"
powershell -NoProfile -Command "try{$m=Invoke-RestMethod 'http://127.0.0.1:8000/meta/schema' -TimeoutSec 8; Write-Host ('OK  architecture=' + ($m.architecture -ne $null))}catch{Write-Host ('FAIL ' + $_.Exception.Message)}"

echo.
echo 完成。若两条均为 OK，浏览器硬刷新(Ctrl+Shift+R)即可使用「安全校核」。
pause
