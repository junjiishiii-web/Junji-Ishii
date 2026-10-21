"""Executor de testes do Modeler Assistant — controla o Avaya one-X Communicator.

Roda na máquina do QA (que está na VPN e com o one-X aberto e logado) e abre um
servidor local em http://127.0.0.1:47123. A aba Automação do Modeler (site) manda
cada CT para cá; o executor:

  1. disca pelo one-X (campo "Insira um nome ou número" + botão Discar);
  2. URA ROGUE: ao atender, digita o código da esteira;
  3. URA Legado: acompanha o URADebug da URA em tempo real (pasta de rede
     \\\\URA\\lmcti\\Data\\UraLog\\AAAA\\MM\\DD) e manda as teclas de cada passo quando a
     URA toca o prompt daquele estado; sem acesso ao log, usa tempo de espera;
  4. desliga e devolve ao site o log da chamada (Log URA + Log Integração) ou,
     no ROGUE, tenta achar o trace no Grafana.

O controle do one-X é feito pelos controles da janela (UI Automation): não mexe no
mouse nem no teclado, então o QA continua usando o computador normalmente.
"""
import ctypes
import datetime
import glob
import json
import os
import queue
import re
import ssl
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSAO = "1.3"
PORTA = int(os.environ.get("MODELER_EXECUTOR_PORTA", "47123"))

# Segurança: o executor liga de verdade, então só obedece ao Modeler Assistant (qualquer outra
# página aberta no navegador é recusada) e só disca para as URAs de homologação conhecidas.
ORIGENS_PERMITIDAS = {
    "https://modeler-assistant.onrender.com",
    "http://localhost:8001", "http://127.0.0.1:8001",
    "http://localhost:8002", "http://127.0.0.1:8002",
}
ORIGENS_PERMITIDAS |= {o.strip() for o in os.environ.get("MODELER_EXECUTOR_ORIGENS", "").split(",") if o.strip()}
NUMEROS_PERMITIDOS = {
    "003121086290", "003121086490", "003121086950", "003121089290",   # URA Legado BH
    "001921375400",                                                     # URA Legado CPS
    "002136161194216915",                                               # ROGUE (CRN esteiras)
}
NUMEROS_PERMITIDOS |= {re.sub(r"\D", "", n) for n in os.environ.get("MODELER_EXECUTOR_NUMEROS", "").split(",") if n.strip()}

_TECLAS = {
    "0": "DialButtonZero", "1": "DialButtonOne", "2": "DialButtonTwo", "3": "DialButtonThree",
    "4": "DialButtonFour", "5": "DialButtonFive", "6": "DialButtonSix", "7": "DialButtonSeven",
    "8": "DialButtonEight", "9": "DialButtonNine", "*": "DialButtonStar", "#": "DialButtonPound",
}
# Partes da janela do one-X que não interessam (o histórico de chamadas tem milhares de itens
# e deixaria cada busca lenta).
_PULAR = {"CallLog", "Contacts", "Messages", "FeatureButtons", "SettingsPanelAudio", "SettingsPanelVideo", "SettingsPanelPhone"}

_LINHA = re.compile(r"^\[(\d{2}/\d{2}/\d{4})\]\[(\d{2}:\d{2}:\d{2})\]\[[^\]]*\]\[([^\]]*)\]\[(\d+)\]\[(\d+)\]->(.*)$")


def _agora():
    return datetime.datetime.now().strftime("%H:%M:%S")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


# ─────────────────────────── one-X ───────────────────────────

def _onex_aberto():
    """Procura a janela do one-X sem COM (barato; usado no /status)."""
    achou = []
    user32 = ctypes.windll.user32
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "one-x" in buf.value.lower() and user32.IsWindowVisible(hwnd):
                achou.append(buf.value)
        return True
    user32.EnumWindows(_cb, 0)
    return bool(achou)


def _mostrado(el):
    """Controle exibido pelo one-X: tem tamanho na tela. Não usa is_visible(), que fica False quando a
    janela está atrás de outra ou parcialmente fora do monitor (os controles ocultos do WPF têm 0x0)."""
    try:
        r = el.rectangle()
        return r.width() > 0 and r.height() > 0
    except Exception:
        return False


def _exe_do_processo(pid):
    try:
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = ctypes.c_ulong(1024)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return os.path.basename(buf.value).lower()
        finally:
            k32.CloseHandle(h)
    except Exception:
        pass
    return ""


class OneX:
    def __init__(self):
        from pywinauto import Desktop  # importado aqui: precisa do COM da thread que usa
        self._Desktop = Desktop
        self.janela = None

    def _janela(self):
        if self.janela is not None:
            try:
                self.janela.element_info.name   # ainda existe?
                return self.janela
            except Exception:
                self.janela = None
        # Não filtra por "visível": janela parcialmente fora da tela ou atrás de outra conta como visível=False
        # para o Windows. Procura pelo programa (onexcui.exe) e, de reserva, pelo título.
        vistas = []
        for tentativa in range(3):
            try:
                janelas = self._Desktop(backend="uia").windows(visible_only=False)
            except Exception:
                janelas = []
            pelo_titulo = None
            for w in janelas:
                try:
                    titulo = w.window_text() or ""
                    exe = _exe_do_processo(w.element_info.process_id)
                except Exception:
                    continue
                if exe == "onexcui.exe":
                    vistas.append(titulo)
                    if titulo and _mostrado(w):
                        self.janela = w
                        return w
                if pelo_titulo is None and "one-x" in titulo.lower():
                    pelo_titulo = w
            if pelo_titulo is not None:
                self.janela = pelo_titulo
                return pelo_titulo
            time.sleep(1)
        detalhe = f" Janelas do onexcui.exe encontradas: {vistas}" if vistas else " Nenhuma janela do onexcui.exe encontrada."
        raise RuntimeError("Não encontrei a janela do Avaya one-X Communicator (está aberto e logado?)." + detalhe)

    def achar(self, ids):
        achados, pilha = {}, [self._janela()]
        while pilha:
            e = pilha.pop()
            try:
                filhos = e.children()
            except Exception:
                continue
            for c in filhos:
                try:
                    aid = c.element_info.automation_id or ""
                    if aid in _PULAR:
                        continue
                    if aid in ids and aid not in achados and _mostrado(c):
                        achados[aid] = c
                    pilha.append(c)
                except Exception:
                    pass
        return achados

    def em_chamada(self):
        # Um soluço da UI Automation no meio da chamada não pode derrubar o CT: tenta de novo.
        for tentativa in range(3):
            try:
                return "ButtonEnd" in self.achar({"ButtonEnd"})
            except Exception:
                if tentativa == 2:
                    raise
                self.janela = None
                time.sleep(1)

    def tempo_na_tela(self):
        t = self.achar({"TextBlockTime"}).get("TextBlockTime")
        return (t.window_text() or "").strip() if t else ""

    def discar(self, digitos):
        c = self.achar({"TextBoxSearch", "ButtonDial"})
        if "TextBoxSearch" not in c or "ButtonDial" not in c:
            raise RuntimeError("Não achei o campo de número ou o botão Discar do one-X.")
        c["TextBoxSearch"].set_edit_text(digitos)
        time.sleep(0.3)
        c["ButtonDial"].invoke()

    def teclas(self, digitos, intervalo=0.35):
        botoes = self.achar(set(_TECLAS.values()))
        for d in digitos:
            b = botoes.get(_TECLAS.get(d, ""))
            if not b:
                raise RuntimeError(f"Tecla '{d}' do teclado do one-X não está visível (abra o teclado numérico no one-X).")
            b.invoke()
            time.sleep(intervalo)

    def desligar(self):
        b = self.achar({"ButtonEnd"}).get("ButtonEnd")
        if b:
            b.invoke()
            return True
        return False


# ─────────────────────── log da URA Legado ───────────────────────

class LogUra:
    """Lê o URADebug do dia em tempo real e isola a chamada feita pelo executor."""

    def __init__(self, host, node, inicio, ani=""):
        self.inicio = inicio
        self.ani = re.sub(r"\D", "", ani or "")
        d = inicio
        self.dia = f"{d:%Y-%m-%d}"
        self.data_log = f"{d:%d/%m/%Y}"
        self.base = rf"\\{host}\lmcti\Data"
        self.dir_ura = os.path.join(self.base, "UraLog", f"{d:%Y}", f"{d:%m}", f"{d:%d}")
        self.dir_int = os.path.join(self.base, "IntegracaoLog", f"{d:%Y}", f"{d:%m}", f"{d:%d}")
        self.node = str(node)
        self.offsets, self.restos = {}, {}
        self.candidatas = {}          # (arquivo, canal, transacao) -> {"hora", "ani"}
        self.chamada = None           # (arquivo, canal, transacao)
        self.linhas = []              # linhas desta chamada
        self.eventos = []             # (seq, tipo, valor, estado, hora)
        self._seq = 0
        self._ultima = None

    def acessivel(self):
        try:
            return os.path.isdir(self.dir_ura)
        except OSError:
            return False

    def _segundos(self, hhmmss):
        h, m, s = map(int, hhmmss.split(":"))
        return h * 3600 + m * 60 + s

    def ler(self):
        padrao = os.path.join(self.dir_ura, f"URADebug_{self.dia}_{self.node}_*.txt")
        limite = time.time() - 600
        for arq in glob.glob(padrao):
            try:
                if os.path.getmtime(arq) < limite and arq not in self.offsets:
                    continue
                with open(arq, "rb") as f:
                    if arq not in self.offsets:
                        # Arquivo já existente: começa perto do fim (a chamada é nova).
                        f.seek(0, 2)
                        self.offsets[arq] = max(0, f.tell() - 200_000)
                    f.seek(self.offsets[arq])
                    bruto = f.read()
                    self.offsets[arq] += len(bruto)
            except OSError:
                continue
            texto = self.restos.get(arq, "") + bruto.decode("cp1252", errors="replace")
            partes = texto.split("\n")
            self.restos[arq] = partes.pop()
            for linha in partes:
                self._linha(arq, linha.rstrip("\r"))

    def _linha(self, arq, linha):
        m = _LINHA.match(linha)
        if not m:
            if self._ultima == self.chamada and self.chamada and linha.strip() and not re.match(r"^-{20,}", linha):
                self.linhas.append(linha)
            return
        data, hora, funcao, canal, transacao, msg = m.groups()
        chave = (arq, canal, transacao)
        self._ultima = chave
        if data != self.data_log:
            return
        if self.chamada is None:
            c = self.candidatas.setdefault(chave, {"hora": hora, "ani": ""})
            if funcao.strip() == "Inicializacao":
                r = re.match(r"^ANI\s*:\s*(\S+)", msg)
                if r:
                    c["ani"] = re.sub(r"\D", "", r.group(1))
            self._escolher()
        if chave != self.chamada:
            return
        self.linhas.append(linha)
        estado = funcao.strip()
        for tipo, rx in (("prompt", r"Vocalizando Prompt - (\S+)"), ("digitos", r"Digitos Coletados - (.*)$"),
                         ("sp", r"O ScripPoint (\d+) foi marcado"), ("transferencia", r"Transferindo para: (\S+)")):
            r = re.search(rx, msg)
            if r:
                self._seq += 1
                self.eventos.append((self._seq, tipo, r.group(1).strip(), estado, hora))
        if "DESLIGAMENTO" in msg:
            self._seq += 1
            self.eventos.append((self._seq, "desligamento", "", estado, hora))

    def _escolher(self):
        """A chamada do executor: a primeira que começou depois da discagem (folga de 20 s
        para diferença de relógio). Se o ANI foi informado, ele precisa bater."""
        alvo = self._segundos(self.inicio.strftime("%H:%M:%S")) - 20
        boas = []
        for chave, c in self.candidatas.items():
            if self._segundos(c["hora"]) < alvo:
                continue
            if self.ani and c["ani"] and c["ani"][-8:] != self.ani[-8:]:
                continue
            boas.append((c["hora"], chave))
        if boas:
            self.chamada = sorted(boas)[0][1]

    def esperar(self, condicao, limite, parar):
        fim = time.time() + limite
        while time.time() < fim and not parar.is_set():
            self.ler()
            r = condicao()
            if r:
                return r
            time.sleep(0.5)
        return None

    def integracao(self):
        if not self.chamada:
            return "", ""
        arq, canal, transacao = self.chamada
        m = re.search(r"_(\d{4}-\d{2}-\d{2}_\d+_\d+)\.txt$", arq, re.I)
        if not m:
            return "", ""
        nome = f"IntegracaoDebug_{m.group(1)}.txt"
        caminho = os.path.join(self.dir_int, nome)
        try:
            with open(caminho, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 3_000_000))
                texto = f.read().decode("cp1252", errors="replace")
        except OSError:
            return nome, ""
        saida, dentro = [], False
        for linha in texto.split("\n"):
            linha = linha.rstrip("\r")
            mm = _LINHA.match(linha)
            if mm:
                dentro = mm.group(4) == canal and mm.group(5) == transacao and mm.group(1) == self.data_log
            elif re.match(r"^-{20,}\s*$", linha):
                dentro = False
            if dentro:
                saida.append(linha)
        return nome, "\n".join(saida)


# ─────────────────────── trace do ROGUE (Grafana) ───────────────────────

def _diagnostico_pasta(log):
    try:
        if not os.path.isdir(log.base):
            return "a pasta compartilhada não abre deste computador"
        if not os.path.isdir(os.path.join(log.base, "UraLog")):
            return "sem a pasta UraLog"
        return "sem a pasta do dia"
    except OSError as e:
        return f"erro {e.__class__.__name__}"


def buscar_trace_rogue(grafana, ds_uid, inicio, ani=""):
    """Tenta achar no Jaeger (pelo proxy do Grafana) o trace que começou logo depois da discagem."""
    if not grafana or not ds_uid:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE   # Grafana interno com certificado próprio
    ini_us = int((inicio.timestamp() - 30) * 1_000_000)
    fim_us = int((time.time() + 60) * 1_000_000)
    url = (f"{grafana.rstrip('/')}/api/datasources/proxy/uid/{ds_uid}/api/traces"
           f"?service=Conversation&start={ini_us}&end={fim_us}&limit=40")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), context=ctx, timeout=20) as r:
            dados = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {"erro": f"Grafana: {type(e).__name__}: {e}"}
    ani = re.sub(r"\D", "", ani or "")
    melhores = []
    for t in dados.get("data") or []:
        spans = t.get("spans") or []
        if not spans:
            continue
        comeco = min(s.get("startTime", 0) for s in spans)
        if comeco < ini_us:
            continue
        if ani:
            froms = {re.sub(r"\D", "", str(tg.get("value", ""))) for s in spans for tg in (s.get("tags") or [])
                     if tg.get("key") in ("sessionContext.fromName", "sessionContext.ani")}
            if froms and not any(f.endswith(ani[-8:]) for f in froms if f):
                continue
        melhores.append((comeco, t))
    if not melhores:
        return {"erro": "Nenhum trace novo no Grafana depois da discagem."}
    return {"trace": {"data": [sorted(melhores, key=lambda x: x[0])[0][1]]}}


# ─────────────────────────── execução de um CT ───────────────────────────

class _Parado(Exception):
    pass


class Execucao:
    def __init__(self, pedido):
        self.pedido = pedido
        self.ct_id = pedido.get("ct_id", "")
        self.estado = "na_fila"
        self.eventos = []
        self.erro = ""
        self.resultado = {}
        self.inicio = None
        self.fim = None
        self.parar = threading.Event()

    def _dormir(self, segundos):
        # Espera interrompível: "Parar a execução" no site corta na hora.
        if self.parar.wait(float(segundos)):
            raise _Parado()

    def ev(self, texto):
        self.eventos.append(f"{_agora()} {texto}")
        print(f"[{self.ct_id}] {texto}", flush=True)

    def json(self):
        return {"ct_id": self.ct_id, "estado": self.estado, "eventos": self.eventos[-60:], "erro": self.erro,
                "inicio": self.inicio.isoformat(timespec="seconds") if self.inicio else None,
                "fim": self.fim.isoformat(timespec="seconds") if self.fim else None,
                "resultado": self.resultado if self.estado in ("concluida", "erro") else {}}

    def rodar(self):
        # Roda SEMPRE na thread única de _trabalhador(): o acesso à UI Automation criado numa thread
        # não funciona em outra (era por isso que só o 1º CT ligava e os seguintes "não achavam" o one-X).
        p = self.pedido
        onex = None
        try:
            onex = _onex_da_thread()
            if onex.em_chamada():
                raise RuntimeError("Já existe uma chamada ativa no one-X. Encerre-a antes de executar.")
            numero = re.sub(r"[^\d*#]", "", p.get("numero", ""))
            if not numero:
                raise RuntimeError("Sem número para discar.")
            if numero not in NUMEROS_PERMITIDOS:
                raise RuntimeError(f"Número {numero} não é de uma URA cadastrada no executor; não disquei.")
            self.inicio = datetime.datetime.now()
            self.estado = "discando"
            onex.discar(numero)
            self.ev(f"discando {numero}")
            fim = time.time() + float(p.get("espera_atender", 40))
            while time.time() < fim and not onex.em_chamada():
                self._dormir(0.5)
            if not onex.em_chamada():
                raise RuntimeError("A chamada não completou (o one-X não mostrou a ligação ativa).")
            self.estado = "em_chamada"
            self.ev("chamada ativa")

            if p.get("dtmf_ao_atender"):
                self._dormir(p.get("espera_codigo", 5))
                onex.teclas(str(p["dtmf_ao_atender"]))
                self.ev(f"código da esteira {p['dtmf_ao_atender']} digitado")

            log = None
            ura = p.get("ura") or {}
            if p.get("tecnologia") == "ura_legado" and ura.get("host"):
                # Pasta de rede da URA: pelo nome e, se não abrir, pelo IP.
                tentativas = []
                for h in [ura.get("host"), ura.get("ip")]:
                    if not h:
                        continue
                    cand = LogUra(h, ura.get("node", ""), self.inicio, p.get("ani", ""))
                    if cand.acessivel():
                        log = cand
                        break
                    tentativas.append(f"{cand.dir_ura} ({_diagnostico_pasta(cand)})")
                if log:
                    achou = log.esperar(lambda: log.chamada, 25, self.parar)
                    self.ev(f"log da URA: chamada canal {int(log.chamada[1])}, transação {int(log.chamada[2])}" if achou
                            else "log da URA: ainda não achei a chamada; sigo pelo tempo de espera")
                else:
                    self.ev("sem acesso ao log da URA — " + " | ".join(tentativas) + "; sigo pelo tempo de espera")

            espera_passo = float(p.get("espera_passo", 10))
            ultimo_seq = 0
            for passo in p.get("passos") or []:
                digitos = re.sub(r"[^\d*#]", "", str(passo.get("digitos", "")))
                if not digitos:
                    continue
                if self.parar.is_set():
                    raise _Parado()
                if not onex.em_chamada():
                    self.ev("a chamada caiu antes do fim dos passos")
                    break
                alvo = f"step {passo.get('n')} ({passo.get('estado') or '—'})"
                if log and log.chamada:
                    def _pronto(ultimo=ultimo_seq):
                        for seq, tipo, valor, estado, hora in log.eventos:
                            if seq <= ultimo or tipo != "prompt":
                                continue
                            if (_norm(passo.get("prompt_id")) and (_norm(passo.get("prompt_id")) in _norm(valor) or _norm(valor) in _norm(passo.get("prompt_id"))))\
                                    or (_norm(passo.get("estado")) and _norm(passo.get("estado")) in _norm(estado)):
                                return (seq, valor)
                        return None
                    r = log.esperar(_pronto, float(p.get("espera_prompt", 30)), self.parar)
                    if r:
                        ultimo_seq = r[0]
                        self.ev(f"{alvo}: URA tocou {r[1]}")
                    else:
                        novos = [e for e in log.eventos if e[0] > ultimo_seq and e[1] == "prompt"]
                        if novos:
                            ultimo_seq = novos[-1][0]
                        self.ev(f"{alvo}: prompt esperado não apareceu no log; digito assim mesmo")
                    self._dormir(p.get("espera_apos_prompt", 1.5))
                else:
                    self._dormir(espera_passo)
                onex.teclas(digitos)
                self.ev(f"{alvo}: digitou {digitos}")

            # Fim da jornada: transferência/desligamento no log, ou um tempo fixo.
            if log and log.chamada:
                r = log.esperar(lambda: [e for e in log.eventos if e[1] in ("transferencia", "desligamento")], float(p.get("espera_final", 25)), self.parar)
                if self.parar.is_set():
                    raise _Parado()
                self.ev("URA transferiu/encerrou" if r else "fim dos passos (sem transferência no log)")
                self._dormir(3)
            else:
                self._dormir(p.get("espera_final_sem_log", 15))
            if onex.desligar():
                self.ev("desliguei")
            time.sleep(2)

            if log:
                log.esperar(lambda: None, 4, self.parar)   # últimas linhas (CDR) depois do desligamento
                nome_int, texto_int = log.integracao()
                self.resultado = {
                    "tipo": "ura_legado",
                    "ura_arquivo": os.path.basename(log.chamada[0]) if log.chamada else "",
                    "ura_texto": "\n".join(log.linhas),
                    "integracao_arquivo": nome_int,
                    "integracao_texto": texto_int,
                }
            elif p.get("tecnologia") == "ura_rogue":
                self._dormir(p.get("espera_trace", 15))
                r = buscar_trace_rogue(p.get("grafana_url"), p.get("grafana_ds_uid"), self.inicio, p.get("ani", ""))
                self.resultado = {"tipo": "ura_rogue", **(r or {})}
                self.ev("trace do Grafana obtido" if r and r.get("trace") else f"trace não obtido: {(r or {}).get('erro', '')}")
            self.estado = "concluida"
        except _Parado:
            self.estado = "parado"
            self.ev("execução parada pelo QA")
            try:
                if onex and onex.desligar():
                    self.ev("desliguei")
            except Exception:
                pass
        except Exception as e:
            self.erro = f"{e}"
            self.estado = "erro"
            self.ev(f"ERRO: {e}")
            traceback.print_exc()
            try:
                if onex and onex.em_chamada():
                    onex.desligar()
                    self.ev("desliguei a chamada pendente")
            except Exception:
                pass
        finally:
            self.fim = datetime.datetime.now()


_ATUAL = {"exec": None}
_TRAVA = threading.Lock()
_FILA = queue.Queue()
_ONEX = {"obj": None}


def _onex_da_thread():
    if _ONEX["obj"] is None:
        _ONEX["obj"] = OneX()
    return _ONEX["obj"]


def _trabalhador():
    """Uma única thread faz todo o controle do one-X, CT após CT."""
    try:
        import comtypes
        comtypes.CoInitializeEx()
    except Exception:
        pass
    while True:
        ex = _FILA.get()
        try:
            ex.rodar()
        except Exception:
            traceback.print_exc()


# ─────────────────────────── servidor local ───────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _origem_ok(self):
        return (self.headers.get("Origin") or "") in ORIGENS_PERMITIDAS

    def _cors(self):
        origem = self.headers.get("Origin") or ""
        if origem not in ORIGENS_PERMITIDAS:
            return
        self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chrome: página pública acessando 127.0.0.1 (Private/Local Network Access)
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Vary", "Origin")

    def _json(self, codigo, dados):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        self.send_response(204 if self._origem_ok() else 403)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._origem_ok():
            return self._json(403, {"erro": "Origem não autorizada."})
        if self.path.startswith("/status"):
            ex = _ATUAL["exec"]
            ocupado = bool(ex and ex.estado in ("na_fila", "discando", "em_chamada"))
            return self._json(200, {"executor": "modeler-avaya", "versao": VERSAO, "onex_aberto": _onex_aberto(),
                                    "ocupado": ocupado, "ct_atual": ex.ct_id if ex else ""})
        if self.path.startswith("/execucao"):
            ex = _ATUAL["exec"]
            return self._json(200, ex.json() if ex else {"estado": "nenhuma"})
        self._json(404, {"erro": "rota desconhecida"})

    def do_POST(self):
        # Checado no servidor: mesmo um POST "simples" (sem preflight) de outro site é recusado
        # antes de qualquer ação.
        if not self._origem_ok():
            return self._json(403, {"erro": "Origem não autorizada."})
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self._json(415, {"erro": "Use Content-Type: application/json."})
        tam = int(self.headers.get("Content-Length") or 0)
        try:
            dados = json.loads(self.rfile.read(tam).decode("utf-8") or "{}")
        except Exception:
            return self._json(400, {"erro": "JSON inválido"})
        if self.path.startswith("/executar"):
            with _TRAVA:
                ex = _ATUAL["exec"]
                if ex and ex.estado in ("na_fila", "discando", "em_chamada"):
                    return self._json(409, {"erro": f"Já estou executando {ex.ct_id}."})
                ex = Execucao(dados)
                _ATUAL["exec"] = ex
                _FILA.put(ex)
            return self._json(200, {"ok": True, "ct_id": ex.ct_id})
        if self.path.startswith("/parar"):
            ex = _ATUAL["exec"]
            if ex:
                ex.parar.set()
            return self._json(200, {"ok": True})
        self._json(404, {"erro": "rota desconhecida"})


def main():
    print("=" * 64)
    print(f"  MODELER ASSISTANT — EXECUTOR AVAYA v{VERSAO}")
    print(f"  Ouvindo em http://127.0.0.1:{PORTA}  (mantenha esta janela aberta)")
    print("  One-X aberto:", "SIM" if _onex_aberto() else "NÃO — abra e faça login no Avaya one-X")
    print("=" * 64, flush=True)
    threading.Thread(target=_trabalhador, daemon=True, name="onex").start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
