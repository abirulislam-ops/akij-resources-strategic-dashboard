@echo off
echo ========================================
echo   Akij Resources Strategic Planning
echo          Dashboard Launcher
echo ========================================
echo.
echo Starting dashboard...
echo Browser will open automatically at http://localhost:8501
echo.
echo Press Ctrl+C to stop the dashboard
echo.
cd /d "%~dp0"
python -m streamlit run app.py --server.port 8501 --server.headless false
pause