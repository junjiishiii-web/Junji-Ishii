@echo off
REM Arraste um arquivo .xlsb em cima deste .bat pra converter pra .xlsx
REM usando o Excel ja instalado na maquina (sem instalar nada).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ConverterXLSB.ps1" -CaminhoArquivo "%~1"
