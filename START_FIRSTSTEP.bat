@echo off
cd /d "%~dp0"
if not exist .env (
 echo MISSING .env - copy .env.example and fill in credentials.
 pause
 exit /b 1
)
if not exist .venv py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python app.py
pause
