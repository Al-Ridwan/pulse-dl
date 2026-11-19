@echo off
title PulseDL - Studio MP3 Extractor ^& Universal Video Downloader
cd /d "%~dp0"
set "PATH=C:\pinokio\bin\miniforge\Library\bin;%PATH%"
echo Starting PulseDL on http://127.0.0.1:8000 ...
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

