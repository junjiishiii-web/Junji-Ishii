import sys
import os
import io
import pathlib
import traceback
import datetime
import threading
from fastapi import Body, FastAPI, UploadFile, File, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

# Injeta a pasta atual no sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import gsheets
import sessions
from parser import gerar_modelagem_testes_completa, dados_para_frontend, exportar_planilha_para_bytes

_LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ModelerAssistant", "logs")
try:
    os.makedirs(_LOG_DIR, exist_ok=True)
except OSError:
    _LOG_DIR = os.path.expanduser("~")
_BACKEND_LOG = os.path.join(_LOG_DIR, "backend.log")

SESSION_COOKIE = "modeler_session"
SESSION_MAX_AGE = 8 * 60 * 60  # 8h — cobre um turno de trabalho


def _log_erro(contexto, exc):
    try:
        with open(_BACKEND_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {contexto}\n")
            f.write(traceback.format_exc())
            f.write("\n")
    except OSError:
        pass


app = FastAPI(title="Modeler Assistant API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir Frontend Estático
_HERE = pathlib.Path(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
_FRONTEND = _HERE.parent / "frontend"
if not _FRONTEND.exists():
    _FRONTEND = _HERE / "frontend"

if _FRONTEND.exists():
    app.mount("/app", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")


def _sessao_de(request: Request) -> tuple[sessions.SessaoDados, str, bool]:
    """Le o cookie de sessao do pedido; cria um novo se nao existir."""
    sid = request.cookies.get(SESSION_COOKIE)
    novo = not sid
    if novo:
        sid = sessions.novo_session_id()
    return sessions.obter_ou_criar(sid), sid, novo


_COOKIE_SECURE = os.environ.get("MODELER_COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")


def _aplicar_cookie_se_novo(resp, sid, novo):
    if novo:
        resp.set_cookie(
            key=SESSION_COOKIE,
            value=sid,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=_COOKIE_SECURE,
        )


_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _validar_xlsx_basico(conteudo: bytes, nome_arquivo: str, rotulo: str):
    if not conteudo or not conteudo.startswith(_ZIP_MAGIC):
        raise HTTPException(
            status_code=400,
            detail=(
                f"O arquivo '{nome_arquivo}' enviado como {rotulo} não parece ser um .xlsx válido "
                "(o conteúdo não é reconhecível como pacote Excel). Isso costuma acontecer quando o "
                "arquivo é um .xls antigo, .xlsb, foi renomeado sem converter de verdade, ou corrompeu "
                "no envio. Abra no Excel e use \"Salvar como\" → Pasta de Trabalho do Excel (.xlsx), "
                "depois envie de novo."
            ),
        )


@app.post("/api/upload-spec")
async def upload_spec(request: Request, response: Response, file: UploadFile = File(...)):
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)
    conteudo = await file.read()
    _validar_xlsx_basico(conteudo, file.filename, "SPEC")
    sessao.spec_bytes = conteudo
    sessao.nome_spec = file.filename
    return {"status": "success", "arquivo": file.filename}


@app.post("/api/upload-spec-empresas")
async def upload_spec_empresas(request: Request, response: Response, file: UploadFile = File(...)):
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)
    conteudo = await file.read()
    _validar_xlsx_basico(conteudo, file.filename, "SPEC ClaroEmpresas")
    sessao.spec_empresas_bytes = conteudo
    return {"status": "success", "arquivo": file.filename}


def _link_google_sheets(request: Request, response: Response, payload: dict, alvo: str):
    """alvo: 'spec' ou 'spec_empresas' — baixa e valida, devolvendo (sessao, nome_arquivo)."""
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)
    url = (payload or {}).get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Informe o link do Google Sheets.")
    try:
        conteudo, file_id = gsheets.baixar_como_xlsx(url)
    except gsheets.GoogleSheetsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nome_arquivo = f"GoogleSheets_{file_id}.xlsx"
    if alvo == "spec":
        sessao.spec_bytes = conteudo
        sessao.nome_spec = nome_arquivo
    else:
        sessao.spec_empresas_bytes = conteudo
    return {"status": "success", "arquivo": nome_arquivo}


@app.post("/api/upload-spec-link")
def upload_spec_link(request: Request, response: Response, payload: dict = Body(...)):
    return _link_google_sheets(request, response, payload, "spec")


@app.post("/api/upload-spec-empresas-link")
def upload_spec_empresas_link(request: Request, response: Response, payload: dict = Body(...)):
    return _link_google_sheets(request, response, payload, "spec_empresas")


@app.post("/api/upload-eep")
async def upload_eep(request: Request, response: Response, file: UploadFile = File(...)):
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)
    sessao.eep_bytes = await file.read()
    sessao.nome_eep = file.filename
    return {"status": "success", "arquivo": file.filename}


# Mantido por compatibilidade com versões antigas do frontend.
@app.post("/api/upload-escopo")
async def upload_escopo(request: Request, response: Response, file: UploadFile = File(...)):
    return await upload_eep(request, response, file)


def _gerar(sessao: sessions.SessaoDados, tipo_a: bool, ivr_code: str = ""):
    if not sessao.spec_bytes or not sessao.eep_bytes:
        raise HTTPException(status_code=400, detail="Certifique-se de carregar os arquivos da SPEC e do EEP.")
    try:
        return gerar_modelagem_testes_completa(
            io.BytesIO(sessao.spec_bytes),
            sessao.eep_bytes,
            tipo_a=tipo_a,
            ivr_code=ivr_code or None,
            eep_filename=sessao.nome_eep,
            spec_bytes_empresas=sessao.spec_empresas_bytes,
        )
    except Exception as e:
        _log_erro("Erro em gerar_modelagem_testes_completa", e)
        raise HTTPException(
            status_code=500,
            detail=f"Erro na modelagem de QA: {type(e).__name__}: {e}. Detalhes em {_BACKEND_LOG}",
        )


@app.get("/api/modelagem")
def obter_modelagem(request: Request, response: Response, tipo_a: bool = True, ivr_code: str = ""):
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)
    dados = _gerar(sessao, tipo_a, ivr_code)
    return dados_para_frontend(dados)


# ---------- Geração assíncrona com progresso real (para a barra de % + ETA) ----------


def _rodar_modelagem_em_thread(sessao: sessions.SessaoDados, tipo_a, ivr_code):
    def callback(pct, etapa):
        sessao.atualizar_progresso(percentual=round(pct, 1), etapa=etapa)

    try:
        dados = gerar_modelagem_testes_completa(
            io.BytesIO(sessao.spec_bytes),
            sessao.eep_bytes,
            tipo_a=tipo_a,
            ivr_code=ivr_code or None,
            eep_filename=sessao.nome_eep,
            spec_bytes_empresas=sessao.spec_empresas_bytes,
            progress_callback=callback,
        )
        sessao.resultado = dados
        sessao.atualizar_progresso(percentual=100, etapa="Concluído.", concluido=True)
    except Exception as e:
        _log_erro("Erro em gerar_modelagem_testes_completa (async)", e)
        sessao.atualizar_progresso(
            concluido=True,
            erro=f"Erro na modelagem de QA: {type(e).__name__}: {e}. Detalhes em {_BACKEND_LOG}",
        )


@app.post("/api/iniciar-modelagem")
def iniciar_modelagem(request: Request, response: Response, tipo_a: bool = True, ivr_code: str = ""):
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)

    if not sessao.spec_bytes or not sessao.eep_bytes:
        raise HTTPException(status_code=400, detail="Certifique-se de carregar os arquivos da SPEC e do EEP.")

    import time as _time

    with sessao.lock:
        sessao.progresso.update(
            {"percentual": 0, "etapa": "Iniciando...", "concluido": False, "erro": None, "inicio": _time.time(), "elapsed": 0.0}
        )
    sessao.resultado = None

    thread = threading.Thread(target=_rodar_modelagem_em_thread, args=(sessao, tipo_a, ivr_code), daemon=True)
    thread.start()
    return {"status": "iniciado"}


@app.get("/api/progresso")
def obter_progresso(request: Request, response: Response):
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)
    return sessao.ler_progresso()


@app.get("/api/resultado-modelagem")
def obter_resultado_modelagem(request: Request, response: Response):
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)
    progresso = sessao.ler_progresso()
    if not progresso["concluido"]:
        raise HTTPException(status_code=425, detail="A modelagem ainda não terminou.")
    if progresso["erro"]:
        raise HTTPException(status_code=500, detail=progresso["erro"])
    if not sessao.resultado:
        raise HTTPException(status_code=500, detail="Resultado indisponível — tente gerar novamente.")
    return dados_para_frontend(sessao.resultado)


@app.get("/api/exportar-testes")
def exportar_planilha_testes(request: Request, tipo_a: bool = True, ivr_code: str = ""):
    sessao, sid, novo = _sessao_de(request)
    dados = _gerar(sessao, tipo_a, ivr_code)
    try:
        xlsx_bytes, _relatorio = exportar_planilha_para_bytes(dados)
    except Exception as e:
        _log_erro("Erro em exportar_planilha_para_bytes", e)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao exportar planilha Excel: {type(e).__name__}: {e}. Detalhes em {_BACKEND_LOG}",
        )

    filename = f"Plano_de_Testes_URA_{str(dados['jira_ivr']).replace('/', '_').replace(' ', '')}.xlsx"
    resp = StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
    _aplicar_cookie_se_novo(resp, sid, novo)
    return resp


@app.get("/api/relatorio-validacao")
def relatorio_validacao(request: Request, response: Response, tipo_a: bool = True, ivr_code: str = ""):
    sessao, sid, novo = _sessao_de(request)
    _aplicar_cookie_se_novo(response, sid, novo)
    dados = _gerar(sessao, tipo_a, ivr_code)
    try:
        _xlsx_bytes, relatorio = exportar_planilha_para_bytes(dados)
    except Exception as e:
        _log_erro("Erro em relatorio_validacao", e)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao validar planilha: {type(e).__name__}: {e}. Detalhes em {_BACKEND_LOG}",
        )
    return relatorio


@app.get("/api/status-servidor")
def status_servidor():
    """Usado apenas para diagnostico: quantas sessoes ativas o servidor tem agora."""
    return {"sessoes_ativas": sessions.contagem_ativa()}


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("MODELER_HOST", "127.0.0.1")
    porta = int(os.environ.get("MODELER_PORT", "8001"))
    uvicorn.run("app:app", host=host, port=porta, reload=False)
