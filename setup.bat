@echo off
chcp 65001 > nul
echo ========================================
echo   AI 知识库 - 驱制一体/角模块 搭建脚本
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [失败] 未找到 Python，请安装 Python 3.11+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python 已安装

REM 检查 Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 未找到 Docker，将使用本地模式运行
    set LOCAL_MODE=1
) else (
    echo [OK] Docker 已安装
    set LOCAL_MODE=0
)

echo.
echo 正在创建虚拟环境...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo 正在安装依赖...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo ========================================
echo  安装完成！请运行 run.bat 启动系统
echo ========================================
pause
