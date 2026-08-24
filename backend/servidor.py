"""
Ponto de entrada do modo servidor web (sem janela): sobe o FastAPI ouvindo na
rede local para varios colegas acessarem pelo navegador ao mesmo tempo,
cada um com sua propria sessao isolada (ver sessions.py).

Diferenca do desktop.py: aqui nao ha janela pywebview nenhuma — e so o
servidor, pensado para ficar rodando em segundo plano (via Tarefa Agendada)
o tempo todo que esta maquina estiver ligada. Atualizar o app agora e so
editar os arquivos em backend/frontend e reiniciar este processo — sem
reinstalar nada em lugar nenhum.

Variaveis de ambiente:
  MODELER_HOST — interface de rede (padrao 0.0.0.0 = todas, acessivel na LAN)
  MODELER_PORT — porta TCP (padrao 8001)
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

_LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ModelerAssistant", "logs")
try:
    os.makedirs(_LOG_DIR, exist_ok=True)
except OSError:
    _LOG_DIR = os.path.expanduser("~")

# Quando rodado via pythonw.exe (sem console — ex.: Tarefa Agendada em modo
# oculto), sys.stdout/stderr vem como None e qualquer lib que assuma um
# stream de verdade quebra (uvicorn inclusive). Redireciona pra arquivo antes
# de qualquer coisa usar esses streams — mesmo problema/solucao do desktop.py.
if sys.stdout is None:
    sys.stdout = open(os.path.join(_LOG_DIR, "servidor_stdout.log"), "a", encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = open(os.path.join(_LOG_DIR, "servidor_stderr.log"), "a", encoding="utf-8", buffering=1)


def main():
    import uvicorn
    from app import app

    host = os.environ.get("MODELER_HOST", "0.0.0.0")
    # PORT e a variavel que servicos de nuvem (Render, Railway, etc.) injetam
    # automaticamente com a porta que o container deve escutar — tem
    # prioridade sobre MODELER_PORT, que continua valendo pra uso local.
    porta = int(os.environ.get("PORT") or os.environ.get("MODELER_PORT", "8001"))
    uvicorn.run(app, host=host, port=porta, log_level="info")


if __name__ == "__main__":
    main()
