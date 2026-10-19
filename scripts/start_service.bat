@echo off
rem ================================================
rem  KnowledgeNet 开机自启：启动 Nebula(WSL1) + 后端
rem ================================================
setlocal

set PROJ=C:\Users\x30085681\Desktop\up_X\AI4KnowledgeNet
set PY=C:\Users\x30085681\Desktop\up_X\驱制一体\液冷高速端制动\ai-knowledge-base\venv\Scripts\python.exe

echo [1/3] 启动 NebulaGraph (WSL1)...
wsl -d Ubuntu -u root -- bash /mnt/c/Users/x30085681/Desktop/up_X/AI4KnowledgeNet/scripts/start_nebula_wsl1.sh

echo [2/3] 等待 Nebula 就绪...
timeout /t 20 /nobreak >nul

echo [3/3] 启动后端 uvicorn (仅当 8000 未占用)...
netstat -ano | findstr ":8000 .*LISTENING" >nul
if %errorlevel%==0 (
  echo 端口 8000 已被占用，跳过后端启动。
) else (
  pushd "%PROJ%"
  start "KnowledgeNet-Backend" /b "%PY%" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
  popd
  echo 后端已启动 (端口 8000)。
)

echo 完成。可访问 http://127.0.0.1:8000
endlocal
