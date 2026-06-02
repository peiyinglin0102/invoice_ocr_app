@echo off
chcp 65001 > nul
echo ===========================================
echo  AI 智能外幣發票理財系統 — 啟動腳本
echo ===========================================
echo.

cd /d "%~dp0"

REM ─── Backend ───────────────────────────────
echo [1/2] 正在啟動 FastAPI 後端 (Port: 8000)...
if not exist "venv\Scripts\activate.bat" (
    echo 初始化 Python 虛擬環境...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo 安裝後端套件（首次執行較久）...
pip install -r requirements.txt --quiet
start "FastAPI Backend" cmd /k "cd /d %~dp0 && call venv\Scripts\activate.bat && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

echo 等待後端啟動...
timeout /t 4 /nobreak > nul

REM ─── Frontend ──────────────────────────────
echo [2/2] 正在啟動 React 前端 (Port: 3000)...
cd frontend
if not exist "node_modules" (
    echo 安裝前端套件（首次執行較久）...
    npm install
)
start "React Frontend" cmd /k "npm run dev"

cd ..

echo.
echo ===========================================
echo  服務啟動完成！
echo  前端: http://localhost:3000
echo  後端: http://localhost:8000
echo  後端 API 文件: http://localhost:8000/docs
echo ===========================================
echo.
pause
