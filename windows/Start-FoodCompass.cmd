@echo off
setlocal
pushd "%~dp0"
if not exist "python\python.exe" goto missing
"python\python.exe" -X utf8 launcher.py %*
set code=%errorlevel%
popd
if not "%code%"=="0" pause
exit /b %code%
:missing
echo python\python.exe was not found. Extract the whole ZIP to a folder first, then run this file again.
popd
pause
exit /b 1
