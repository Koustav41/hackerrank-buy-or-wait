@echo off
cd /d "%~dp0"
echo ===================================================
echo  Starting Buy or Wait FastAPI Backend
echo  URL: http://127.0.0.1:8000
echo ===================================================

if exist ".venv\Scripts\python.exe" (
    echo Using project virtual environment (.venv)...
    ".venv\Scripts\python.exe" backend\main.py
    goto end
)

if exist "%USERPROFILE%\AppData\Roaming\uv\python\cpython-3.14.4-windows-x86_64-none\python.exe" (
    echo Using local uv python installation...
    "%USERPROFILE%\AppData\Roaming\uv\python\cpython-3.14.4-windows-x86_64-none\python.exe" backend\main.py
    goto end
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo Using system python...
    python backend\main.py
    goto end
)

echo ERROR: Python executable was not found!
echo Please ensure .venv is created or Python is installed.
:end
pause
