@echo off
echo ===========================================
echo Starting AI Invoice App...
echo ===========================================

if not exist "venv\Scripts\activate.bat" (
    echo Initializing virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing requirements...
pip install -r requirements.txt

echo.
echo ===========================================
echo Starting Web App...
echo ===========================================
streamlit run app.py
pause
