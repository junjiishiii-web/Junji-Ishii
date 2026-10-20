@echo off
cd /d "%~dp0"
title Modeler Assistant - Executor Avaya
cls
echo ============================================================
echo   MODELER ASSISTANT - EXECUTOR DE TESTES (Avaya one-X)
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto SEM_PYTHON

set "AMBIENTE=%LOCALAPPDATA%\ModelerExecutor\venv"
if exist "%AMBIENTE%\Scripts\python.exe" goto INSTALAR
echo [INFO] Primeira execucao: preparando o ambiente (1 a 2 minutos)...
python -m venv "%AMBIENTE%"
if errorlevel 1 goto ERRO_VENV

:INSTALAR
"%AMBIENTE%\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto ERRO_PIP

echo [OK] Ambiente pronto.
echo.
echo Mantenha esta janela aberta e use a aba Automacao do Modeler Assistant.
echo Para parar, feche esta janela.
echo.
"%AMBIENTE%\Scripts\python.exe" executor_avaya.py
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
echo [ERRO] Nao foi possivel instalar o pywinauto (confira a internet/proxy).
pause
exit /b
