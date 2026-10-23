@echo off
cd /d "%~dp0"
title Modeler Assistant - Executor de testes
cls
echo ============================================================
echo   MODELER ASSISTANT - EXECUTOR DE TESTES
echo   URA Legado / URA ROGUE (Avaya one-X) e ChatBOT (WhatsApp Web)
echo ============================================================
echo.

if not exist "%~dp0executor_avaya.py" goto SEM_ARQUIVOS

python --version >nul 2>&1
if errorlevel 1 goto SEM_PYTHON

set "AMBIENTE=%LOCALAPPDATA%\ModelerExecutor\venv"
if exist "%AMBIENTE%\Scripts\python.exe" goto INSTALAR
echo [INFO] Primeira execucao: preparando o ambiente (1 a 3 minutos)...
python -m venv "%AMBIENTE%"
if errorlevel 1 goto ERRO_VENV

:INSTALAR
echo [INFO] Conferindo as bibliotecas (pywinauto e playwright)...
"%AMBIENTE%\Scripts\python.exe" -m pip install -q --disable-pip-version-check "pywinauto>=0.6.8" "playwright>=1.45"
if errorlevel 1 goto ERRO_PIP

echo [OK] Ambiente pronto.
echo.
echo Mantenha esta janela aberta e use a aba Automacao do Modeler Assistant.
echo Para parar, feche esta janela.
echo.
"%AMBIENTE%\Scripts\python.exe" "%~dp0executor_avaya.py"
pause
exit /b

:SEM_ARQUIVOS
echo [ERRO] Nao encontrei o executor_avaya.py nesta pasta:
echo        %~dp0
echo.
echo        Provavelmente o .bat foi aberto de DENTRO do arquivo .zip.
echo        Clique com o botao direito no ModelerExecutor.zip, escolha
echo        "Extrair tudo...", abra a pasta extraida e rode o
echo        iniciar_executor.bat de la.
pause
exit /b

:SEM_PYTHON
echo [ERRO] Python nao encontrado. Instale o Python 3.10 ou superior
echo        (marque "Add Python to PATH") e abra este arquivo de novo.
pause
exit /b

:ERRO_VENV
echo [ERRO] Nao foi possivel criar o ambiente em %AMBIENTE%.
pause
exit /b

:ERRO_PIP
echo [ERRO] Nao foi possivel instalar as bibliotecas pywinauto/playwright
echo        (confira a internet ou o proxy da rede).
pause
exit /b
