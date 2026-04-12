@echo off
chcp 65001 > nul
title Matthew Actionables
echo.
echo ============================================================
echo   MATTHEW ACTIONABLES
echo   Pulling live Canvas data...
echo ============================================================
echo.

cd /d "%~dp0"

python3 pull_actionables.py matthew

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Something went wrong. Press any key to close.
    pause
    exit /b 1
)

echo.
echo Opening in browser...

for %%f in (Matthew_Actionables_*.html) do set LATEST=%%f

if defined LATEST (
    start "" "%LATEST%"
) else (
    echo Could not find HTML file.
    pause
)

echo.
echo Done! Press any key to close this window.
pause
