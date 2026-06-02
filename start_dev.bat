@echo off
echo ===========================================
echo 啟動：多國發票辨識系統 (前後端分離架構)
echo ===========================================

cd /d "%~dp0"

echo 正在啟動 Backend...
cd backend
if not exist "venv\Scripts\activate.bat" (
    echo 初始化後端虛擬環境...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo 檢查並安裝後端依賴...
pip install -r requirements.txt > nul 2>&1
echo 啟動 FastAPI 伺服器 (Port: 8000)...
start "Backend API" cmd /k "call venv\Scripts\activate.bat & uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

cd ..

echo 正在啟動 Frontend...
cd frontend
echo 檢查並安裝前端依賴 (第一次可能需要幾分鐘)...
call npm install --silent > nul 2>&1
echo 啟動 React (Vite) 伺服器 (Port: 5173)...
start "Frontend Web" cmd /k "npm run dev"

echo ===========================================
echo 服務啟動完成！
echo 前端網頁將在瀏覽器中開啟: http://localhost:5173/
echo 後端 API 位於: http://localhost:8000/
echo ===========================================
pause
