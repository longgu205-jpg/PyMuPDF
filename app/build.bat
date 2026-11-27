@echo off
setlocal
cd /d "%~dp0"

echo === PDF Translator - build Windows exe (onedir) ===
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python launcher "py" not found. Install Python 3.x first.
    pause
    exit /b 1
)

echo [1/5] Creating clean venv: build_venv ...
if exist build_venv rmdir /s /q build_venv
py -3 -m venv build_venv
if errorlevel 1 goto :fail

call build_venv\Scripts\activate.bat

echo [2/5] Installing pymupdf + pyinstaller ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo [3/5] Running tests ...
python -m pip install pytest
python -m pytest tests\test_pdftrans.py -q
if errorlevel 1 goto :fail

echo [4/5] Building dist\PDFTranslator\ onedir bundle ...
python -m PyInstaller --noconfirm --clean --onedir --windowed --name PDFTranslator --collect-all pymupdf translate_gui.py
if errorlevel 1 goto :fail

echo [5/5] Done.
echo Output: %~dp0dist\PDFTranslator\PDFTranslator.exe
echo Zip the whole dist\PDFTranslator folder to share with colleagues.
pause
exit /b 0

:fail
echo.
echo [ERROR] Build failed. Check the messages above.
pause
exit /b 1
