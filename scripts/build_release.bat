@echo off
setlocal

cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import PIL" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=.venv\Scripts\python.exe"
    ) else (
        set "PYTHON=python"
    )
) else (
    set "PYTHON=python"
)

if exist ".venv\Scripts\pyinstaller.exe" (
    set "PYINSTALLER=.venv\Scripts\pyinstaller.exe"
) else (
    set "PYINSTALLER=pyinstaller"
)

%PYTHON% scripts\generate_icons.py
if errorlevel 1 exit /b %errorlevel%

%PYINSTALLER% --noconfirm --clean documentos_empresa_app.spec
if errorlevel 1 exit /b %errorlevel%

echo.
echo Build Windows concluido em: %cd%\dist\G-docs
echo Icone de empacotamento: assets\icons\icon.ico
