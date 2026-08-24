@echo off
:: Inicia o Modeler Assistant em modo servidor web (sem janela de app),
:: acessivel por outros computadores da rede local.
::
:: Uso manual: so dar duplo-clique. A janela do terminal fica aberta
:: mostrando os logs; feche a janela (ou Ctrl+C) para parar o servidor.
::
:: Para rodar sempre em segundo plano (sem essa janela), use a Tarefa
:: Agendada "ModelerAssistantWeb" (configure_autostart.ps1 registra ela).

cd /d "%~dp0"
title Modeler Assistant - Servidor Web

if not exist venv (
    echo [ERRO] Ambiente virtual "venv" nao encontrado. Rode iniciar_qa_modeler.bat
    echo        uma vez primeiro para criar e configurar o ambiente.
    pause
    exit /b 1
)

call venv\Scripts\activate

set MODELER_HOST=0.0.0.0
set MODELER_PORT=8001

echo ============================================================
echo   MODELER ASSISTANT - SERVIDOR WEB
echo   Acessivel em: http://%COMPUTERNAME%:%MODELER_PORT%/app/index.html
echo   (ou pelo IP desta maquina na rede, na mesma porta)
echo   Feche esta janela para parar o servidor.
echo ============================================================
echo.

python backend\servidor.py
pause
