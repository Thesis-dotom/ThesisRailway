@echo off
echo Installing Thesis requirements...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Review the error above.
  pause
  exit /b 1
)
echo.
echo Starting Thesis...
python app.py
pause
