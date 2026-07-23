@echo off
setlocal EnableExtensions

cd /d "%~dp0\.."

goto :main

:python_has_modules
set "PYTHON_CMD=%~1"
set "REQUIRED_MODULES=%~2"
"%PYTHON_CMD%" -c "import importlib.util, sys; mods=[m for m in '%REQUIRED_MODULES%'.split(',') if m]; missing=[m for m in mods if importlib.util.find_spec(m) is None]; sys.exit(1 if missing else 0)" >nul 2>&1
exit /b %errorlevel%

:resolve_python_for_modules
set "TARGET_VAR=%~1"
set "REQUIRED_MODULES=%~2"
for %%P in (py python) do (
    call :python_has_modules "%%P" "%REQUIRED_MODULES%"
    if not errorlevel 1 (
        set "%TARGET_VAR%=%%P"
        exit /b 0
    )
)
exit /b 1

:main
set "BUILD_PYTHON="
set "ICON_PYTHON="
if exist ".venv\Scripts\python.exe" (
    call :python_has_modules ".venv\Scripts\python.exe" "openpyxl,PyInstaller"
    if not errorlevel 1 set "BUILD_PYTHON=.venv\Scripts\python.exe"
    call :python_has_modules ".venv\Scripts\python.exe" "PIL"
    if not errorlevel 1 set "ICON_PYTHON=.venv\Scripts\python.exe"
)
if not defined BUILD_PYTHON (
    call :resolve_python_for_modules BUILD_PYTHON "openpyxl,PyInstaller"
    if errorlevel 1 (
        echo Dependencias ausentes para build. Instale com:
        echo   py -m pip install -r requirements.txt
        exit /b 1
    )
)
if not defined ICON_PYTHON (
    call :resolve_python_for_modules ICON_PYTHON "PIL"
    if errorlevel 1 (
        echo Dependencia ausente para gerar icones. Instale com:
        echo   py -m pip install -r requirements.txt
        exit /b 1
    )
)

set "RUN_TESTS=%RUN_TESTS%"
if not defined RUN_TESTS set "RUN_TESTS=1"
set "DIST_DIR=dist\DocFLow"
set "APP_EXE=%DIST_DIR%\DocFLow.exe"

if not "%RUN_TESTS%"=="0" (
    echo Executando testes antes do build...
    "%BUILD_PYTHON%" -m unittest tests.test_services tests.test_storage tests.test_resources tests.test_display tests.test_release_files
    if errorlevel 1 exit /b 1
)

echo Gerando icones de release...
"%ICON_PYTHON%" scripts\generate_icons.py
if errorlevel 1 exit /b %errorlevel%

echo Executando PyInstaller...
"%BUILD_PYTHON%" -m PyInstaller --noconfirm --clean documentos_empresa_app.spec
if errorlevel 1 exit /b %errorlevel%
if not exist "%DIST_DIR%\" (
    echo O build terminou sem gerar a pasta "%DIST_DIR%".
    exit /b 1
)
if not exist "%APP_EXE%" (
    echo O build terminou sem gerar o executavel "%APP_EXE%".
    echo Conteudo atual de "%DIST_DIR%":
    dir "%DIST_DIR%" /a
    echo.
    echo Rode o comando abaixo para ver o log completo do PyInstaller:
    echo   "%BUILD_PYTHON%" -m PyInstaller --noconfirm --clean documentos_empresa_app.spec
    exit /b 1
)

for /f %%i in ('"%BUILD_PYTHON%" -c "from documentos_empresa_app import __version__; print(__version__)"') do set "APP_VERSION=%%i"
if not defined APP_VERSION (
    echo Nao foi possivel identificar a versao da aplicacao.
    exit /b 1
)

set "INSTALLER_VERSION="
for /f %%i in ('powershell -NoProfile -Command "$content = Get-Content 'assets\installer\DocFLow.iss' -Raw; if ($content -match '#define AppVersion \"([^\"]+)\"') { $matches[1] }"') do set "INSTALLER_VERSION=%%i"
if not defined INSTALLER_VERSION (
    echo Nao foi possivel identificar a versao do instalador em assets\installer\DocFLow.iss.
    exit /b 1
)
if /I not "%INSTALLER_VERSION%"=="%APP_VERSION%" (
    echo A versao do instalador ^(%INSTALLER_VERSION%^) difere da versao da aplicacao ^(%APP_VERSION%^).
    echo Atualize assets\installer\DocFLow.iss antes de empacotar no Windows.
    exit /b 1
)

if not exist "dist_release" mkdir "dist_release"
set "ZIP_PATH=dist_release\DocFLow-win64-v%APP_VERSION%.zip"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"

echo Empacotando arquivos finais...
powershell -NoProfile -Command "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Build Windows concluido em: %cd%\%DIST_DIR%
echo Arquivo de distribuicao: %cd%\%ZIP_PATH%
echo Icone de empacotamento: assets\icons\icon.ico

where iscc >nul 2>&1
if not errorlevel 1 (
    echo.
    echo Inno Setup detectado. Gerando instalador...
    iscc assets\installer\DocFLow.iss
    if errorlevel 1 exit /b 1
) else (
    echo.
    echo Inno Setup nao encontrado no PATH.
    echo Para gerar o instalador, abra assets\installer\DocFLow.iss no Inno Setup ou execute "iscc assets\installer\DocFLow.iss".
)
