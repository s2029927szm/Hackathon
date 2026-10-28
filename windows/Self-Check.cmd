@echo off
setlocal
pushd "%~dp0"
"python\python.exe" -X utf8 verify_integration.py
popd
pause
