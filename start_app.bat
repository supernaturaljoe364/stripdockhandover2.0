@echo off
cd /d "%~dp0"
rem USB link to the phone (IP Webcam over the cable). Harmless if already set.
rem The adb.exe path is read from config.yaml (adb_path), so there is only one place to edit.
set "ADB="
for /f "usebackq delims=" %%A in (`.venv\Scripts\python -c "import yaml; print(yaml.safe_load(open('config.yaml', encoding='utf-8')).get('adb_path') or '')"`) do set "ADB=%%A"
if not defined ADB goto noadb
"%ADB%" forward tcp:8080 tcp:8080
goto run
:noadb
echo adb_path is empty in config.yaml: no USB port forward, Wi-Fi mode.
:run
.venv\Scripts\python run_app.py
pause
