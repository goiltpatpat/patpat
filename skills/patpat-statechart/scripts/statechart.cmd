@echo off
setlocal
node "%~dp0statechart.ts" %*
exit /b %errorlevel%
