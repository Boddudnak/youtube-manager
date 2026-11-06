@echo off
cd /d "%~dp0.."
set PYTHONUTF8=1
py -3.12 ytm.py sync > data\sync\last-run.txt 2>&1
