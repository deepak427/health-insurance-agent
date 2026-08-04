@echo off
REM Reset all agent data - sessions, artifacts, and logs
echo.
echo ========================================
echo   HIP Agent Data Reset
echo ========================================
echo.

REM Stop the agent if running
echo [1/3] Stopping agent if running...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

REM Delete sessions database
echo [2/3] Removing sessions database...
if exist "sessions.db" (
    del /F /Q "sessions.db"
    echo   - Deleted sessions.db
) else (
    echo   - sessions.db not found (already clean)
)

REM Delete artifacts directory
echo [3/3] Removing artifacts...
if exist "my_agent\.adk\artifacts" (
    rmdir /S /Q "my_agent\.adk\artifacts"
    echo   - Deleted my_agent\.adk\artifacts
) else (
    echo   - artifacts directory not found (already clean)
)

REM Also clean session.db inside my_agent if exists
if exist "my_agent\.adk\session.db" (
    del /F /Q "my_agent\.adk\session.db"
    echo   - Deleted my_agent\.adk\session.db
)

echo.
echo ========================================
echo   Reset complete!
echo ========================================
echo.
echo All chat history, artifacts, and sessions have been deleted.
echo You can now restart the agent with: python main.py
echo.
pause
