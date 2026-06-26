@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%stop-gugabobo.bat"
call "%SCRIPT_DIR%start-gugabobo.bat"

endlocal
