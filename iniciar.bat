@echo off
setlocal
 title Meus Gastos - Financas
cd /d "%~dp0"
echo.
echo Iniciando Meus Gastos - Financas...
echo Mantenha esta janela aberta enquanto usa o aplicativo.
echo.
if exist ".venv\Scripts\python.exe" goto dependencies
echo Preparando o ambiente na primeira execucao...
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:usepython
where python >nul 2>nul
if errorlevel 1 goto missingpython
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -c "import pypdf, cryptography" 2>nul
if not errorlevel 1 goto launch
echo Instalando componentes necessarios. Aguarde...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:launch
echo Abrindo o aplicativo em uma porta disponivel...
".venv\Scripts\python.exe" -u app.py
if errorlevel 1 goto failed
goto end
:missingpython
echo Python nao encontrado. Instale Python 3 e execute este arquivo novamente.
goto end
:failed
echo.
echo Nao foi possivel iniciar o aplicativo. Confira a mensagem de erro acima.
:end
echo.
pause
endlocal
