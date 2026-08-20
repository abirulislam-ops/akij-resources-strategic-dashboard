@echo off
echo ========================================
echo   Akij Resources - Strategic Planning
echo          Dashboard Launcher
echo ========================================
echo.
echo Starting dashboard...
echo Browser will open at http://localhost:8501
echo.
echo Press Ctrl+C in this window to stop.
echo.
cd /d "%~dp0dashboard"
python -m streamlit run app.py --server.port 8501 --server.headless false
pause