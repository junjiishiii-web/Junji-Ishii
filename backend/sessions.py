"""
Isolamento de dados por sessao (usuario) para o modo web multiusuario.

O app antes guardava a SPEC/EEP carregada e o progresso da modelagem em
variaveis globais unicas do processo — funcionava bem para um unico usuario
local (app desktop), mas quebraria com varios colegas usando o servidor web
ao mesmo tempo (o upload de um sobrescreveria o do outro). Cada sessao tem
seu proprio estado, identificada por um cookie opaco emitido no primeiro
acesso.
"""
import secrets
import threading
import time

TTL_SEGUNDOS = 2 * 60 * 60  # sessoes inativas por mais de 2h sao descartadas

_sessoes = {}
_lock_global = threading.Lock()


class SessaoDados:
    def __init__(self):
        self.spec_bytes = None
        self.spec_empresas_bytes = None
        self.eep_bytes = None
        self.nome_spec = ""
        self.nome_eep = ""
        self.lock = threading.Lock()
        self.progresso = {
            "percentual": 0,
            "etapa": "Aguardando...",
            "concluido": False,
            "erro": None,
            "inicio": None,
            "elapsed": 0.0,
        }
        self.resultado = None
        self.ultimo_acesso = time.time()

    def atualizar_progresso(self, **kwargs):
        with self.lock:
            self.progresso.update(kwargs)
            if self.progresso["inicio"]:
                self.progresso["elapsed"] = time.time() - self.progresso["inicio"]

    def ler_progresso(self):
        with self.lock:
            self.progresso["elapsed"] = (
                time.time() - self.progresso["inicio"] if self.progresso["inicio"] and not self.progresso["concluido"] else self.progresso["elapsed"]
            )
            return dict(self.progresso)


def novo_session_id():
    return secrets.token_urlsafe(24)


def _purgar_expiradas():
    agora = time.time()
    expiradas = [sid for sid, s in _sessoes.items() if agora - s.ultimo_acesso > TTL_SEGUNDOS]
    for sid in expiradas:
        del _sessoes[sid]


def obter_ou_criar(session_id):
    with _lock_global:
        _purgar_expiradas()
        if session_id not in _sessoes:
            _sessoes[session_id] = SessaoDados()
        sessao = _sessoes[session_id]
        sessao.ultimo_acesso = time.time()
        return sessao


def contagem_ativa():
    with _lock_global:
        _purgar_expiradas()
        return len(_sessoes)
