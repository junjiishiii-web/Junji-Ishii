@echo off
:: Garante que a execução ocorra no diretório deste arquivo .bat
cd /d "%~dp0"

title Modeler Assistant - Modo Desenvolvimento
cls

echo ============================================================
echo   MODELER ASSISTANT - MODO DESENVOLVIMENTO (via navegador)
echo   Para gerar o instalador para os parceiros, use build_instalador.bat
echo ============================================================
echo.

:: 1. Verificar se o Python está instalado no sistema
python --version >nul 2>&1
if errorlevel 1 goto ERRO_PYTHON
goto CHECK_VENV

:ERRO_PYTHON
echo [ERRO] O Python nao foi localizado no sistema!
echo.
echo Certifique-se de:
echo 1. Ter o Python 3.10 ou superior instalado.
echo 2. Ter marcado a opcao "Add Python to PATH" ao instalar.
echo.
pause
exit /b

:CHECK_VENV
:: 2. Criar ambiente virtual se nao existir
if exist venv goto ACTIVATE_VENV
echo [INFO] Criando ambiente virtual isolado...
python -m venv venv
if errorlevel 1 goto ERRO_VENV
echo [OK] Ambiente virtual criado com sucesso!
echo.
goto ACTIVATE_VENV

:ERRO_VENV
echo [ERRO] Falha ao criar o ambiente virtual.
pause
exit /b

:ACTIVATE_VENV
:: 3. Ativar o ambiente virtual
echo [INFO] Ativando ambiente virtual...
call venv\Scripts\activate
if errorlevel 1 goto ERRO_ACTIVATE
goto INSTALL_REQS

:ERRO_ACTIVATE
echo [ERRO] Falha ao ativar o ambiente virtual.
pause
exit /b

:INSTALL_REQS
:: 4. Instalar e atualizar dependencias do requirements.txt
echo [INFO] Verificando e instalando dependencias (requirements.txt)...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 goto ERRO_REQS
echo [OK] Dependencias verificadas e atualizadas!
echo.
goto LAUNCH_APP

:ERRO_REQS
echo [ERRO] Falha ao instalar dependencias do requirements.txt.
pause
exit /b

:LAUNCH_APP
:: 5. Abrir o navegador automaticamente no dashboard do QA
echo [INFO] Abrindo painel de QA no navegador...
start "" "http://localhost:8001/app/index.html"

:: 6. Executar o servidor FastAPI local
echo [INFO] Subindo o servidor backend na porta 8001...
echo.
echo ------------------------------------------------------------
echo     A PLATAFORMA ESTA NO AR! (Mantenha esta janela aberta)
echo ------------------------------------------------------------
echo.
python backend/app.py

pause
