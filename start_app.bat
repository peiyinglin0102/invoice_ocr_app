@echo off
echo ===========================================
echo 啟動：多國發票辨識與自動理財系統
echo ===========================================

:: 建立虛擬環境
if not exist "venv\Scripts\activate.bat" (
    echo 初始化虛擬環境 (Python venv)...
    python -m venv venv
)

:: 啟動虛擬環境
call venv\Scripts\activate.bat

:: 安裝套件
echo 正在檢查並安裝需求套件 (只需下載一次，請耐心等候)...
pip install -r requirements.txt

:: 執行 Streamlit App
echo.
echo ===========================================
echo 正在啟動 Web App...
echo ===========================================
streamlit run app.py
pause
