@echo off


call venv\Scripts\activate.bat
set PYTHONPATH=%PYTHONPATH%;install\lib
python yoloCode\codever2\capture.py

pause
