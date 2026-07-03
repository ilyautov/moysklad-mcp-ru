@echo off
REM Windows double-click installer. Wires the MoySklad MCP server into Claude
REM Desktop and saves your token locally. No pip install, no manual JSON editing.
cd /d "%~dp0"
python install.py %*
if errorlevel 1 (
  echo.
  echo Python не найден? Установите Python 3.10+ с https://python.org
  echo и при установке отметьте "Add python.exe to PATH".
)
echo.
pause
