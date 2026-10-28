@echo off
setlocal
pushd "%~dp0"
"python\python.exe" -X utf8 launcher.py reset
popd
pause
