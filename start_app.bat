@echo off
cd /d C:\stripdock_r3
rem USB link to the phone (IP Webcam over the cable). Harmless if already set.
"C:\Users\Hp\AppData\Local\Android\Sdk\platform-tools\adb.exe" forward tcp:8080 tcp:8080
.venv\Scripts\python run_app.py
pause
