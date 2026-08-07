@echo off
chcp 65001 > nul
echo ========================================
echo  启动 AI 知识库系统
echo ========================================
echo.

REM 尝试 Docker 模式
docker --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [模式] Docker 容器模式
    echo 启动 NebulaGraph + 后端 + 前端...
    docker compose up -d
    echo.
    echo 访问地址:
    echo   图谱可视化: http://localhost:7001
    echo   后端 API:   http://localhost:8000/docs
    echo   前端界面:   http://localhost:8501
    echo.
    goto :end
)

REM 本地模式
echo [模式] 本地 Python 模式
call venv\Scripts\activate.bat

echo 启动后端 API (端口 8000)...
start "KB-Backend" cmd /c "call venv\Scripts\activate.bat && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

echo 启动前端 (端口 8501)...
start "KB-Frontend" cmd /c "call venv\Scripts\activate.bat && streamlit run frontend/app.py --server.port=8501"

echo.
echo 访问地址:
echo   后端 API:   http://localhost:8000/docs
echo   前端界面:   http://localhost:8501
echo.

:end
echo 按任意键退出...
pause >nul
taskkill /f /im cmd.exe /fi "WINDOWTITLE eq KB-*" >nul 2>&1
