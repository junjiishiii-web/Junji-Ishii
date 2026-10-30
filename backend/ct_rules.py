"""
Motor de geracao de Casos de Teste (CTs) aplicando as licoes L1-L14 da skill
de modelagem QA URA/BDD (Mutant / Claro CRN e TLV).

Este modulo e 100% deterministico: nada aqui depende de um LLM. Quando uma
classificacao exigiria julgamento contextual que a heuristica nao consegue
resolver com confianca, o item vira uma entrada em `revisao_necessaria` em vez
de virar um CT "chutado".
"""
import difflib
import functools
import re
from collections import deque

from spec_reader import normalizar_chave, resolver_destino

MAX_GHERKIN = 255

ABREVIACOES = [
    (r"\bChaveHabilitaCNPJAlfanumerico\b", "ChaveCNPJAlfa"),
    (r"\bindicadores 89,?\s*101\s*ou\s*91\b", "Ind89/101/91"),
    (r"\bprimeira consulta RTDM\b", "1a consulta RTDM"),
    (r"\barea cabeada\b", "AreaCabeada"),
    (r"\bcredito reprovado\b", "reprovado"),
    (r"\bcom ChaveHabilitaCNPJAlfanumerico Ativa\b", "com ChaveCNPJAlfa Ativa"),
]

HUBS_BLACKLIST = (
    "chute", "fallback", "global", "voltar", "stay", "rejeicao", "silencio",
    "timeout", "stay_mesmo", "rechamada", "nesse mesmo estado",
)

_ESTADO_NOVO_RE = re.compile(r"\bestado\s+novo\b", re.IGNORECASE)
_REJ_SIL_RE = re.compile(r"\bREJ\b|\bSIL\b|\bINV\b|\bINC\b|digitou algo diferente|ficou em sil[eê]ncio", re.IGNORECASE)


def _eh_transicao_rej_sil(condicao):
    return bool(_REJ_SIL_RE.search(condicao or ""))


_RAMO_ERRO_RE = re.compile(
    r"pela\s+\d|vez|[0-9]️?⃣|\[no input\]|sil[eê]ncio|menos que|algo diferente|n[aã]o confer|inv[aá]lid",
    re.IGNORECASE,
)


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\ufe0f\u20e3\u200d]+"
)


def _sem_emoji(txt):
    return re.sub(r"\s+", " ", _EMOJI_RE.sub(" ", str(txt or ""))).strip(" >-")


def _condicao_do_ct(alteracao, transicao_final):
    """(condicao especifica, contexto): a ULTIMA condicao do caminho de condicoes do CT ("A > B > C" -> "C") e as
    anteriores como contexto. Vem da alteracao ("... — condição: A > B > C") ou da transicao do CT."""
    texto = ""
    m = re.search(r"condi[cç][aã]o:\s*(.+)$", str(alteracao or ""), re.IGNORECASE | re.DOTALL)
    if m:
        texto = m.group(1)
    elif transicao_final is not None:
        texto = transicao_final.get("condicao") or ""
    partes = [_sem_emoji(x) for x in re.split(r"\s>\s", texto) if _sem_emoji(x)]
    if not partes:
        return "", []
    return partes[-1], partes[:-1]


_ERRO_BFS_RE = re.compile(
    r"tratativas?\s+de\s+erro|inv[aá]lid|\bmax\w*|terceira\s+vez|3[ªa]\s+vez|sil[eê]ncio|\bno[\s-]?input|nomatch|timeout|\b(?:rej|sil)\d",
    re.IGNORECASE,
)


def _eh_ramo_erro_bfs(condicao):
    """Condicao de erro/tentativas esgotadas: o caminho ATE um estado nao deve passar por ela (e atalho, nao jornada)."""
    return bool(_ERRO_BFS_RE.search(condicao or ""))


def _eh_ramo_erro(condicao):
    """Saida de erro/repeticao (por tentativa, silencio, entrada invalida): nao faz parte da jornada de ponta a ponta."""
    return _eh_transicao_rej_sil(condicao) or bool(_RAMO_ERRO_RE.search(condicao or ""))

BLOCO_PALETTE = [
    {"nome": "Navy", "header": "1F4E79", "fill": "DEEAF1"},
    {"nome": "Teal", "header": "006B6B", "fill": "D0ECEC"},
    {"nome": "Green", "header": "1E6B32", "fill": "D5F5E3"},
    {"nome": "Amber", "header": "B7770D", "fill": "FDEBD0"},
    {"nome": "Purple", "header": "5D4E75", "fill": "EDE8F5"},
    {"nome": "Slate", "header": "4A5568", "fill": "EDF2F7"},
    {"nome": "Indigo", "header": "3730A3", "fill": "E0E7FF"},
    {"nome": "Rose", "header": "9F1239", "fill": "FFE4E6"},
    {"nome": "Olive", "header": "5B6C44", "fill": "DDE8CC"},
]
REGRESSIVO_COR = {"nome": "Regressivo", "header": "7B241C", "fill": "FADBD8"}
SP_PENDENTE_FILL = "FFFFFF00"


def _aplicar_abreviacoes(texto):
    resultado = texto
    for padrao, curto in ABREVIACOES:
        resultado = re.sub(padrao, curto, resultado, flags=re.IGNORECASE)
    return resultado


def abreviar_gherkin(texto):
    """Abrevia termos conhecidos (L8) e, se ainda assim passar de 255 chars,
    trunca preservando a clausula Entao/Então quando possivel — mas o teto
    de 255 e RIGIDO (campo de nome/summary no XRAY/JIRA nao aceita mais que
    isso), entao, no caso raro em que ate a propria clausula Entao sozinha
    excede 255, ela tambem e cortada em vez de deixar o texto estourar."""
    resultado = _aplicar_abreviacoes(texto)
    if len(resultado) <= MAX_GHERKIN:
        return resultado

    marcador = None
    for candidato in (", Então ", ", Entao "):
        pos = resultado.rfind(candidato)
        if pos != -1:
            marcador = (pos, candidato)
            break

    if not marcador:
        return resultado[: MAX_GHERKIN - 1].rstrip() + "…"

    pos, candidato = marcador
    sufixo = resultado[pos:]
    prefixo = resultado[:pos]
    disponivel = MAX_GHERKIN - len(sufixo) - 1
    if disponivel > 0:
        return prefixo[:disponivel].rstrip() + "…" + sufixo
    return sufixo[: MAX_GHERKIN - 1].rstrip() + "…"


def montar_gherkin(prefixo, meio, sufixo):
    """Monta 'prefixo + meio + sufixo' garantindo <=255 chars (teto rigido,
    exigido pelo campo de nome/summary no XRAY/JIRA) — corta primeiro o meio
    (L8), e so no caso raro de prefixo+sufixo sozinhos ja excederem 255,
    corta tambem o sufixo (aceitando perder parte da clausula Entao em vez
    de estourar o limite)."""
    prefixo = _aplicar_abreviacoes(prefixo)
    meio = _aplicar_abreviacoes(meio)
    sufixo = _aplicar_abreviacoes(sufixo)
    total = prefixo + meio + sufixo
    if len(total) <= MAX_GHERKIN:
        return total
    disponivel = MAX_GHERKIN - len(prefixo) - len(sufixo) - 1
    if disponivel > 0:
        meio_curto = meio[:disponivel].rstrip() + "…"
        return prefixo + meio_curto + sufixo

    sem_meio = prefixo + sufixo
    excesso = len(sem_meio) - MAX_GHERKIN
    if excesso <= 0:
        return sem_meio
    if len(sufixo) > excesso + 1:
        sufixo_curto = sufixo[: len(sufixo) - excesso - 1].rstrip() + "…"
        return prefixo + sufixo_curto
    return sem_meio[: MAX_GHERKIN - 1].rstrip() + "…"


def extrair_restricoes_sessao(condicao_texto):
    """Mapeia termos de condicao para variaveis de sessao (evita contradicoes)."""
    txt = str(condicao_texto).lower()
    # Nomes de chave ("BasesConsultaMotorTecnico") e frases como "visita tecnica"/"motor tecnico" nao dizem
    # qual opcao de menu o cliente escolheu — sem isso a condicao parecia "MPL tecnico" e bloqueava o caminho.
    txt = re.sub(r"chaves?\s+[a-z0-9_]+", " ", txt)
    txt = re.sub(r"(?:visita|motor|suporte|atendimento|diagn[oó]stico)\s+t[eé]cnic[oa]", " ", txt)
    res = {}

    if "anisim" in txt or "ani sim" in txt:
        res["ani"] = "anisim"
    elif "aninao" in txt or "ani nao" in txt or "ani não" in txt or "ani não" in txt:
        res["ani"] = "aninao"

    if "tecnico" in txt or "técnico" in txt:
        res["mpl"] = "tecnico"
    elif "cancelamento" in txt:
        res["mpl"] = "cancelamento"
    elif "financeiro" in txt or "fatura" in txt or "pagamento" in txt or "debito" in txt:
        res["mpl"] = "financeiro"
    elif "outros" in txt:
        res["mpl"] = "outros"

    if "afterhours" in txt.replace(" ", "").replace("-", "") or "fora do horario" in txt or "after hours" in txt:
        if "nao" in txt.replace("ã", "a") or "desativ" in txt:
            res["afterhours"] = "nao_ah"
        else:
            res["afterhours"] = "ah"

    if "celular" in txt or "movel" in txt or "móvel" in txt:
        res["linha"] = "celular"
    elif "fixo" in txt or "fixa" in txt:
        res["linha"] = "fixo"

    if "protocolo valido" in txt or "protocolo válido" in txt:
        res["protocolo"] = "valido"
    elif "protocolo invalido" in txt or "protocolo inválido" in txt:
        res["protocolo"] = "invalido"

    if "inadimplente" in txt or "devedor" in txt:
        res["adimplencia"] = "devedor"
    elif "adimplente" in txt:
        res["adimplencia"] = "adimplente"

    return res


def verificar_conflito_sessao(existentes, novas):
    for k, v in novas.items():
        if k in existentes and existentes[k] != v:
            return True
    return False


def _is_hub(nome):
    low = nome.lower()
    return any(kw in low for kw in HUBS_BLACKLIST)


def _resolver_estado_aproximado(nome_bruto, estados_disponiveis):
    """Corrige pequenos erros de digitacao entre o nome citado na
    Versionamento/VersionamentoBI e o nome real da aba na SPEC (ex.:
    'BemVindo_TLVPosVendaClaroHDTV' vs a aba real 'BemVindo_TLVPosVendasClaroHDTV'
    — falta um 's'). So aceita quando ha EXATAMENTE UM candidato muito
    parecido (similaridade >= 0.92) — se houver ambiguidade (dois nomes
    parecidos igualmente proximos), nao arrisca advinhar e deixa cair no
    fluxo normal de "nao encontrado" pra revisao manual.
    """
    chave = normalizar_chave(nome_bruto)
    candidatos = {normalizar_chave(e): e for e in estados_disponiveis}
    proximos = difflib.get_close_matches(chave, candidatos.keys(), n=2, cutoff=0.92)
    if len(proximos) == 1:
        return candidatos[proximos[0]]
    return None


def _detectar_start_state(spec_model):
    """Acha o verdadeiro ponto de entrada do fluxo (raiz do grafo).

    Specs reais costumam ter MAIS de uma aba com nome parecido com "inicio"
    (ex.: 'Início' E 'MigraWhatsInicio') — uma e o ponto de entrada de
    verdade, a outra e so um estado no MEIO do fluxo que por acaso tem
    "Inicio" no nome. Escolher a primeira por ordem alfabetica/de aba (como o
    codigo antigo fazia) pode pegar a errada, e ai todo estado que só é
    alcançável ANTES dela no fluxo real (ex.: 'Início' -> ... ->
    'MigraWhatsInicio') fica permanentemente "sem caminho de entrada" no BFS,
    mesmo estando perfeitamente conectado ao fluxo. Por isso, entre os
    candidatos por nome, preferimos o que não recebe NENHUMA transição de
    outro estado (a raiz de verdade do grafo).
    """
    cache_key = "_start_state_resolvido"
    if cache_key in spec_model:
        return spec_model[cache_key]

    lista_abas = spec_model["lista_abas"]
    mapa_rotas = spec_model["mapa_rotas"]
    estados = spec_model["estados"]

    candidatos = [a for a in lista_abas if any(k in a.lower() for k in ("inicio", "início", "start"))]
    if not candidatos:
        candidatos = lista_abas[:1]

    resolvido = candidatos[0] if candidatos else None
    if len(candidatos) > 1:
        tem_entrada = set()
        for dados in estados.values():
            for t in dados.get("transicoes", []):
                dest = resolver_destino(mapa_rotas, t["destino"])
                if dest:
                    tem_entrada.add(dest)
        sem_entrada = [c for c in candidatos if c not in tem_entrada]
        if sem_entrada:
            resolvido = sem_entrada[0]

    spec_model[cache_key] = resolvido
    return resolvido


_VEIO_DO_ESTADO_RE = re.compile(r"(?:veio|vindo)\s+d[oae]\s+(?:estado|ura)", re.IGNORECASE)
_URA_EXTERNA_RE = re.compile(r"ura\s+identificadora", re.IGNORECASE)
_CACHE_PREFIXOS_CRUZADOS = {}


def _prefixos_cruzados(spec_model):
    """Prefixos (grupos) do _Start_ que sao hand-off de outra URA: o grupo que tem condicoes
    "Veio do estado X" (ex.: "Entrada normal > Atendimento Televendas > Veio do estado ...")."""
    chave = id(spec_model)
    if chave not in _CACHE_PREFIXOS_CRUZADOS:
        start = _detectar_start_state(spec_model)
        prefixos = set()
        for t in (spec_model["estados"].get(start, {}).get("transicoes", []) if start else []):
            if _VEIO_DO_ESTADO_RE.search(t.get("condicao") or ""):
                path = tuple(t.get("path") or [])
                if len(path) > 1:
                    prefixos.add(path[:-1])
        _CACHE_PREFIXOS_CRUZADOS.clear()
        _CACHE_PREFIXOS_CRUZADOS[chave] = prefixos
    return _CACHE_PREFIXOS_CRUZADOS[chave]


def _eh_entrada_cruzada(t, spec_model):
    """Transicao do _Start_ que e um HAND-OFF vindo de OUTRA URA (ex.: "Atendimento Televendas >
    Veio do estado MenuRentabilizacao" numa SPEC da CRN), e nao a entrada nativa dessa URA
    (ex.: "Entrada normal > Entrou pelo DNIS 0800 ..."). Vale tambem para as irmas do mesmo grupo
    (o "Else" do grupo "Atendimento Televendas") e para "URA IDENTIFICADORA"."""
    cond = t.get("condicao") or ""
    if _VEIO_DO_ESTADO_RE.search(cond) or _URA_EXTERNA_RE.search(cond):
        return True
    path = tuple(t.get("path") or [])
    return any(len(path) > len(pref) and path[: len(pref)] == pref for pref in _prefixos_cruzados(spec_model))


_PADRAO_BASE_RE = re.compile(r"\belse\b|sen[aã]o|caso contr[aá]rio|c[oó]digo base|default|demais|massivo", re.IGNORECASE)
_CHAVE_OFF_RE = re.compile(r"desativad|desligad|desabilitad|inativ|\bn[aã]o\b", re.IGNORECASE)
_CHAVE_ON_RE = re.compile(r"ativad|habilitad|ligad", re.IGNORECASE)
_ESPECIFICO_RE = re.compile(r"gaming|piloto|vip|ouro|rubi|black|premium|segmento|rgc|pj|empresa", re.IGNORECASE)


def _pontuar_transicao(t):
    """Quanto MAIOR, mais dificil/especifica a transicao. Usada para escolher o caminho mais FACIL
    ate um estado por onde so se PASSA (o ponto de validacao fica adiante): poucas condicionais,
    ramo padrao ("Else"/"Codigo base"/"Demais"), chaves desativadas, sem segmentos/pilotos."""
    cond = t.get("condicao") or ""
    path = t.get("path") or [cond]
    pontos = len(path)
    if _PADRAO_BASE_RE.search(cond):
        pontos -= 3
    if _CHAVE_OFF_RE.search(cond):
        pontos -= 2
    elif _CHAVE_ON_RE.search(cond):
        pontos += 2
    pontos += 3 * len(_ESPECIFICO_RE.findall(cond))
    return pontos


# Nome de chave em CamelCase ("DNISPushNotificationNaoCabeadaAfDTMF1", "DDDHabilitaSMSCreditoReprovadoNaoCabeado"):
# diz qual chave esta ligada, nao a situacao do cliente — fica fora dos tracos do cenario.
_RX_NOME_CHAVE = re.compile(r"\b\w*[a-z][A-Z]\w*[a-z][A-Z]\w*\b")
_CONFLITOS_CENARIO = (("cred_ok", "cred_nok"), ("movel_sim", "movel_nao"), ("cab_sim", "cab_nao"))
_RX_TRANSICAO_ERRO = re.compile(r"\bmax\w*\s*(?:erro|err|sil|rej|inv|tent)|\b(?:rej|inv|sil|noinput|nomatch)\b|timeout|sil[eê]ncio|inv[aá]lid", re.IGNORECASE)


def _texto_transicao(t):
    return " ".join(t.get("path") or [t.get("condicao") or ""])


@functools.lru_cache(maxsize=20000)
def _feat_cenario(txt):
    """Tracos de um cenario do EEP ou de uma condicao da SPEC: credito, cliente movel, cabeamento..."""
    # a virgula separa condicoes: "ligou de celular, nao passou pelo estado X" nao e "celular nao"
    n = normalizar_chave(re.sub(r"[,;]", " sep ", _RX_NOME_CHAVE.sub(" ", str(txt or "")))).replace("_", " ")
    f = set()
    if re.search(r"reprovad", n): f.add("cred_nok")
    elif re.search(r"aprovad", n): f.add("cred_ok")
    if re.search(r"nao (?:e )?(?:cliente )?(?:claro )?(?:movel|celular)|movel nao|celular nao|numero movel nao", n): f.add("movel_nao")
    elif re.search(r"movel|celular", n): f.add("movel_sim")
    if re.search(r"nao cabead|cablingtype 0", n): f.add("cab_nao")
    elif re.search(r"cabead|cablingtype [12]", n): f.add("cab_sim")
    if "timeout" in n: f.add("timeout")
    if "brownfield" in n: f.add("brownfield")
    if re.search(r"alto valor|servicegroupid (?!diferente)", n): f.add("altovalor")
    return frozenset(f)


def _conflitos_cenario(f_a, f_b):
    return sum(1 for a, b in _CONFLITOS_CENARIO if (a in f_a and b in f_b) or (b in f_a and a in f_b))


def bfs_caminho_entrada(spec_model, destino_nome, perfil_entrada="aninao", restricoes_extra=None, modo_entrada="nativa", cenario=None,
                        inicio=None, bloqueados=None):
    """BFS com session tracking ate o estado de destino, evitando ciclos/hubs.

    Retorna (caminho, perfil_efetivo). Em specs reais grandes, o UNICO
    caminho estrutural ate um estado as vezes passa por uma chave/condicao
    que so existe do lado ANISIM (ou so do lado ANINAO) — mesmo quando o
    perfil pedido (perfil_entrada) foi o oposto (chutado a partir da
    transicao/estado que gerou o CT, nao do caminho de entrada em si). Sem
    fallback, esse unico caminho valido e rejeitado por "conflito de sessao"
    e o estado fica com 0 CTs mesmo sendo alcancavel. Por isso, so depois de
    esgotar o perfil pedido (com e sem bloqueio de hub) e que tentamos o
    perfil oposto — perfil_efetivo avisa o chamador qual perfil realmente
    funcionou, pra rotular o CT (ANINÃO/ANISIM) de forma condizente com o
    caminho de fato gerado.

    cenario (tracos de _feat_cenario, ex.: credito reprovado + nao cabeado): primeiro so por ramos que nao
    contradizem o cenario, preferindo os que o citam; sem caminho assim, cai na busca de sempre.
    """
    lista_abas = spec_model["lista_abas"]
    mapa_rotas = spec_model["mapa_rotas"]
    estados = spec_model["estados"]
    cenario = frozenset(cenario or ())
    bloqueados = frozenset(bloqueados or ())

    chave_cache = (destino_nome, perfil_entrada, tuple(sorted((restricoes_extra or {}).items())), modo_entrada, tuple(sorted(cenario)),
                   inicio, tuple(sorted(bloqueados)))
    cache_bfs = spec_model.setdefault("_bfs_cache", {})
    if chave_cache in cache_bfs:
        cam_c, perfil_c, hops_c = cache_bfs[chave_cache]
        if cam_c:
            # o mesmo caminho de estados pode ter saltos diferentes conforme o cenario: os steps usam os desta busca
            spec_model.setdefault("_hops_cache", {})[(perfil_c, tuple(cam_c))] = hops_c
        return list(cam_c), perfil_c

    start_state = inicio or _detectar_start_state(spec_model)
    if not start_state:
        return [], perfil_entrada
    if start_state == destino_nome:
        return [start_state], perfil_entrada

    extras_sem_ani = dict(restricoes_extra or {})
    extras_sem_ani.pop("ani", None)

    # saidas de cada estado ja resolvidas (destino real, restricoes, pontuacao, tracos): calculadas uma vez por SPEC
    cache_saidas = spec_model.setdefault("_saidas_bfs", {})

    def _saidas(atual):
        if atual not in cache_saidas:
            cache_saidas[atual] = [
                (t, resolver_destino(mapa_rotas, t["destino"]), extrair_restricoes_sessao(t["condicao"]),
                 _pontuar_transicao(t), _feat_cenario(_texto_transicao(t)))
                for t in estados.get(atual, {}).get("transicoes", [])
            ]
        return cache_saidas[atual]

    def _busca(perfil_ani, bloquear_hubs, filtro_entrada=None, so_compativeis=False, sem_erros=False):
        restricoes_iniciais = {"ani": perfil_ani}
        restricoes_iniciais.update(extras_sem_ani)
        fila = deque([([start_state], restricoes_iniciais, [])])
        visitados = {start_state} | set(bloqueados)
        while fila:
            caminho, restricoes, hops = fila.popleft()
            atual = caminho[-1]
            if atual == destino_nome:
                return caminho, hops
            melhores, ordem = {}, []
            for t, real_dest, novas, pontos_t, f_t in _saidas(atual):
                if atual == start_state and filtro_entrada and not inicio:
                    # primeira transicao: entrada nativa da URA x hand-off vindo de outra URA
                    if (filtro_entrada == "nativa") == _eh_entrada_cruzada(t, spec_model):
                        continue
                if not real_dest or real_dest in visitados:
                    continue
                if sem_erros and _eh_ramo_erro_bfs(t.get("condicao")):
                    continue
                if bloquear_hubs and _is_hub(real_dest) and real_dest != destino_nome:
                    continue
                if verificar_conflito_sessao(restricoes, novas):
                    continue
                if so_compativeis and _conflitos_cenario(cenario, f_t):
                    continue
                pontos = (-len(cenario & f_t) if cenario else 0, pontos_t)
                if real_dest not in melhores:
                    ordem.append(real_dest)
                    melhores[real_dest] = (pontos, t, novas)
                elif pontos < melhores[real_dest][0]:
                    melhores[real_dest] = (pontos, t, novas)
            for real_dest in ordem:
                _pontos, t, novas = melhores[real_dest]
                atualizadas = dict(restricoes)
                atualizadas.update(novas)
                visitados.add(real_dest)
                fila.append((caminho + [real_dest], atualizadas, hops + [t]))
        return [], []

    def _busca_estendida(perfil_ani, bloquear_hubs, filtro_entrada=None, so_compativeis=False):
        """Como _busca (sem ramos de erro), mas guarda a SESSAO junto do estado: o mesmo estado pode ser alcancado por
        saltos com restricoes diferentes (ex.: linha fixa x movel) e so um deles permite seguir adiante."""
        restricoes_iniciais = {"ani": perfil_ani}
        restricoes_iniciais.update(extras_sem_ani)
        fila = deque([([start_state], restricoes_iniciais, [])])
        vistos = {(start_state, tuple(sorted(restricoes_iniciais.items())))}
        expansoes = 0
        while fila and expansoes < 40000:
            caminho, restricoes, hops = fila.popleft()
            atual = caminho[-1]
            if atual == destino_nome:
                return caminho, hops
            expansoes += 1
            saidas = []
            for t, real_dest, novas, pontos_t, f_t in _saidas(atual):
                if atual == start_state and filtro_entrada and not inicio:
                    if (filtro_entrada == "nativa") == _eh_entrada_cruzada(t, spec_model):
                        continue
                if not real_dest or real_dest in caminho or real_dest in bloqueados:
                    continue
                if _eh_ramo_erro_bfs(t.get("condicao")):
                    continue
                if bloquear_hubs and _is_hub(real_dest) and real_dest != destino_nome:
                    continue
                if verificar_conflito_sessao(restricoes, novas):
                    continue
                if so_compativeis and _conflitos_cenario(cenario, f_t):
                    continue
                saidas.append(((-len(cenario & f_t) if cenario else 0, pontos_t), t, real_dest, novas))
            for _pontos, t, real_dest, novas in sorted(saidas, key=lambda x: x[0]):
                atualizadas = dict(restricoes)
                atualizadas.update(novas)
                chave_visto = (real_dest, tuple(sorted(atualizadas.items())))
                if chave_visto in vistos:
                    continue
                vistos.add(chave_visto)
                fila.append((caminho + [real_dest], atualizadas, hops + [t]))
        return [], []

    perfil_alternativo = "anisim" if perfil_entrada == "aninao" else "aninao"
    # Por padrao prefere a entrada NATIVA da URA; so cai num hand-off de outra URA se nao houver outra
    # saida. modo "cruzada" forca o caminho que entra por outra URA (regressao de entrada alternativa).
    filtros = ("nativa", None) if modo_entrada == "nativa" else ("cruzada",)
    for so_compativeis in ((True, False) if cenario else (False,)):
        for filtro in filtros:
            for perfil_ani in (perfil_entrada, perfil_alternativo):
                for bloquear_hubs, sem_erros, estendida in (
                    (True, True, False), (False, True, False), (True, True, True), (False, True, True),
                    (True, False, False), (False, False, False),
                ):
                    if estendida:
                        caminho, hops = _busca_estendida(perfil_ani, bloquear_hubs, filtro, so_compativeis)
                    else:
                        caminho, hops = _busca(perfil_ani, bloquear_hubs, filtro, so_compativeis, sem_erros)
                    if caminho:
                        # guarda as transicoes escolhidas em cada salto: os steps do CT usam EXATAMENTE elas
                        spec_model.setdefault("_hops_cache", {})[(perfil_ani, tuple(caminho))] = hops
                        cache_bfs[chave_cache] = (list(caminho), perfil_ani, hops)
                        return caminho, perfil_ani
    cache_bfs[chave_cache] = ([], perfil_entrada, [])
    return [], perfil_entrada


def _achar_prompt_por_id(prompts, alvo_norm):
    # Igualdade exata primeiro: um alvo curto como "INI" nao pode casar por
    # substring com outro prompt tipo "DTMF_INI_MAXSIL" que venha antes.
    exato = next((p for p in prompts if normalizar_chave(p["id"]) == alvo_norm), None)
    if exato:
        return exato
    return next((p for p in prompts if alvo_norm in normalizar_chave(p["id"])), None)


def _match_prompt(state_data, prox_prompt_target):
    prompts = state_data.get("prompts", [])
    if not prompts:
        return None
    if prox_prompt_target and prox_prompt_target.lower() not in ("", "nan", "- sem prompt -"):
        casado = _achar_prompt_por_id(prompts, normalizar_chave(prox_prompt_target))
        if casado:
            return casado
    return prompts[0]


def _candidatos_prompt_transicao(spec_model, estado_nome, t):
    """Prompts que a transicao realmente referencia via "Proximo Prompt":
    primeiro no estado atual, depois (se for outro estado) no de destino —
    sem o fallback de prompts[0] do _match_prompt (que e so pra escolher o
    que mostrar num step generico, nao pra atribuir prompt/SP)."""
    alvo = (t.get("prox_prompt") or "").strip()
    if not alvo or alvo.lower() in ("nan", "- sem prompt -"):
        return
    alvo_norm = normalizar_chave(alvo)
    destino_real = resolver_destino(spec_model["mapa_rotas"], t.get("destino"))
    # "Proximo Prompt" e o prompt tocado no estado de DESTINO (ex.: "Certo_A"
    # existe em TransferMaisProtocolo, "MaxErro_DTMF" em Transfer); quando a
    # transicao fica no mesmo estado (REJ1, SIL1...), o dono e o proprio estado.
    donos = []
    if destino_real and destino_real != estado_nome:
        donos.append(destino_real)
    donos.append(estado_nome)
    for dono in donos:
        prompt = _achar_prompt_por_id(spec_model["estados"].get(dono, {}).get("prompts", []), alvo_norm)
        if prompt:
            yield prompt, dono


def _sp_efetivo_transicao(spec_model, estado_nome, t):
    """SP efetivo de uma transicao: o dela mesma, ou — quando ela nao tem
    nenhum — o do PROMPT que ela aciona (coluna "Proximo Prompt").

    Specs reais costumam marcar o SP nos prompts de retentativa (REJ1,
    REJ2, SIL1, SIL2, INI), nao na transicao que leva ate eles — ex.: a
    transicao "REJ > 1ª vez" tem sp=None, mas referencia o prompt "REJ1",
    que TEM um SP marcado. Sem essa ligacao, o filtro de "SP novo" via
    VersionamentoBI (gerar_cts_tipo_a) descarta essas transicoes como "sem
    sinal de que fazem parte desta versao", mesmo quando o SP delas esta
    corretamente publicado — e o proprio SP nunca aparece coberto em
    BI_Marcacoes, porque nenhum CT jamais o referencia.
    """
    if t.get("sp"):
        return t["sp"]
    for prompt, _dono in _candidatos_prompt_transicao(spec_model, estado_nome, t):
        if prompt.get("sp"):
            return prompt["sp"]
    return None


_TENTATIVA_RE = re.compile(r"^\s*(\d+)\s*(?:ª|º|°|a|o)?\s*(?:vez(?:es)?|x)\s*$", re.IGNORECASE)
_SIL_RE = re.compile(r"\bSIL\b|sil[eê]ncio", re.IGNORECASE)


def _chave_grupo_retentativa(t):
    """Se a transicao e a N-esima tentativa de uma escada de REJ ou SIL
    (ex.: "Usuário digitou algo diferente (REJ) > 2ª vez"), devolve
    (chave_do_grupo, N); senao None. As tentativas da mesma escada sao uma
    sequencia unica de uma mesma chamada (1ª, 2ª, ... ate sair do estado) e
    cabem no MESMO CT."""
    path = t.get("path") or []
    if len(path) < 2 or not _eh_transicao_rej_sil(t.get("condicao")):
        return None
    m = _TENTATIVA_RE.match(path[-1])
    if not m:
        return None
    return tuple(normalizar_chave(p) for p in path[:-1]), int(m.group(1))


_INC_RE = re.compile(r"\bINC\b|incomplet", re.IGNORECASE)
_INV_RE = re.compile(r"\bINV\b", re.IGNORECASE)


def _rotulo_tipo_retentativa(condicao):
    if _SIL_RE.search(condicao):
        return "Ficar em silêncio (SIL)"
    if _INC_RE.search(condicao):
        return "Digitar sequência incompleta (INC)"
    if _INV_RE.search(condicao):
        return "Digitar valor inválido (INV)"
    return "Digitar opção inválida (REJ)"


_FAMILIA_PROMPT_RE = re.compile(r"(?<![A-Za-z])(INI|REJ\d?|SIL\d?|RPT\d?)(?![A-Za-z])")


def _texto_exibicao_prompt(spec_model, estado_nome, prompt, condicao=""):
    """Prompt que o cliente OUVE. Quando o prompt do estado e so um trecho de uma montagem por concat
    (ex.: "INI" = "Ok, vamo la! Qual dessas opcoes aqui te ajuda?" + opcoes TEC/FIN/CMP...), usa o
    texto completo do exemplo da SPEC ("EXEMPLO 1: DE INI SEM CLARO GAMING")."""
    if not prompt:
        return None
    exemplos = (spec_model["estados"].get(estado_nome) or {}).get("concat_exemplos") or []
    if not exemplos:
        return prompt.get("texto")
    familias = _FAMILIA_PROMPT_RE.findall(prompt["id"])
    if not familias:
        return prompt.get("texto")
    familia = familias[-1].upper()
    com_gaming = bool(re.search(r"gaming", condicao or "", re.IGNORECASE)) and not re.search(r"desativad", condicao or "", re.IGNORECASE)
    candidatos = [e for e in exemplos if re.search(rf"\bDE\s+{re.escape(familia)}\b", e["titulo"], re.IGNORECASE)]
    if not candidatos:
        return prompt.get("texto")
    def _contexto_ok(e):
        t = e["titulo"].upper()
        if "COM CLARO GAMING" in t:
            return com_gaming
        if "SEM CLARO GAMING" in t:
            return not com_gaming
        return True
    escolhido = next((e for e in candidatos if _contexto_ok(e)), candidatos[0])
    return escolhido["texto"]


_INTERATIVO_RE = re.compile(r"\bdtmf\b|digitou|tecla", re.IGNORECASE)
_ELSE_RE = re.compile(r"\belse\b|caso contr[aá]rio", re.IGNORECASE)


_TERMINAL_RE = re.compile(r"^(?:transfer|_end_)", re.IGNORECASE)


_NEGATIVO_RE = re.compile(
    r"inv[aá]lid|erro|falha|\bn[aã]o\b|recus|\bsair\b|bloque|timeout|sil[eê]ncio|rejeit|desist|cancel|desconhec|sem resposta|max(?:imo)?\b",
    re.IGNORECASE,
)
_POSITIVO_RE = re.compile(r"v[aá]lid|sucesso|\bsim\b|confirm|correto|aceit|titular|eleg[ií]vel|\bok\b|continu|identificou|encontrou", re.IGNORECASE)


def _distancia_terminal(spec_model, inicio, visitados, limite=25):
    """Saltos de `inicio` ate uma transferencia/fim (estado sem saida) pelos ramos que NAO sao erro/silencio/
    rejeicao — atravessa estados de coleta de dado e menus, porque o CT vai de ponta a ponta. None se nao ha."""
    from collections import deque

    cache = spec_model.setdefault("_dist_cache", {})
    if inicio in cache:
        return cache[inicio]
    mapa = spec_model["mapa_rotas"]
    estados = spec_model["estados"]
    fila = deque([(inicio, 0)])
    vistos = {inicio}
    resultado = None
    while fila:
        estado, d = fila.popleft()
        dados = estados.get(estado)
        if _TERMINAL_RE.match(estado) or (dados is not None and not dados.get("transicoes")):
            resultado = d
            break
        if d >= limite or dados is None:
            continue
        for t in dados.get("transicoes", []):
            if _eh_ramo_erro(t["condicao"]):
                continue
            dest = resolver_destino(mapa, t["destino"])
            if dest and dest not in vistos:
                vistos.add(dest)
                fila.append((dest, d + 1))
    cache[inicio] = resultado
    return resultado


def _steps_jornada(spec_model, estado_atual, visitados, limite=25):
    """Continua a jornada DE PONTA A PONTA a partir do estado em que o CT acabou: segue o caminho "feliz" da SPEC
    — passando por estados de coleta de dado e menus — ate uma transferencia, _End_ ou estado sem saida. Em cada
    estado escolhe a saida que nao e erro/silencio/rejeicao, preferindo condicoes positivas (valido, sucesso, sim...)
    e a que chega mais rapido ao desfecho; empate: a mais facil."""
    steps = []
    atual = estado_atual
    for _ in range(limite):
        dados = spec_model["estados"].get(atual)
        if not dados or _TERMINAL_RE.match(atual):
            break
        candidatos = []
        for t in dados.get("transicoes", []):
            if _eh_ramo_erro(t["condicao"]):
                continue
            destino = resolver_destino(spec_model["mapa_rotas"], t["destino"])
            if destino and destino != atual and destino not in visitados:
                candidatos.append((t, destino))
        if not candidatos:
            break
        pontuados = []
        for idx_c, (tc, dc) in enumerate(candidatos):
            dist = _distancia_terminal(spec_model, dc, visitados | {atual})
            neg = len(_NEGATIVO_RE.findall(tc["condicao"] or "")) - len(_POSITIVO_RE.findall(tc["condicao"] or ""))
            pontuados.append((neg, (dist if dist is not None else 99), _pontuar_transicao(tc), 0 if _ELSE_RE.search(tc["condicao"]) else 1, idx_c))
        melhor = min(pontuados)
        t, destino = candidatos[melhor[4]]
        sp_t = _sp_efetivo_transicao(spec_model, atual, t)
        prompt, _dono = next(_candidatos_prompt_transicao(spec_model, atual, t), (None, None))
        prompt_id = prompt["id"] if prompt else "—"
        prompt_texto = (_texto_exibicao_prompt(spec_model, destino, prompt, t["condicao"]) or "—") if prompt else "—"
        sp_prompt = _sp_prompt_novo(spec_model, prompt, sp_t)
        marcas = ", ".join(f"{x[0]}={x[1]}" for x in (sp_t, sp_prompt) if x)
        if marcas:
            resultado = marcas + (f" — {prompt_texto}" if prompt_texto != "—" else "")
        else:
            resultado = prompt_texto
        passo_j = {
            "step_num": 0,
            "acao": _acao_para_step(1, t["condicao"], "aninao") + (f" ➜ {t.get('handoff_txt') or 'MIGRAÇÃO SPEC ' + t['handoff']}" if t.get("handoff") else ""),
            "estado": destino,
            "prompt_id": prompt_id,
            "prompt_texto": prompt_texto,
            "sp": sp_t,
            "sp_prompt": sp_prompt,
            "resultado": resultado,
            "entradas": list(t.get("entradas") or []),
        }
        if spec_model["estados"].get(destino, {}).get("spec") and spec_model.get("_specs"):
            passo_j["spec"] = spec_model["estados"][destino]["spec"]
        steps.append(passo_j)
        visitados.add(destino)
        atual = destino
    return steps


def _sp_prompt_novo(spec_model, prompt, sp_transicao):
    """SP do PROMPT (ex.: spp=2476 do INI_MP) quando e uma marcacao NOVA do projeto e e diferente do SP
    da transicao: o prompt tambem marca quando toca, e o CT precisa conferir os dois."""
    if not prompt or not prompt.get("sp"):
        return None
    sp = prompt["sp"]
    if sp == sp_transicao or sp[1] not in (spec_model.get("_sps_novos") or ()):
        return None
    return sp


def _step_retentativa(spec_model, estado_nome, t, sp_t):
    """Step de uma tentativa de REJ/SIL: mostra o prompt de retentativa
    (REJ1, REJ2, SIL1, SIL2, ... ou o prompt de saida da ultima tentativa),
    com seu texto e SP, e pra onde a chamada segue."""
    prompt, dono = next(_candidatos_prompt_transicao(spec_model, estado_nome, t), (None, None))
    prompt_id = prompt["id"] if prompt else "—"
    prompt_texto = (_texto_exibicao_prompt(spec_model, dono or estado_nome, prompt, "") or "—") if prompt else "—"
    path = t.get("path") or [t["condicao"]]
    folha = path[-1]
    acao = f"{_rotulo_tipo_retentativa(t['condicao'])} — {folha}"

    destino_real = resolver_destino(spec_model["mapa_rotas"], t.get("destino"))
    destino_txt = f"segue para {destino_real}" if destino_real and destino_real != estado_nome else "permanece no estado"
    sp_prompt = _sp_prompt_novo(spec_model, prompt, sp_t)
    marcas = ", ".join(f"{x[0]}={x[1]}" for x in (sp_t, sp_prompt) if x)
    if marcas:
        resultado = marcas + (f" — {prompt_texto}" if prompt_texto != "—" else "")
    else:
        resultado = prompt_texto
    return {
        "step_num": 0,
        "acao": acao,
        "estado": dono or estado_nome,
        "prompt_id": prompt_id,
        "prompt_texto": prompt_texto,
        "sp": sp_t,
        "sp_prompt": sp_prompt,
        "resultado": f"{resultado} | {destino_txt}",
    }


def _step_transicao(spec_model, estado_nome, t, sp_t, perfil):
    """Step da ACAO que dispara uma transicao quando o CT nao chega a trocar de estado
    (destino "Mesmo Estado", pseudo-destino como "Seguir resultados de ..."): sem ele o CT
    mostraria o SP mas nao a acao que o gera (ex.: digitar * para marcar o spt)."""
    state_data = spec_model["estados"].get(estado_nome, {})
    alvo = (t.get("prox_prompt") or "").strip()
    prompt = None
    if alvo and alvo.lower() not in ("nan", "- sem prompt -"):
        prompt = _achar_prompt_por_id(state_data.get("prompts", []), normalizar_chave(alvo))
    texto = prompt["texto"] if prompt and prompt.get("texto") else None
    destino_bruto = (t.get("destino") or "").strip()
    destino_real = resolver_destino(spec_model["mapa_rotas"], destino_bruto)
    if destino_real and destino_real != estado_nome:
        destino_txt = f"segue para {destino_real}"
    elif destino_real == estado_nome or destino_bruto.lower().startswith("mesmo"):
        destino_txt = "permanece no estado"
    elif destino_bruto:
        destino_txt = f"segue conforme a SPEC: {destino_bruto}"
    else:
        destino_txt = ""
    if sp_t:
        marcado = f"{sp_t[0]}={sp_t[1]}" + (f" — {texto}" if texto else "")
    else:
        marcado = texto or ""
    resultado = " | ".join(x for x in (marcado, destino_txt) if x) or "—"
    return {
        "step_num": 0,
        "acao": _acao_para_step(1, t["condicao"], perfil),
        "estado": estado_nome,
        "prompt_id": prompt["id"] if prompt else "—",
        "prompt_texto": texto or "—",
        "sp": sp_t,
        "resultado": resultado,
    }


_CHAVE_DESATIVADA_RE = re.compile(
    r"chave\s+([A-Za-z][A-Za-z0-9_]{4,})\s+(?:desativad\w*|desligad\w*|inativ\w*|desabilitad\w*|n[aã]o\s+ativ\w*)",
    re.IGNORECASE,
)
_ALT_CONCAT_RE = re.compile(r"concat", re.IGNORECASE)
_FAMILIA_CONCAT_RE = re.compile(r"(?<![A-Za-z])(REJ|RPT|SIL)\s*(\d?)(?![A-Za-z])", re.IGNORECASE)
_TOKEN_PROMPT_RE = re.compile(r"\*_?([A-Za-z0-9]+(?:_[A-Za-z0-9]+)*)_?\*?")
_CHAVE_RE = re.compile(r"chaves?\s+([A-Za-z][A-Za-z0-9_]{5,})", re.IGNORECASE)


def _dicas_alteracao(alteracao):
    """O que o changelog cita explicitamente: prompts (ex.: "*_SupeitaDeOutage_Cob" -> a parte
    depois de "*_") e chaves ("chave BasesHabilitaSmartVT"). Servem para testar SO o que mudou
    quando nao ha ScriptPoint novo para guiar."""
    texto = alteracao or ""
    prompts = {normalizar_chave(m.group(1)).strip("_") for m in _TOKEN_PROMPT_RE.finditer(texto)}
    prompts = {p for p in prompts if len(p) >= 4}
    chaves = {normalizar_chave(m.group(1)) for m in _CHAVE_RE.finditer(texto)}
    dtmfs = {m.group(1) for m in re.finditer(r"dtmf\s*(\d)", texto, re.IGNORECASE)}
    return prompts, chaves, dtmfs


def _transicao_casa_dicas(t, dicas):
    prompts, chaves, dtmfs = dicas
    alvo_prompt = normalizar_chave(t.get("prox_prompt") or "")
    if alvo_prompt and any(p in alvo_prompt for p in prompts):
        return True
    cond = normalizar_chave(t.get("condicao") or "")
    if any(c in cond for c in chaves):
        return True
    return any(re.search(rf"dtmf_?{d}(?!\d)", cond) for d in dtmfs)


# Condições do caminho que dependem da massa (cliente, chaves, base, crédito...), e não da tecla.
_RX_COND_MASSA = re.compile(
    r"chave|dnis|ddd|segment|client|cr[eé]dit|score|cabl|cabead|mailing|rechamad|adimpl|inadimpl|m[oó]vel|celular|fixo|"
    r"\bcep\b|cpf|cnpj|contrato|plano|produto|\bbase\b|servicegroup|rtdm|afterhours|hor[aá]rio|protocolo|\bmpl\b|"
    r"cadastr|identific|ani\b|elegiv|pilot|perfil|indicador|recencia|rec[eê]ncia|bloque|suspens|ativ[ao]|desativ",
    re.IGNORECASE,
)
_RX_SO_TECLA = re.compile(r"^\s*(dtmf|digit\w*|tecl\w*|op[cç][aã]o|selecion\w*)?\s*[:=]?\s*[\d*#]{1,3}\s*$", re.IGNORECASE)


def _condicoes_da_massa(perfil, restricoes, tags, extras, steps):
    """Como a massa do CT precisa estar: perfil do ANI, restrições da sessão, as condições do cenário
    (ex.: tabela do EEP — grupo, critério, cliente móvel, crédito, target) e as condições da SPEC no
    caminho que dependem do cliente/chaves (não as que são só uma tecla)."""
    itens = [{"rotulo": "Perfil do ANI",
              "valor": "ANI Não — ligar de um número que NÃO identifica o cliente" if perfil == "aninao"
              else "ANI Sim — ligar do número cadastrado para o cliente"}]
    for chave, rotulo in tags.items():
        if restricoes and chave in restricoes:
            itens.append({"rotulo": rotulo, "valor": str(restricoes[chave])})
    for k, v in extras or []:
        if str(v or "").strip():
            itens.append({"rotulo": str(k).strip(), "valor": str(v).strip()})
    vistos = {i["valor"].lower() for i in itens}
    cenario = " ".join(str(v) for _k, v in (extras or [])).lower()
    for st in steps or []:
        acao = str(st.get("acao") or "")
        m = re.search(r"\((.*)\)\s*$", acao)
        if not m:
            continue
        for cond in re.split(r"\s+>\s+", m.group(1)):
            cond = cond.strip()
            if not cond or _RX_SO_TECLA.match(cond) or not _RX_COND_MASSA.search(cond) or cond.lower() in vistos:
                continue
            if re.fullmatch(r"ani\s+(sim|n[aã]o)", cond, re.IGNORECASE):   # já está no "Perfil do ANI"
                continue
            vistos.add(cond.lower())
            rotulo = f"Condição em {st.get('estado') or '—'}"
            if _diverge_do_cenario(cenario, cond.lower()):
                rotulo = f"⚠️ Divergente do cenário — {rotulo}"
            itens.append({"rotulo": rotulo, "valor": cond})
    return itens


# ── Massa POR CT: os dados que o cliente/API precisam ter, lidos das condicoes do caminho da SPEC
_ORDEM_MASSA = (
    "Segmento", "StatusContrato", "Documento", "Produto / linha", "Quantidade", "Chaves (parâmetros)",
    "Dado / retorno de API", "API / serviço", "Base / mailing", "Recência / prazo", "Horário / data",
)
_RX_IGNORAR_FRAG = re.compile(
    r"^(else|primeir\w+ vez|segund\w+ vez|terceir\w+ vez|tratativas? de erro|nesse mesmo estado|direcionamento [uú]nico|"
    r"veio d[oae]s? estado.*|ouviu .*|ani\s+(sim|n[aã]o)|dtmf.*|fim|n[aã]o h[aá] intera\w+)$",
    re.IGNORECASE,
)
_RX_CHAVE_ESTADO = re.compile(
    r"\bchave\s*:?\s*\[?([A-Za-z][A-Za-z0-9_]{4,})\]?\s*(?:=\s*)?(ativada|desativada|ligada|desligada|habilitada|desabilitada|ativa|inativa|true|false)\b",
    re.IGNORECASE,
)
_RX_CHAVE_NOME = re.compile(r"\(\s*chave:\s*\[?([A-Za-z][A-Za-z0-9_]{4,})\]?\s*\)|\bchave\s+\[?([A-Z][A-Za-z0-9_]{7,})\]?")
_RX_LIGADA = re.compile(r"^(ativada|ligada|habilitada|ativa|true)$", re.IGNORECASE)
_RX_CONECTADO_NEG = re.compile(r"desconect|cancelad|suspens|bloquead|contrato\s+(?:inativo|encerrado)", re.IGNORECASE)
_RX_IDENTIFICOU = re.compile(
    r"id reconhecido|cpf ou cnpj (?:v[aá]lido|retornado)|apenas um cpf|ani reconhecido|cliente identificad|servi[cç]o ok|"
    r"apenas um contrato|desambiguad|identificou|servi[cç]o conectado|possui (?:o )?produto",
    re.IGNORECASE,
)


def _massa_por_ct(steps):
    """Detalha a massa do CT (o que o cliente/API precisam ter para a ligacao seguir ESTE caminho): segmento,
    status do contrato, documento, produto/linha, chaves, dados e retornos de API, base/mailing, recencia, horario.
    Tudo sai das condicoes dos passos; o que a SPEC nao diz fica sem inventar."""
    grupos = {}

    chaves_vistas = {}

    def add(campo, valor):
        valor = re.sub(r"\s+", " ", str(valor or "")).strip(" -:;,.")
        if valor.count("(") != valor.count(")"):
            valor = valor.replace("(", "").replace(")", "").strip()
        if not valor:
            return
        lista = grupos.setdefault(campo, [])
        if valor.lower() not in {x.lower() for x in lista} and len(lista) < 8:
            lista.append(valor[:130])

    identificou = negativo_status = False
    for st in steps or []:
        m = re.search(r"\((.*)\)(?:\s*➜.*)?\s*$", str(st.get("acao") or ""), re.DOTALL)
        if not m:
            continue
        if re.search(r"_cm\b|claro\s*multi", str(st.get("estado") or ""), re.IGNORECASE):
            add("Segmento", "ComboMulti = segmento 10")
        for cond in re.split(r"\s+>\s+", m.group(1)):
            cond = re.sub(r"\(([^()]*)\)", lambda mm: "(" + mm.group(1).replace(",", "/") + ")", cond)
            cond = re.sub(r"entre\s+(\d+h\w*)\s+e\s+(\d+h\w*)", r"entre \1 a \2", cond, flags=re.IGNORECASE)   # faixa de horario
            cond = re.sub(r"\b(MENOR|MAIOR)\s+OU\s+IGUAL", r"\1-OU-IGUAL", cond, flags=re.IGNORECASE)
            for frag in re.split(r"\s+(?:E|OU|e|ou)\s+|\s*[;,]\s*|\n", cond):
                frag = frag.strip()
                if frag.startswith("(") and frag.endswith(")") and frag.count("(") == 1:
                    frag = frag[1:-1].strip()
                if len(re.sub(r"[^A-Za-zÀ-ú]", "", frag)) < 4 or _RX_IGNORAR_FRAG.match(frag) or _RX_SO_TECLA.match(frag):
                    continue
                baixo = frag.lower()
                if _RX_IDENTIFICOU.search(frag):
                    identificou = True
                if _RX_CONECTADO_NEG.search(frag):
                    negativo_status = True
                    add("StatusContrato", f"≠ 1 — contrato NÃO conectado ({frag})")
                    continue
                # segmento
                if re.search(r"combo\s*multi", baixo):
                    if re.search(r"n[aã]o\s+(?:[eé]\s+)?(?:cliente\s+)?combo\s*multi|combo\s*multi\s*=\s*n[aã]o", baixo):
                        add("Segmento", "NÃO é ComboMulti (segmento diferente de 10)")
                    else:
                        add("Segmento", "ComboMulti = segmento 10")
                    continue
                if re.fullmatch(r"demais segmentos?|outros segmentos?", baixo):
                    continue
                if re.search(r"cliente ge|rubi|black|premium|\bouro\b|gaming|piloto|\bvip\b|\bpme\b|empresarial|segmento", baixo):
                    add("Segmento", frag)
                    continue
                # chaves
                mc = _RX_CHAVE_ESTADO.search(frag)
                if mc:
                    if re.search(r"_cm\b", mc.group(1), re.IGNORECASE) and _RX_LIGADA.match(mc.group(2)):
                        add("Segmento", "ComboMulti = segmento 10")
                    if mc.group(1).lower() not in chaves_vistas:   # a mesma chave nao pode estar nos dois estados
                        chaves_vistas[mc.group(1).lower()] = True
                        add("Chaves (parâmetros)", f"{mc.group(1)} = {'ATIVA' if _RX_LIGADA.match(mc.group(2)) else 'DESATIVADA'}")
                    continue
                mn = _RX_CHAVE_NOME.search(frag)
                if mn:
                    add("Chaves (parâmetros)", f"{mn.group(1) or mn.group(2)} — conforme a condição: {frag[:70]}")
                    continue
                # campo = valor (dado do cliente / retorno de API)
                mv = re.search(r"([A-Za-zÀ-ú][A-Za-zÀ-ú0-9_\.\s]{2,45}?)\s*(?:=|==)\s*([^\s].*)$", frag)
                if mv and not re.search(r"chave", mv.group(1), re.IGNORECASE):
                    add("Dado / retorno de API", f"{mv.group(1).strip()} = {mv.group(2).strip()}")
                    continue
                if re.search(r"\bapis?\b|consulta|sucesso|timeout|retorno|servi[cç]o\s+n?ok|erro (?:na|ao|de)", baixo):
                    add("API / serviço", frag)
                elif re.search(r"entre\s+\d+h|hor[aá]rio|segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo|feriado|\bhoje\b|amanh[aã]|manh[aã]|\btarde\b|noite", baixo):
                    add("Horário / data", frag)
                elif re.search(r"\bcpf\b|\bcnpj\b|\bpf\b|\bpj\b", baixo):
                    add("Documento", frag)
                elif re.search(r"mais de (?:um|uma|\d)|apenas (?:um|uma|\d)|[uú]nic[oa]|\d+\s+(?:contratos?|linhas?|chips?)", baixo):
                    add("Quantidade", frag)
                elif re.search(r"rec[eê]ncia|dentro do prazo|\bprazo\b|\d+\s*dias", baixo):
                    add("Recência / prazo", frag)
                elif re.search(r"linha (?:fixa|m[oó]vel|pme)|claro tv|banda larga|internet|controle|(?<![-\w])p[oó]s(?![-\w])|\bpr[eé]\b|chip|portabilidade|telefone|celular|m[oó]vel|\bfixa\b", baixo):
                    add("Produto / linha", frag)
                elif re.search(r"mailing|\bbase\b|cadastrad", baixo):
                    add("Base / mailing", frag)
    if identificou and not negativo_status:
        add("StatusContrato", "1 (conectado) — cliente identificado com contrato ativo")
    itens = []
    for campo in _ORDEM_MASSA:
        if grupos.get(campo):
            itens.append({"rotulo": f"Massa · {campo}", "valor": " ; ".join(grupos[campo])})
    return itens


def _diverge_do_cenario(cenario, cond):
    """O caminho da SPEC contradiz a linha do cenário do EEP (ex.: cenário 'Crédito Reprovado' e o caminho
    passa por 'Crédito APROVADO'): o QA precisa saber antes de montar a massa."""
    if not cenario:
        return False
    def tem(txt, rx):
        return re.search(rx, txt) is not None
    pares = (
        (r"reprovad", r"(?<!re)aprovad"),
        (r"n[aã]o cliente", r"(?<!n[aã]o )\bcliente claro m[oó]vel"),
        (r"(?<!n[aã]o )\bcabead", r"n[aã]o cabead"),
    )
    for a, b in pares:
        if (tem(cenario, a) and tem(cond, b) and not tem(cond, a)) or (tem(cenario, b) and tem(cond, a) and not tem(cond, b)):
            return True
    return False


def _acao_para_step(idx, condicao, perfil):
    if idx == 0:
        return f"Ligar na URA ({'ANI Não' if perfil == 'aninao' else 'ANI Sim'})"
    condicao = (condicao or "Navegar").strip()
    baixo = condicao.lower()
    if any(p in baixo for p in ("dtmf", "digita", "opcao", "opção")):
        return f"Selecionar opção ({condicao})"
    if "nesse mesmo estado" in baixo:
        return f"Permanecer no estado ({condicao})"
    return f"Navegar ({condicao})"


def montar_steps(spec_model, caminho, perfil, transicao_final=None):
    steps = []
    # Saltos escolhidos pelo BFS (o mais facil e compativel com a sessao): maior prefixo do caminho em cache.
    cache = spec_model.get("_hops_cache") or {}
    hops_pref, tam_pref = [], 0
    for k in range(len(caminho), 1, -1):
        achado = cache.get((perfil, tuple(caminho[:k])))
        if achado is not None:
            hops_pref, tam_pref = achado, k
            break
    for j, estado_nome in enumerate(caminho):
        prox_prompt_target = ""
        condicao = ""
        handoff = None
        sp_hop = None
        entradas_hop = []   # ChatBOT: o que o cliente manda/clica para seguir esta transição
        if j == 0:
            condicao = ""
        else:
            anterior = caminho[j - 1]
            transicoes = spec_model["estados"].get(anterior, {}).get("transicoes", [])
            if j < tam_pref and j - 1 < len(hops_pref):
                match_t = hops_pref[j - 1]
            else:
                candidatas = [t for t in transicoes if resolver_destino(spec_model["mapa_rotas"], t["destino"]) == estado_nome]
                match_t = min(candidatas, key=_pontuar_transicao) if candidatas else None
            # O ultimo hop de um CT por transicao deve usar ESSA transicao
            # (nao a primeira que por acaso aponte pro mesmo destino).
            if transicao_final is not None and j == len(caminho) - 1:
                match_t = transicao_final
            if match_t:
                condicao = match_t["condicao"]
                prox_prompt_target = match_t.get("prox_prompt", "")
                sp_hop = match_t.get("sp")
                entradas_hop = list(match_t.get("entradas") or [])
                handoff = match_t.get("handoff")

        state_data = spec_model["estados"].get(estado_nome, {})
        prompt = _match_prompt(state_data, prox_prompt_target)
        prompt_id = prompt["id"] if prompt else "—"
        prompt_texto = (_texto_exibicao_prompt(spec_model, estado_nome, prompt, condicao) or "—") if prompt else "—"

        sp_prompt = _sp_prompt_novo(spec_model, prompt, sp_hop)
        marcas = ", ".join(f"{x[0]}={x[1]}" for x in (sp_hop, sp_prompt) if x)
        if marcas:
            resultado_hop = marcas + (f" — {prompt_texto}" if prompt_texto != "—" else "")
        else:
            resultado_hop = prompt_texto

        acao_passo = _acao_para_step(j, condicao, perfil)
        if j == 0 and estado_nome != _detectar_start_state(spec_model):
            acao_passo = "Entrar no estado (sem caminho a partir do _Start_ na SPEC)"
        elif j > 0 and not condicao:
            acao_passo = "Seguir para o estado (estado anterior declarado na SPEC; sem transição explícita)"
        if handoff:
            acao_passo += " ➜ " + (match_t.get("handoff_txt") or f"MIGRAÇÃO SPEC {handoff}")
        passo = {
            "step_num": j + 1,
            "acao": acao_passo,
            "estado": estado_nome,
            "prompt_id": prompt_id,
            "prompt_texto": prompt_texto,
            "sp": sp_hop,
            "sp_prompt": sp_prompt,
            "resultado": resultado_hop,
            "entradas": entradas_hop,
        }
        if state_data.get("spec") and spec_model.get("_specs"):
            passo["spec"] = state_data["spec"]
        steps.append(passo)
    return steps


def _resultado_final_texto(sp_final, destino_final):
    if sp_final:
        tipo, codigo = sp_final
        return f"{tipo}={codigo}"
    return None


def _formatar_resultado_esperado(steps, sp_final, sp_pendente):
    linhas = ["LOG", "CDR", "ScriptPoint"]
    marcados = []
    for s in steps:
        if s.get("sp"):
            marcados.append(s["sp"])
        if s.get("sp_prompt"):
            marcados.append(s["sp_prompt"])
    if sp_final:
        marcados.append(sp_final)
    vistos = set()
    for tipo, codigo in marcados:
        chave = f"{tipo}={codigo}"
        if chave not in vistos:
            vistos.add(chave)
            linhas.append(chave)
    if sp_pendente:
        linhas.append("⚠️ SP PENDENTE — inserir manualmente após publicação do BI")
    if len(linhas) == 3:
        linhas.append("Sem novo SP registrado (fluxo preservado)")
    return "\n".join(linhas)


class GeradorCT:
    def __init__(self, spec_model, eep_model, tipo_a=True, progress_callback=None, modo_completo=False):
        self.modo_completo = modo_completo
        self._ids_fixos = set()  # CTs que nao se fundem (ex.: um por target de transferencia)
        self._consolidados = 0
        self._notas_caminho = {}
        self._bfs = self._bfs_completo if modo_completo else bfs_caminho_entrada
        self._via_cache = {}
        if spec_model.get("_specs"):
            self._bfs_base = self._bfs
            self._bfs = self._bfs_encadeado
        self.spec_model = spec_model
        self.eep_model = eep_model
        self.tipo_a = tipo_a
        self.casos_teste = []
        self.revisao_necessaria = []
        self._contador = 0
        self._blocos = []  # [{"numero","nome","cor"}]
        self._sp_bi_cobertura = {}  # codigo -> [ct_id,...]
        self._progress_callback = progress_callback
        # Codigos de SP realmente novos desta versao (Versionamento BI). Uma
        # aba de estado traz TODAS as marcacoes de B.I. ja publicadas
        # historicamente, nao so as novas — sem filtrar por isso, cada
        # transicao com SP antigo (de uma versao anterior) vira um CT "novo"
        # por engano. So filtramos quando a VersionamentoBI tem conteudo; se
        # vier vazia (projeto greenfield, sem SP publicado ainda), nao ha
        # nada para comparar e todas as transicoes contam como candidatas.
        self._sps_novos = {sp["codigo"] for sp in spec_model.get("versionamento_bi", []) if sp.get("codigo")}
        if modo_completo:
            self._sps_novos = set()  # SPEC completa: nao ha "SP novo" — tudo entra
        spec_model["_sps_novos"] = self._sps_novos  # montar_steps mostra o SP do PROMPT quando ele e novo
        self._transicoes_ignoradas_sp_antigo = 0
        self._transicoes_ignoradas_sem_sp = 0
        self._transicoes_fora_da_alteracao = 0
        self._sp_regressao = {}
        self._dicas_por_estado = {}

    def _sufixo_spec(self, estado):
        """" (SPEC CRN)" quando a modelagem encadeia varias SPECs; vazio no caso comum."""
        if not self.spec_model.get("_specs"):
            return ""
        spec = (self.spec_model["estados"].get(estado) or {}).get("spec")
        return f" (SPEC {spec})" if spec else ""

    def _progresso(self, pct, etapa):
        if self._progress_callback:
            try:
                self._progress_callback(pct, etapa)
            except Exception:
                pass

    def _novo_id(self, sufixo=""):
        self._contador += 1
        return f"CT-{self._contador:02d}{sufixo}"

    def _cor_bloco(self, bloco_num, regressivo=False):
        if regressivo:
            return REGRESSIVO_COR
        return BLOCO_PALETTE[(bloco_num - 1) % len(BLOCO_PALETTE)]

    def _registrar_sp(self, sp, ct_id):
        if not sp:
            return
        tipo, codigo = sp
        self._sp_bi_cobertura.setdefault(codigo, []).append(ct_id)

    def _add_ct(self, bloco_num, bloco_nome, estado, alteracao, perfil, caminho, sp_final=None, regressivo=False, sp_pendente=False, gherkin_override=None, restricoes=None, sps_todos=None, steps_extra=None, transicao_final=None, sp_legado=False, acao_final=None, resultado_inicial=None, condicoes_massa=None):
        if not caminho:
            self.revisao_necessaria.append(
                {
                    "tipo": "sem_caminho",
                    "estado": estado,
                    "detalhe": f"Não foi possível calcular um caminho de entrada ate o estado '{estado}' a partir do início do fluxo.",
                }
            )
            return None

        if self.modo_completo and self._notas_caminho.get(estado) and not str(alteracao or "").startswith("["):
            alteracao = f"[{self._notas_caminho[estado]}] {alteracao or ''}".strip()
        steps = montar_steps(self.spec_model, caminho, perfil, transicao_final=transicao_final)
        n_montados = len(steps)
        # Steps adicionais (ex.: tentativas REJ1/REJ2/... ou SIL1/SIL2/... da
        # mesma escada, num unico CT) entram depois do caminho ate o estado.
        for extra in steps_extra or []:
            novo = dict(extra)
            novo["step_num"] = len(steps) + 1
            steps.append(novo)
        n_validacao = len(steps)
        # TODO CT vai de PONTA A PONTA: depois do ponto de validacao a jornada segue ate a transferencia/fim.
        if not str(alteracao or "").startswith("Cenário") and steps:
            ultimo_estado = steps[-1].get("estado")
            if ultimo_estado and ultimo_estado not in ("-", "—"):
                visitados_ct = {st.get("estado") for st in steps}
                for passo_jornada in _steps_jornada(self.spec_model, ultimo_estado, visitados_ct):
                    passo_jornada["step_num"] = len(steps) + 1
                    steps.append(passo_jornada)
        sps_todos = [sp for sp in (sps_todos or []) if sp]
        if sps_todos and not sp_final:
            sp_final = sps_todos[0]
        sp_pendente = sp_pendente or (sp_final is None and self.tipo_a and not (regressivo or sp_legado))

        resultado_txt = _formatar_resultado_esperado(steps, sp_final, sp_pendente)
        if resultado_inicial:
            resultado_txt = f"{resultado_inicial}\n{resultado_txt}"
        steps.append(
            {
                "step_num": len(steps) + 1,
                "acao": acao_final or "Encerrar a chamada",
                "estado": "-",
                "prompt_id": "—",
                "prompt_texto": "—",
                "sp": None,
                "resultado": resultado_txt,
            }
        )

        perfil_txt = "ANINÃO" if perfil == "aninao" else "ANISIM"
        if len(sps_todos) > 1:
            resultado_gherkin = "marcar os ScriptPoints " + ", ".join(sp[1] for sp in sps_todos)
        else:
            resultado_gherkin = (
                f"marcar o ScriptPoint {sp_final[1]}" if sp_final else "preservar o fluxo vigente sem novo SP (SP PENDENTE)"
            )
        if gherkin_override:
            gherkin = abreviar_gherkin(gherkin_override)
        else:
            cond_ct, contexto_ct = _condicao_do_ct(alteracao, transicao_final)
            passo_val = steps[n_montados - 1] if 0 < n_montados <= len(steps) else {}
            if cond_ct and len(steps) >= 2 and n_montados >= 2:
                destino_txt = passo_val.get("estado")
                prompt_id = passo_val.get("prompt_id")
                alvo_txt = f"ir para o estado {destino_txt}" if destino_txt and destino_txt not in ("-", "—") else "seguir o fluxo"
                if prompt_id and prompt_id not in ("-", "—"):
                    alvo_txt += f" (prompt {prompt_id})"
                prefixo = f"Dado cliente {perfil_txt} na jornada de homologação, Quando "
                sufixo = f", Então URA deve {alvo_txt} e {resultado_gherkin}."
                gherkin = montar_gherkin(prefixo, cond_ct, sufixo)
            else:
                prefixo = f"Dado cliente {perfil_txt} na jornada de homologação, Quando percorrer o caminho de entrada até o estado {estado} ("
                sufixo = f"), Então URA deve {resultado_gherkin}."
                gherkin = montar_gherkin(prefixo, alteracao or "garantia de fluxo", sufixo)

        sufixo = "b" if sp_pendente and self.tipo_a else ""
        ct_id = self._novo_id(sufixo)
        # CT regressivo confere SP LEGADO (ja em producao): fica numa lista PROPRIA, separada das
        # marcacoes novas do projeto (senao SPs antigos apareceriam como marcacao do projeto).
        if regressivo or sp_legado:
            for sp_reg in ([sp_final] if sp_final else []) + [sp for sp in sps_todos if sp != sp_final]:
                reg = self._sp_regressao.setdefault(sp_reg[1], {"codigo": sp_reg[1], "tipo": sp_reg[0], "cts": [], "estados": []})
                if ct_id not in reg["cts"]:
                    reg["cts"].append(ct_id)
                if estado not in reg["estados"]:
                    reg["estados"].append(estado)
        if not (regressivo or sp_legado):
            self._registrar_sp(sp_final, ct_id)
            for sp_extra in sps_todos:
                if sp_extra != sp_final:
                    self._registrar_sp(sp_extra, ct_id)
            # SP NOVO que o CT toca pelo caminho/jornada tambem e conferido por ele (ex.: spp do prompt INI_MP)
            for passo in steps:
                for chave_sp in ("sp", "sp_prompt"):
                    sp_passo = passo.get(chave_sp)
                    if sp_passo and sp_passo[1] in self._sps_novos and sp_passo[1] not in self._sp_bi_cobertura:
                        self._registrar_sp(sp_passo, ct_id)

        tags ={"linha": "Celular/Fixo", "afterhours": "AfterHours", "mpl": "MPL", "protocolo": "Protocolo", "adimplencia": "Adimplência"}
        pre_req_partes = [f"ANI {'Não' if perfil == 'aninao' else 'Sim'}"]
        for chave, rotulo in tags.items():
            if restricoes and chave in restricoes:
                pre_req_partes.append(f"{rotulo}: {restricoes[chave]}")
        # Mesmas tags acima, SEM a "Alteração"/"Garantia de fluxo" — essa
        # parte conta a HISTORIA do CT (o que mudou), nao a massa/requisito
        # de dado necessario pra executa-lo. Usado na aba Massa_Testes, que
        # antes so apontava "veja o Pré-Requisito" em vez de mostrar os
        # requisitos de verdade.
        requisitos_massa = " | ".join(pre_req_partes)
        condicoes = _condicoes_da_massa(perfil, restricoes, tags, condicoes_massa, steps) + _massa_por_ct(steps)
        cond_pre, contexto_pre = _condicao_do_ct(alteracao, transicao_final)
        if cond_pre and not gherkin_override:
            pre_req_partes.append(f"Estado: {estado}")
            if contexto_pre:
                pre_req_partes.append("Caminho de condições: " + " → ".join(contexto_pre))
            pre_req_partes.append(f"Condição a validar: {cond_pre}")
            alt_txt = re.sub(r"\s*[—-]\s*condi[cç][aã]o:.*$", "", str(alteracao or ""), flags=re.IGNORECASE | re.DOTALL).strip()
            if alt_txt and alt_txt != "Cobertura completa da SPEC":
                pre_req_partes.append(f"Alteração: {alt_txt}")
        else:
            pre_req_partes.append(f"Alteração: {alteracao}" if alteracao else "Garantia de fluxo principal")
        pre_requisito = " | ".join(pre_req_partes)

        caso = {
            "id": ct_id.replace("CT-", ""),
            "ct_id": ct_id,
            "bloco": bloco_num,
            "bloco_nome": bloco_nome,
            "regressivo": regressivo,
            "estado": estado,
            "spec": (self.spec_model["estados"].get(estado) or {}).get("spec") if self.spec_model.get("_specs") else None,
            "alteracao_relatada": alteracao,
            "perfil": perfil_txt,
            "caminho_qa": caminho,
            "gherkin": gherkin,
            "steps": steps,
            "sp_pendente": sp_pendente,
            "sp_final": (
                ", ".join(f"{tipo}={cod}" for tipo, cod in sps_todos)
                if len(sps_todos) > 1
                else (f"{sp_final[0]}={sp_final[1]}" if sp_final else None)
            ),
            "pre_requisito": pre_requisito,
            "requisitos_massa": requisitos_massa,
            "condicoes_massa": condicoes,
        }
        self.casos_teste.append(caso)
        if str(alteracao or "").startswith("Cenário"):
            self._ids_fixos.add(ct_id)
        return caso

    # ---------- L1-L4, L6-L8: CTs principais por estado alterado ----------

    def gerar_cts_tipo_a(self):
        estados_alterados = list(self.spec_model["versionamento"]["estados_alterados"])
        if self.modo_completo:
            estados_alterados = [
                {"nome": n, "alteracao": "Cobertura completa da SPEC"} for n in self._estados_em_ordem_de_fluxo()
            ]

        # A VersionamentoBI e a fonte de verdade de quais SPs sao realmente
        # novos desta versao. Se ela cita um estado que o changelog da
        # _Versionamento_ nao mencionou explicitamente (lacuna comum quando o
        # changelog e preenchido a mao), ainda assim precisamos gerar CT pra
        # esse estado — senao SPs legitimamente novos ficam de fora so por
        # causa de uma lacuna no texto do changelog.
        nomes_ja_cobertos = {normalizar_chave(e["nome"]) for e in estados_alterados}
        estados_so_no_bi = {}
        for sp in self.spec_model.get("versionamento_bi", []):
            estado_bi = sp.get("estado")
            if not estado_bi:
                continue
            chave = normalizar_chave(estado_bi)
            if chave in nomes_ja_cobertos or chave in estados_so_no_bi:
                continue
            estados_so_no_bi[chave] = estado_bi
        for chave, nome_estado in estados_so_no_bi.items():
            estados_alterados.append(
                {
                    "nome": nome_estado,
                    "alteracao": "Novo(s) ScriptPoint(s) publicado(s) na Versionamento BI desta versão "
                    "(estado não citado no changelog da Versionamento).",
                }
            )

        # O changelog da _Versionamento_ costuma ter UMA LINHA POR ALTERAÇÃO
        # descrita, e o MESMO estado pode aparecer em varias linhas (uma
        # descrevendo cada mudança). Sem isso, cada linha repetida reprocessa
        # TODAS as transicoes do estado de novo, multiplicando os CTs por
        # engano (ex.: 1 estado citado 4x vira 4x os CTs dele). L4 e "1 CT
        # por SP novo", nao "1 CT por SP novo por linha de changelog".
        agrupados = {}
        ordem = []
        for est in estados_alterados:
            chave = normalizar_chave(est["nome"])
            if chave not in agrupados:
                agrupados[chave] = {"nome": est["nome"], "alteracoes": []}
                ordem.append(chave)
            desc = (est.get("alteracao") or "").strip()
            if desc and desc not in agrupados[chave]["alteracoes"]:
                agrupados[chave]["alteracoes"].append(desc)
        estados_alterados = [
            {"nome": agrupados[c]["nome"], "alteracao": " | ".join(agrupados[c]["alteracoes"])} for c in ordem
        ]

        self._estados_alterados_ref = list(estados_alterados)

        if not estados_alterados:
            ivr_usado = self.spec_model.get("ivr_resolvido")
            if ivr_usado:
                # Com o IVR definido (informado ou descoberto), "nada
                # encontrado" quer dizer que o bloco dele nao foi lido —
                # nunca cair no plano B de testar a primeira aba da SPEC, que
                # modelaria um estado que nao pertence ao projeto.
                self.revisao_necessaria.append(
                    {
                        "tipo": "versionamento_vazio",
                        "detalhe": f"Não encontrei estados alterados nem ScriptPoints do {ivr_usado} nas abas de "
                        "Versionamento e Versionamento BI (conferi variações como 'IVR-N' e 'IVR- N'). Nenhum CT "
                        "foi gerado para não modelar um estado que não é do projeto. Confira o código IVR, o nome "
                        "das abas de versionamento e se o bloco do projeto está preenchido. "
                        + self._resumo_diag_versionamento(),
                    }
                )
                estados_alterados = []
            else:
                self.revisao_necessaria.append(
                    {
                        "tipo": "versionamento_vazio",
                        "detalhe": "Nenhum estado alterado encontrado na aba de Versionamento — "
                        "confira se o código IVR informado bate com o bloco marcado na SPEC.",
                    }
                )
                estados_alterados = [
                    {"nome": self.spec_model["lista_abas"][0], "alteracao": "Garantia de teste do fluxo principal"}
                ] if self.spec_model["lista_abas"] else []

        total_estados = len(estados_alterados)
        for bloco_idx, est in enumerate(estados_alterados, start=1):
            nome_real = resolver_destino(self.spec_model["mapa_rotas"], est["nome"]) or est["nome"]
            self._progresso(
                int(5 + 75 * (bloco_idx - 1) / max(total_estados, 1)),
                f"Gerando cenários para o estado {bloco_idx} de {total_estados} ({nome_real})...",
            )
            cor = self._cor_bloco(bloco_idx)
            bloco_nome = f"Bloco {bloco_idx}"
            if nome_real not in self.spec_model["estados"]:
                corrigido = _resolver_estado_aproximado(nome_real, self.spec_model["estados"].keys())
                if corrigido:
                    self.revisao_necessaria.append(
                        {
                            "tipo": "estado_corrigido_automaticamente",
                            "estado": est["nome"],
                            "detalhe": f"Estado '{est['nome']}' citado no Versionamento não bate exatamente com "
                            f"nenhuma aba da SPEC, mas '{corrigido}' é uma correspondência muito próxima "
                            "(provável erro de digitação) e foi usada no lugar. Confira se está correto.",
                        }
                    )
                    nome_real = corrigido
                else:
                    self._blocos.append(
                        {"numero": bloco_idx, "nome": bloco_nome, "cor": cor, "titulo": f"{bloco_nome} — {nome_real}{self._sufixo_spec(nome_real)}"}
                    )
                    self.revisao_necessaria.append(
                        {
                            "tipo": "estado_nao_encontrado",
                            "estado": est["nome"],
                            "detalhe": f"Estado '{est['nome']}' citado no Versionamento não foi encontrado como aba na SPEC.",
                        }
                    )
                    continue

            self._blocos.append({"numero": bloco_idx, "nome": bloco_nome, "cor": cor, "titulo": f"{bloco_nome} — {nome_real}{self._sufixo_spec(nome_real)}"})

            transicoes = self.spec_model["estados"][nome_real].get("transicoes", [])
            alt_lower = (est.get("alteracao") or "").lower()
            perfil_base = "anisim" if ("anisim" in alt_lower and "aninao" not in alt_lower and "ani nao" not in alt_lower) else "aninao"
            estado_novo = bool(_ESTADO_NOVO_RE.search(est.get("alteracao") or ""))

            # Sem NENHUM SP publicado na VersionamentoBI pra esta versão
            # (self._sps_novos vazio), nao ha como saber qual das transicoes
            # do estado e a que de fato mudou. Pra um projeto pequeno/
            # genuinamente greenfield (poucas transicoes por estado — o
            # arquivo de referencia testado tem no maximo 36), testar todas
            # ainda e razoavel. Mas pra um estado GRANDE e ja existente (ex.:
            # 93 ramos legados, so 1 chave nova incluida), testar tudo e
            # especulativo demais (L3/L4) — 1 CT de garantia de fluxo ja
            # cobre a garantia de que o estado e alcancavel e testavel. O
            # limite abaixo fica acima do maior estado do projeto de
            # referencia validado, pra nao regredir esse caso legitimo.
            LIMITE_TRANSICOES_SEM_SP = 50
            # Sem SP novo: se o changelog cita prompts/chaves e alguma transicao do estado os usa,
            # testa so essas (o que de fato mudou) em vez de todas as ramificacoes do estado.
            dicas_estado = _dicas_alteracao(est.get("alteracao"))
            self._dicas_por_estado[nome_real] = dicas_estado
            prompts_novos_estado = [
                p for p in self.spec_model["estados"][nome_real].get("prompts", [])
                if any(tok in normalizar_chave(p["id"]) for tok in dicas_estado[0])
            ]
            usar_dicas = (
                not self._sps_novos
                and any(dicas_estado)
                and (bool(prompts_novos_estado) or any(_transicao_casa_dicas(t, dicas_estado) for t in transicoes))
            )
            # Alteracao de montagem/tempo de concat: o que mudou sao as VARIACOES do concat (CTs
            # proprios mais adiante), nao as ramificacoes do menu.
            concat_alterado = (
                not self._sps_novos
                and bool(_ALT_CONCAT_RE.search(est.get("alteracao") or ""))
                and bool(self.spec_model["estados"][nome_real].get("concat_exemplos"))
            )
            usar_dicas = usar_dicas or concat_alterado
            if not transicoes or (
                not self._sps_novos and not usar_dicas and not self.modo_completo and len(transicoes) > LIMITE_TRANSICOES_SEM_SP
            ):
                caminho, perfil_efetivo = self._bfs(self.spec_model, nome_real, perfil_entrada=perfil_base)
                self._add_ct(bloco_idx, bloco_nome, nome_real, est["alteracao"], perfil_efetivo, caminho)
                continue

            # L4: 1 CT por transicao/SP novo do estado alterado (salvo condicionais identicas)
            # L2: ANINAO antes de ANISIM
            def _chave_ordenacao(t):
                restr = extrair_restricoes_sessao(t["condicao"])
                return (0 if restr.get("ani") != "anisim" else 1, t["condicao"])

            vistos_condicao = set()
            cts_antes = len(self.casos_teste)
            sp_antigo_local = 0
            sem_sp_local = 0
            sem_caminho_local = 0
            fora_alt_local = 0
            # Condicionais NOVAS: o ramo OPOSTO (irmao no mesmo grupo — ex.: "chave ATIVADA E nao tem
            # visita" x "chave DESATIVADA OU ja tem visita") precisa ser validado junto, com o SP legado.
            filhos_por_pai = {}
            for t_cont in transicoes:
                c_path = t_cont.get("path") or []
                if len(c_path) > 1:
                    filhos_por_pai.setdefault(tuple(c_path[:-1]), set()).add(c_path[-1])
            pais_novos = set()
            for t_pai in transicoes:
                sp_pai = _sp_efetivo_transicao(self.spec_model, nome_real, t_pai)
                caminho_pai = t_pai.get("path") or []
                # so decisoes de poucos ramos (condicional verdadeiro/falso), nao menus com muitas opcoes
                if (self._sps_novos and sp_pai and sp_pai[1] in self._sps_novos and len(caminho_pai) > 1
                        and len(filhos_por_pai.get(tuple(caminho_pai[:-1]), ())) <= 3):
                    pais_novos.add(tuple(caminho_pai[:-1]))
            irmaos_por_pai = {}

            def _avaliar(t):
                """(sp_efetivo, status) — status: 'ok' | 'irmao' | 'antigo' | 'sem_sp'."""
                sp_t = _sp_efetivo_transicao(self.spec_model, nome_real, t)
                # Num estado NOVO, os ramos de REJ/SIL (usuario digitou algo
                # diferente / ficou em silencio) devem ser 100% mapeados,
                # mesmo quando a tentativa final (normalmente a 3ª) sai pra
                # OUTRO estado (ex.: Transfer) tocando um prompt que nao
                # carrega SP nenhum (nem novo, nem antigo — e so um prompt
                # de saida compartilhado).
                if estado_novo and _eh_transicao_rej_sil(t["condicao"]):
                    return sp_t, "ok"
                if not self._sps_novos:
                    if usar_dicas and not _transicao_casa_dicas(t, dicas_estado):
                        return sp_t, "fora_alteracao"
                    return sp_t, "ok"
                caminho_t = tuple(t.get("path") or [])
                eh_irmao = len(caminho_t) > 1 and caminho_t[:-1] in pais_novos and not _eh_transicao_rej_sil(t["condicao"])
                if eh_irmao and irmaos_por_pai.get(caminho_t[:-1], 0) >= 2:
                    eh_irmao = False
                if sp_t and sp_t[1] not in self._sps_novos:
                    # SP ja existia antes desta versao (nao esta na lista de novos da VersionamentoBI):
                    # fora do escopo — salvo se e o ramo oposto de uma condicional nova.
                    if eh_irmao:
                        irmaos_por_pai[caminho_t[:-1]] = irmaos_por_pai.get(caminho_t[:-1], 0) + 1
                        return sp_t, "irmao"
                    return sp_t, "antigo"
                if not sp_t:
                    # Sem NENHUMA marcacao de SP, com a BI ja preenchida:
                    # nenhum sinal de que faz parte desta versao — pode ser
                    # so um ramo antigo do menu. Sem esse filtro, um estado
                    # grande com dezenas de ramos legados gera uma "SP
                    # PENDENTE" pra CADA UM (violando L3/L4).
                    if eh_irmao:
                        irmaos_por_pai[caminho_t[:-1]] = irmaos_por_pai.get(caminho_t[:-1], 0) + 1
                        return sp_t, "irmao"
                    return sp_t, "sem_sp"
                return sp_t, "ok"

            def _contar_ignorada(status):
                nonlocal sp_antigo_local, sem_sp_local, fora_alt_local
                if status == "fora_alteracao":
                    self._transicoes_fora_da_alteracao += 1
                    fora_alt_local += 1
                elif status == "antigo":
                    self._transicoes_ignoradas_sp_antigo += 1
                    sp_antigo_local += 1
                elif status == "sem_sp":
                    self._transicoes_ignoradas_sem_sp += 1
                    sem_sp_local += 1

            # As tentativas de uma mesma escada de REJ (ou de SIL) — 1ª vez,
            # 2ª vez, 3ª vez... — sao uma sequencia unica de uma so chamada
            # (volta pro mesmo estado ate esgotar e sair): viram UM CT com um
            # step por tentativa (mostrando o prompt REJ1/REJ2/... de cada
            # uma), em vez de um CT por tentativa.
            unidades = []
            grupos = {}
            for t in sorted(transicoes, key=_chave_ordenacao):
                chave = _chave_grupo_retentativa(t)
                if chave is None:
                    unidades.append([t])
                    continue
                if chave[0] not in grupos:
                    grupos[chave[0]] = []
                    unidades.append(grupos[chave[0]])
                grupos[chave[0]].append((chave[1], t))

            for unidade in unidades:
                eh_escada = bool(unidade) and isinstance(unidade[0], tuple)

                if not eh_escada:
                    t = unidade[0]
                    sp_t, status = _avaliar(t)
                    if status not in ("ok", "irmao"):
                        _contar_ignorada(status)
                        continue
                    eh_irmao = status == "irmao"

                    assinatura = normalizar_chave(t["condicao"])
                    if assinatura in vistos_condicao:
                        continue
                    vistos_condicao.add(assinatura)

                    restr = extrair_restricoes_sessao(t["condicao"])
                    perfil = restr.get("ani", perfil_base)
                    caminho, perfil_efetivo = self._bfs(self.spec_model, nome_real, perfil_entrada=perfil, restricoes_extra=restr
                    )
                    if not caminho:
                        sem_caminho_local += 1
                        continue
                    if perfil_efetivo != perfil:
                        perfil = perfil_efetivo
                        restr = dict(restr)
                        restr["ani"] = perfil_efetivo
                    destino_hop = resolver_destino(self.spec_model["mapa_rotas"], t["destino"])
                    caminho_completo = caminho + ([destino_hop] if destino_hop and destino_hop != caminho[-1] else [])
                    alteracao_txt = f"{est['alteracao']} — condição: {t['condicao']}" if est.get("alteracao") else t["condicao"]
                    if eh_irmao:
                        alteracao_txt = f"Ramo oposto da condicional nova — condição: {t['condicao']}"
                    steps_jornada = []
                    if destino_hop and destino_hop != nome_real:
                        # a jornada segue conforme a SPEC ate a transferencia/fim (nao para no SP de passagem)
                        steps_jornada = _steps_jornada(self.spec_model, destino_hop, set(caminho_completo))
                    if len(caminho_completo) == len(caminho):
                        # Sem troca de estado: o CT precisa mostrar a ACAO que gera o SP.
                        if _eh_transicao_rej_sil(t["condicao"]):
                            passo_acao = _step_retentativa(self.spec_model, nome_real, t, sp_t)
                        else:
                            passo_acao = _step_transicao(self.spec_model, nome_real, t, sp_t, perfil)
                        steps_jornada = [passo_acao] + steps_jornada
                    self._add_ct(
                        bloco_idx, bloco_nome, nome_real, alteracao_txt, perfil, caminho_completo,
                        sp_final=sp_t, restricoes=restr, steps_extra=steps_jornada,
                        transicao_final=t if len(caminho_completo) > len(caminho) else None,
                        sp_legado=eh_irmao,
                    )
                    continue

                tentativas = [t for _n, t in sorted(unidade, key=lambda x: x[0])]
                avaliacoes = [_avaliar(t) for t in tentativas]
                if not any(status == "ok" for _sp, status in avaliacoes):
                    for _sp, status in avaliacoes:
                        _contar_ignorada(status)
                    continue

                restr = extrair_restricoes_sessao(tentativas[0]["condicao"])
                perfil = restr.get("ani", perfil_base)
                caminho, perfil_efetivo = self._bfs(self.spec_model, nome_real, perfil_entrada=perfil, restricoes_extra=restr
                )
                if not caminho:
                    sem_caminho_local += len(tentativas)
                    continue
                if perfil_efetivo != perfil:
                    perfil = perfil_efetivo
                    restr = dict(restr)
                    restr["ani"] = perfil_efetivo

                steps_extra = [
                    _step_retentativa(self.spec_model, nome_real, t, sp_t)
                    for t, (sp_t, _status) in zip(tentativas, avaliacoes)
                ]
                # Se a ultima tentativa sai pra outro estado (Transfer, menu,
                # _End_...), a jornada segue conforme a SPEC ate o fim.
                destino_saida = resolver_destino(self.spec_model["mapa_rotas"], tentativas[-1].get("destino"))
                if destino_saida and destino_saida != nome_real:
                    steps_extra += _steps_jornada(
                        self.spec_model, destino_saida, set(caminho) | {nome_real, destino_saida}
                    )
                sps_escada = []
                for sp_t, _status in avaliacoes:
                    if sp_t and sp_t not in sps_escada:
                        sps_escada.append(sp_t)

                pai = " > ".join((tentativas[0].get("path") or [tentativas[0]["condicao"]])[:-1])
                folhas = " → ".join((t.get("path") or [t["condicao"]])[-1] for t in tentativas)
                rotulo = f"{pai} > {folhas}"
                alteracao_txt = f"{est['alteracao']} — condição: {rotulo}" if est.get("alteracao") else rotulo
                self._add_ct(
                    bloco_idx, bloco_nome, nome_real, alteracao_txt, perfil, caminho,
                    sp_final=sps_escada[0] if sps_escada else None, sps_todos=sps_escada,
                    steps_extra=steps_extra, restricoes=restr,
                )

            if self._sps_novos and len(self.casos_teste) > cts_antes:
                # O prompt de ENTRADA do estado (o primeiro da lista, tipo
                # "INI") toca sempre que qualquer CT alcanca este estado —
                # mas raramente tem uma transicao propria dedicada a ele (a
                # unica transicao que aponta pra ele via "Proximo Prompt"
                # costuma ja ter seu proprio SP de destino, que tem
                # prioridade em _sp_efetivo_transicao). Sem isso, o SP do
                # prompt de entrada nunca e creditado a nenhum CT, mesmo
                # sendo tocado em TODOS eles — credita ao primeiro CT deste
                # estado.
                prompts_estado = self.spec_model["estados"].get(nome_real, {}).get("prompts", [])
                if prompts_estado:
                    sp_entrada = prompts_estado[0].get("sp")
                    if sp_entrada and sp_entrada[1] in self._sps_novos and sp_entrada[1] not in self._sp_bi_cobertura:
                        self._registrar_sp(sp_entrada, self.casos_teste[cts_antes]["ct_id"])

            if len(self.casos_teste) == cts_antes and transicoes and not concat_alterado:
                partes = []
                if sp_antigo_local:
                    partes.append(f"{sp_antigo_local} transição(ões) com SP antigo (fora da VersionamentoBI)")
                if sem_sp_local:
                    partes.append(f"{sem_sp_local} transição(ões) sem nenhuma marcação de SP")
                if fora_alt_local:
                    partes.append(
                        f"{fora_alt_local} transição(ões) não citadas pelo versionamento (a alteração é de prompts/chaves: "
                        "os prompts novos são validados nos CTs de fraseologia)"
                    )
                if sem_caminho_local:
                    partes.append(f"{sem_caminho_local} transição(ões) sem caminho de entrada encontrado (BFS)")
                motivo = (
                    ", ".join(partes) + "."
                    if partes
                    else "nenhuma transição gerou um CT válido (verifique a estrutura da aba manualmente)."
                )
                self.revisao_necessaria.append(
                    {
                        "tipo": "estado_sem_ct_completo" if self.modo_completo else "estado_sem_sp_novo",
                        "estado": nome_real,
                        "detalhe": f"Estado '{nome_real}' está no Versionamento, mas não gerou nenhum CT: {motivo} "
                        "Confira manualmente se o código IVR/cor detectados "
                        "estão corretos.",
                    }
                )

    # ---------- L12/L13: cobertura por produto (Tipo B, regra de transferencia pura) ----------

    def gerar_cts_transferencia(self):
        """
        Projeto SO de transferencia (sem alteracao de navegacao): a SPEC e a BASE do caminho e o EEP traz a tabela de
        cenarios com o TARGET/ID de transferencia ATH. Um CT por cenario: percorre a SPEC pelo caminho mais facil
        ate a transferencia ATH (preferindo a transicao cuja condicao combina com o cenario: credito, cliente movel,
        cabeamento...) e valida o ID de transferencia esperado.
        """
        cenarios = self.eep_model.get("cenarios_transferencia") or []
        estados = self.spec_model["estados"]
        mapa = self.spec_model["mapa_rotas"]

        # todas as transicoes que levam a um estado de transferencia
        entradas_transfer = []
        for origem, dados_origem in estados.items():
            for t in dados_origem.get("transicoes", []):
                destino = resolver_destino(mapa, t.get("destino"))
                if destino and _TERMINAL_RE.match(destino) and not destino.lower().startswith("_end_"):
                    entradas_transfer.append((origem, t, destino))
        if not entradas_transfer:
            self.revisao_necessaria.append(
                {
                    "tipo": "sem_estado_transferencia",
                    "detalhe": "A SPEC não tem transições para estados de transferência (Transfer*): não há onde validar o ID de "
                    "transferência ATH. Confira se a SPEC enviada é a do fluxo que transfere.",
                }
            )
            return
        if not cenarios:
            self.revisao_necessaria.append(
                {
                    "tipo": "sem_tabela_cenarios_transferencia",
                    "detalhe": "Não encontrei no EEP uma tabela de cenários com o TARGET/VDN/ID de transferência. Gerei 1 CT por "
                    "caminho distinto até a transferência; informe os IDs manualmente.",
                }
            )
            cenarios = [
                {"cenario": str(i + 1), "alvo": "", "rotulo_alvo": "ID de transferência", "campos": [("Origem", f"{o} → {d}")]}
                for i, (o, _t, d) in enumerate(entradas_transfer[:30])
            ]

        def _caminho_ate(origem, t, f_cen):
            restr = extrair_restricoes_sessao(t["condicao"])
            caminho, perfil_ef = self._bfs(self.spec_model, origem, perfil_entrada=restr.get("ani", "aninao"), restricoes_extra=restr, cenario=f_cen)
            if not caminho:
                caminho, perfil_ef = self._bfs(self.spec_model, origem, perfil_entrada="aninao", cenario=f_cen)
            return restr, caminho, perfil_ef

        def _pontos(f_cen, t, caminho, perfil_ef):
            """O caminho INTEIRO (saltos do BFS + transicao final) contra o cenario: ganha pelos tracos do cenario
            citados, perde por cada condicao que o contradiz e por condicoes que se contradizem entre si. Transferir
            por erro (max erro/silencio/rejeicao) so vale se nao houver outro jeito — salvo no cenario de timeout."""
            hops = (self.spec_model.get("_hops_cache") or {}).get((perfil_ef, tuple(caminho))) or []
            textos = [_texto_transicao(h) for h in hops] + [_texto_transicao(t)]
            feats = [_feat_cenario(x) for x in textos]
            uniao = set().union(*feats)
            perda = sum(_conflitos_cenario(f_cen, f) for f in feats) + _conflitos_cenario(uniao, uniao)
            erros = 0 if "timeout" in f_cen else sum(1 for x in textos if _RX_TRANSICAO_ERRO.search(x))
            return len(f_cen & uniao) - 2 * perda - erros, perda, erros

        feats_spec = frozenset().union(*(_feat_cenario(_texto_transicao(t)) for dados in estados.values() for t in dados.get("transicoes", [])))
        rotulo_alvo = (cenarios[0].get("rotulo_alvo") or "Target").strip(": ") or "Target"
        ultimo_grupo, bloco_idx, bloco_nome = None, len(self._blocos), ""
        primeiro_bloco = True
        for i, cen in enumerate(cenarios):
            self._progresso(int(5 + 80 * i / max(len(cenarios), 1)), f"Gerando cenário de transferência {i + 1} de {len(cenarios)}...")
            campos = cen.get("campos") or []
            grupo = next((v for k, v in campos if re.search(r"grupo", k, re.IGNORECASE) and not re.search(r"crit", k, re.IGNORECASE)), "")
            if grupo != ultimo_grupo or primeiro_bloco:
                primeiro_bloco = False
                bloco_idx += 1
                bloco_nome = f"Bloco {bloco_idx}"
                self._blocos.append(
                    {"numero": bloco_idx, "nome": bloco_nome, "cor": self._cor_bloco(bloco_idx), "titulo": f"{bloco_nome} — {grupo or 'Transferência ATH'}"}
                )
                ultimo_grupo = grupo

            texto_cen = " ".join(v for k, v in campos if not re.fullmatch(r"cen[aá]rio", k.strip(), re.IGNORECASE))
            f_cen = frozenset(_feat_cenario(texto_cen))
            # na ordem do melhor caso (todos os tracos do cenario que a SPEC cita, so os conflitos da transicao final):
            # para assim que nenhuma das restantes consegue passar a melhor ja achada
            teto = len(f_cen & feats_spec)
            otimistas = sorted(
                ((-(teto - 2 * _conflitos_cenario(f_cen, _feat_cenario(_texto_transicao(t)))), _pontuar_transicao(t),
                  len(t.get("path") or []), k), origem, t, destino)
                for k, (origem, t, destino) in enumerate(entradas_transfer)
            )
            melhor = None
            for otimista, origem, t, destino in otimistas:
                if melhor is not None and (otimista[0], 0, otimista[1], otimista[2]) > melhor[0][:4]:
                    break
                _restr, caminho, perfil_ef = _caminho_ate(origem, t, f_cen)
                if not caminho:
                    continue
                pontos, perda, erros = _pontos(f_cen, t, caminho, perfil_ef)
                chave = (-pontos, erros, otimista[1], otimista[2], len(caminho), otimista[3])
                if melhor is None or chave < melhor[0]:
                    melhor = (chave, origem, t, destino, pontos + erros, perda)
            if melhor is None:
                continue
            _chave, origem, t, destino, pontos, perda = melhor
            # de novo a busca escolhida (vem do cache): os steps usam os saltos DESTE caminho
            restr, caminho, perfil_ef = _caminho_ate(origem, t, f_cen)
            completo = caminho + ([destino] if destino != caminho[-1] else [])
            alvo = cen.get("alvo") or "—"
            numero = cen.get("cenario") or str(i + 1)
            descr_cond = "; ".join(f"{k}: {v}" for k, v in campos if not re.fullmatch(r"cen[aá]rio", k.strip(), re.IGNORECASE))

            def _titulo(txt):
                return re.sub(r"\s+", " ", str(txt).replace("–", " ").replace("-", " ")).strip().title()

            grupo_txt = _titulo(grupo) if grupo else ""
            valores = [v for k, v in campos if not re.search(r"cen[aá]rio|grupo|crit[eé]rio", k, re.IGNORECASE)]
            movel = next((v for v in valores if re.search(r"m[oó]vel|celular", v, re.IGNORECASE)), "")
            credito = next((v for v in valores if re.search(r"cr[eé]dito", v, re.IGNORECASE) and not re.search(r"n[aã]o se aplica", v, re.IGNORECASE)), "")
            criterio = next((v for k, v in campos if re.search(r"crit[eé]rio", k, re.IGNORECASE)), "")
            quando_partes = [movel, credito] if credito else [movel, (criterio[:60] if criterio else "")]
            quando_txt = " ".join(p for p in quando_partes if p).strip() or descr_cond[:80]
            inds = self.eep_model.get("indicadores") or []
            ind = "101" if "101" in inds else (inds[0] if inds else "")
            dado_txt = (f"Ind.Atend.{ind} " if ind else "") + (f"do {grupo_txt}" if grupo_txt else f"no cenário {numero}")
            gherkin = (
                f"Dado {dado_txt}, Quando {quando_txt} na transferencia para ATH, Então é direcionado para taxonomia {alvo}"
            )
            nota = "" if pontos > 0 and not perda else " [condições do cenário não localizadas na SPEC: caminho padrão até a transferência; preparar a massa conforme o EEP]"
            self._add_ct(
                bloco_idx, bloco_nome, destino,
                f"Cenário {numero} — {descr_cond}",
                perfil_ef, completo, regressivo=False, gherkin_override=gherkin,
                transicao_final=t if len(completo) > len(caminho) else None,
                sp_legado=True, restricoes=restr,
                acao_final="Encerrar a chamada e validar o target",
                resultado_inicial=f"{'Target' if rotulo_alvo.lower().startswith('target') else rotulo_alvo} {alvo}{nota}",
                condicoes_massa=[(k, v) for k, v in campos if not re.fullmatch(r"cen[aá]rio", k.strip(), re.IGNORECASE)
                                 and not re.search(r"target|vdn|\bid\b", k, re.IGNORECASE)]
                + [(f"{rotulo_alvo} esperado", alvo)],
            )

    def gerar_cts_tipo_b(self):
        if self.eep_model.get("cenarios_transferencia") or self.eep_model.get("tipo_b_transferencia"):
            return self.gerar_cts_transferencia()
        lista_abas = self.spec_model["lista_abas"]
        estados_transfer = [a for a in lista_abas if "transfer" in a.lower()]
        estado_alvo = estados_transfer[0] if estados_transfer else (lista_abas[0] if lista_abas else None)
        if not estado_alvo:
            return

        chaves = self.eep_model.get("chaves") or ["Chave de elegibilidade não identificada no EEP"]
        bloco_idx = 1
        bloco_nome = f"Bloco {bloco_idx}"
        cor = self._cor_bloco(bloco_idx)
        self._blocos.append({"numero": bloco_idx, "nome": bloco_nome, "cor": cor, "titulo": f"{bloco_nome} — {estado_alvo}"})

        total_chaves = len(chaves)
        for idx, chave in enumerate(chaves):
            self._progresso(
                int(5 + 75 * idx / max(total_chaves, 1)),
                f"Gerando cobertura por produto {idx + 1} de {total_chaves} ({chave})...",
            )
            caminho, perfil_efetivo = self._bfs(self.spec_model, estado_alvo, perfil_entrada="aninao")
            self._add_ct(
                bloco_idx,
                bloco_nome,
                estado_alvo,
                f"Regra de transferência especializada via chave {chave}",
                perfil_efetivo,
                caminho,
            )

    # ---------- L9: fraseologia obrigatoria p/ prompts na cor do projeto ----------

    def _via_para(self, destino):
        """Estado de uma SPEC ANTERIOR por onde o cliente precisa passar para chegar a `destino` (numa SPEC seguinte):
        o changelog do destino cita o contexto de entrada (ex.: "usuarios que aceitaram o chute de ativacao de chip na
        URAID" -> estado ChuteAtivacaoChip_CM da URAID). Sem isso, o BFS escolheria qualquer outro caminho ate la."""
        if destino in self._via_cache:
            return self._via_cache[destino]
        via = None
        estados = self.spec_model["estados"]
        specs = [x["rotulo"] for x in self.spec_model.get("_specs", [])]
        spec_destino = (estados.get(destino) or {}).get("spec")
        if spec_destino in specs and specs.index(spec_destino) > 0:
            alteradas = self.spec_model["versionamento"].get("estados_alterados", [])
            texto = " ".join(e.get("alteracao") or "" for e in alteradas if e["nome"] == destino)
            alvo = normalizar_chave(texto).replace("_", "")
            melhor = (1, None)  # exige 2+ palavras do nome do estado no texto
            for e in alteradas:
                nome = e["nome"]
                spec_e = (estados.get(nome) or {}).get("spec")
                if spec_e not in specs or specs.index(spec_e) >= specs.index(spec_destino) or nome not in estados:
                    continue
                original = estados[nome].get("nome_original") or nome
                palavras = [normalizar_chave(w).replace("_", "") for w in re.findall(r"[A-Z][a-z]+|[A-Z]+(?![a-z])|\d+", original)]
                palavras = [w for w in palavras if len(w) >= 4]
                if len(palavras) >= 2 and all(w in alvo for w in palavras) and len(palavras) > melhor[0]:
                    melhor = (len(palavras), nome)
            via = melhor[1]
        self._via_cache[destino] = via
        return via

    def _bfs_encadeado(self, spec_model, destino_nome, perfil_entrada="aninao", restricoes_extra=None, modo_entrada="nativa", cenario=None):
        base, perfil_base = self._bfs_base(spec_model, destino_nome, perfil_entrada, restricoes_extra, modo_entrada, cenario)
        via = self._via_para(destino_nome) if modo_entrada == "nativa" else None
        if not via or not base or via in base or via == destino_nome:
            return base, perfil_base
        cam1, perf1 = bfs_caminho_entrada(spec_model, via, perfil_entrada, restricoes_extra, "nativa")
        if not cam1:
            return base, perfil_base
        cam2, perf2 = bfs_caminho_entrada(spec_model, destino_nome, perf1, None, "nativa", inicio=via, bloqueados=set(cam1[:-1]))
        if not cam2:
            return base, perfil_base
        cache = spec_model.setdefault("_hops_cache", {})
        hops1 = cache.get((perf1, tuple(cam1)))
        hops2 = cache.get((perf2, tuple(cam2)))
        if hops1 is None or hops2 is None:
            return base, perfil_base
        completo = cam1 + cam2[1:]
        cache[(perf1, tuple(completo))] = list(hops1) + list(hops2)
        self._notas_via = getattr(self, "_notas_via", {})
        self._notas_via[destino_nome] = via
        return completo, perf1

    def _bfs_completo(self, spec_model, destino_nome, perfil_entrada="aninao", restricoes_extra=None, modo_entrada="nativa", cenario=None):
        """Modo SPEC completa: nenhum estado pode ficar de fora. Sem caminho a partir do _Start_, tenta pelos
        ESTADOS ANTERIORES declarados na aba do estado; em ultimo caso o CT entra direto no estado, com aviso."""
        caminho, perfil = bfs_caminho_entrada(spec_model, destino_nome, perfil_entrada, restricoes_extra, modo_entrada, cenario)
        if caminho or modo_entrada != "nativa":
            return caminho, perfil
        estados = spec_model["estados"]
        for ant in (estados.get(destino_nome) or {}).get("estados_anteriores", []):
            p = resolver_destino(spec_model["mapa_rotas"], ant) or ant
            if p in estados and p != destino_nome:
                cam_p, perf_p = bfs_caminho_entrada(spec_model, p, perfil_entrada, None, "nativa")
                if cam_p:
                    self._notas_caminho[destino_nome] = f"ENTRADA PELO ESTADO ANTERIOR {p} (a SPEC não traz a transição explícita)"
                    return cam_p + [destino_nome], perf_p
        self._notas_caminho[destino_nome] = "SEM CAMINHO A PARTIR DO _START_ (estado de apoio ou entrada vinda de outra URA)"
        return [destino_nome], perfil_entrada

    def _estados_em_ordem_de_fluxo(self):
        """Todos os estados com aba: primeiro os alcancaveis a partir do _Start_ (ordem de descoberta), depois os
        demais — que ganham aviso em Revisao Necessaria (sem caminho de entrada)."""
        from collections import deque

        estados = self.spec_model["estados"]
        mapa = self.spec_model["mapa_rotas"]
        inicio = _detectar_start_state(self.spec_model)
        ordem, vistos = [], set()
        fila = deque([inicio] if inicio else [])
        while fila:
            atual = fila.popleft()
            if atual in vistos or atual not in estados:
                continue
            vistos.add(atual)
            ordem.append(atual)
            for t in estados[atual].get("transicoes", []):
                dest = resolver_destino(mapa, t.get("destino"))
                if dest and dest not in vistos:
                    fila.append(dest)
        restantes = [n for n in estados if n not in vistos]
        if restantes:
            self.revisao_necessaria.append(
                {
                    "tipo": "info_estados_inalcancaveis",
                    "detalhe": f"{len(restantes)} estado(s) da SPEC não são alcançáveis a partir do _Start_ pelas transições "
                    "lidas e entram sem caminho de entrada: " + ", ".join(restantes[:25]) + (" …" if len(restantes) > 25 else ""),
                }
            )
        return ordem + restantes

    def gerar_cts_concat(self):
        """
        Estados cuja alteracao cita "concat" (montagem dinamica do prompt, tempo de silencio entre
        trechos...): cada VARIACAO de montagem descrita no estado ("Exemplo se o cliente tem 1
        produto", "...todos os produtos", "...base de Repeticao") vira um CT; as tentativas de uma
        mesma escada (REJ1+REJ2, RPT1+RPT2, SIL) ficam juntas, como nas demais escadas.
        """
        estados = getattr(self, "_estados_alterados_ref", None) or []
        bloco_idx = len(self._blocos) + 1
        criado_bloco = False
        for est in estados:
            if not _ALT_CONCAT_RE.search(est.get("alteracao") or ""):
                continue
            nome_real = resolver_destino(self.spec_model["mapa_rotas"], est["nome"]) or est["nome"]
            exemplos = (self.spec_model["estados"].get(nome_real) or {}).get("concat_exemplos") or []
            if not exemplos:
                continue
            caminho, perfil_efetivo = self._bfs(self.spec_model, nome_real, perfil_entrada="aninao")
            if not caminho:
                continue
            perfil_txt = "ANINÃO" if perfil_efetivo == "aninao" else "ANISIM"

            grupos = {}
            for ex in exemplos:
                m = _FAMILIA_CONCAT_RE.search(ex["titulo"].replace("Exemplo", "", 1))
                chave = (ex["secao"], m.group(1).upper()) if m else (ex["secao"], "VAR", ex["titulo"])
                grupos.setdefault(chave, []).append(ex)

            for chave, lista in grupos.items():
                if not criado_bloco:
                    bloco_nome = f"Bloco {bloco_idx}"
                    self._blocos.append(
                        {"numero": bloco_idx, "nome": bloco_nome, "cor": self._cor_bloco(bloco_idx), "titulo": f"{bloco_nome} — Concat {nome_real}"}
                    )
                    criado_bloco = True
                secao = chave[0]
                condicao_secao = ""
                m_ch = re.search(r"CHAVE\s+([A-Za-z0-9_]+)", secao, re.IGNORECASE)
                if m_ch:
                    condicao_secao = f" (chave {m_ch.group(1)} ativa)"
                elif secao and not re.fullmatch(r"EXEMPLOS DE CONCAT:?", secao.strip(), re.IGNORECASE):
                    condicao_secao = " (" + secao[:80].capitalize() + ")"
                else:
                    condicao_secao = " (regra geral — chave desativada)"

                steps_extra, sps = [], []
                for ex in lista:
                    rotulo = re.sub(r"^\s*Exemplo\s*", "", ex["titulo"], flags=re.IGNORECASE).strip(" :") or ex["titulo"]
                    tempos = sorted({f"{n} ms" for n in re.findall(r"(\d+)\s*ms", ex["concat"] or "")})
                    detalhe = f"Concat: {ex['concat']}" if ex["concat"] else ""
                    if tempos:
                        detalhe += f" | silêncio entre os trechos: {', '.join(tempos)}"
                    steps_extra.append(
                        {
                            "step_num": 0,
                            "acao": f"Ouvir a montagem do prompt — {rotulo}",
                            "estado": nome_real,
                            "prompt_id": f"{nome_real}_Concat",
                            "prompt_texto": ex["texto"],
                            "sp": ex.get("sp"),
                            "resultado": (f"{ex['sp'][0]}={ex['sp'][1]} — " if ex.get("sp") else "") + ex["texto"] + (f" | {detalhe}" if detalhe else ""),
                        }
                    )
                    if ex.get("sp") and ex["sp"] not in sps:
                        sps.append(ex["sp"])

                rotulos = " / ".join(
                    re.sub(r"^\s*Exemplo\s*", "", e["titulo"], flags=re.IGNORECASE).strip(" :") for e in lista
                )
                if len(chave) == 3:
                    perfil_variacao = re.sub(r"^(se )?(o )?", "", rotulos.strip(" ."), flags=re.IGNORECASE)
                    quando = f"entrar no estado {nome_real} — {perfil_variacao[:90]}"
                else:
                    fam = {"REJ": "errar a opção", "RPT": "pedir para repetir as opções", "SIL": "ficar em silêncio"}[chave[1]]
                    quando = f"o cliente {fam} ({len(lista)} tentativa(s))"
                gherkin = (
                    f"Dado cliente {perfil_txt}{condicao_secao}, Quando {quando}, Então a locução deve ser montada "
                    f"conforme o Concat da SPEC, com o tempo de silêncio entre os trechos."
                )
                self._add_ct(
                    bloco_idx,
                    f"Bloco {bloco_idx}",
                    nome_real,
                    f"Concat — {rotulos[:120]}{condicao_secao}",
                    perfil_efetivo,
                    caminho,
                    sp_final=sps[0] if sps else None,
                    sps_todos=sps,
                    gherkin_override=gherkin,
                    steps_extra=steps_extra,
                )

    def _transicao_que_toca_prompt(self, estado, prompt):
        """(origem, transicao) de uma transicao que leva a `estado` tocando `prompt` como
        proximo prompt — da o caminho exato (e a variante, ex.: Casa/Empresa) ate ele.
        Usa um indice montado UMA vez (a busca ingenua era cubica em SPECs grandes)."""
        if not hasattr(self, "_idx_prompt_transicao"):
            mapa = self.spec_model["mapa_rotas"]
            estados = self.spec_model["estados"]
            idx = {}
            for origem, dados_origem in estados.items():
                for t in dados_origem.get("transicoes", []):
                    alvo = (t.get("prox_prompt") or "").strip()
                    if not alvo:
                        continue
                    destino = resolver_destino(mapa, t.get("destino"))
                    if not destino or destino not in estados:
                        continue
                    casado = _achar_prompt_por_id(estados[destino].get("prompts", []), normalizar_chave(alvo))
                    if casado:
                        idx.setdefault((destino, casado["id"]), (origem, t))
            self._idx_prompt_transicao = idx
        return self._idx_prompt_transicao.get((estado, prompt["id"]), (None, None))

    def gerar_cts_fraseologia(self, itens_cor):
        """
        L9: prompts NOVOS (celulas na cor da versao, na tabela de prompts do estado) precisam
        ser validados — texto da locucao e, nas tentativas de erro/silencio, a escada completa.
        Agrupa por variante (ex.: Casa/Empresa) e tipo: 1 CT por INI, 1 CT por escada REJ,
        1 CT por escada SIL (REJ1+REJ2 juntos, SIL1+SIL2 juntos), e 1 CT por prompt avulso.
        Prompts que ja aparecem em algum step de outro CT nao geram CT duplicado.
        """
        itens_cor = dict(itens_cor or {})
        if self.modo_completo:
            for nome_estado, dados_estado in self.spec_model["estados"].items():
                itens_cor[nome_estado] = [(0, 0, p["id"], "") for p in dados_estado.get("prompts", [])]
        if not self._sps_novos and not self.modo_completo:
            # Sem SP novo, os prompts que o changelog cita ("*_AgendamentoDeVT"...) sao os novos.
            for estado_nome, (tokens_prompt, _chaves, _dtmfs) in self._dicas_por_estado.items():
                sd = self.spec_model["estados"].get(estado_nome, {})
                sinteticos = [
                    (0, 0, p["id"], "")
                    for p in sd.get("prompts", [])
                    if any(tok in normalizar_chave(p["id"]) for tok in tokens_prompt)
                ]
                if sinteticos:
                    itens_cor.setdefault(estado_nome, []).extend(sinteticos)
        if not itens_cor:
            return
        cobertos = {p["prompt_id"] for c in self.casos_teste for p in c["steps"] if p.get("prompt_id") not in (None, "—")}
        bloco_idx = len(self._blocos) + 1
        criado_bloco = False
        familia_re = re.compile(r"(?<![a-z])(INI|Ini|REJ|Rej|SIL|Sil)(\d?)(?=_|$)")
        ordem_familia = {"ini": 0, "rej": 1, "sil": 2}

        def _classificar(pid):
            m = familia_re.search(pid)
            if not m:
                return ("outro", normalizar_chave(pid), 0)
            return (m.group(1).lower(), normalizar_chave(pid[: m.start()] + pid[m.end():]), int(m.group(2) or 1))

        for aba, itens in itens_cor.items():
            estado = resolver_destino(self.spec_model["mapa_rotas"], aba) or aba
            state_data = self.spec_model["estados"].get(estado)
            if not state_data or not state_data.get("prompts"):
                continue

            novos, vistos = [], set()
            for _row, _col, valor, _cont in itens:
                prompt = next((p for p in state_data["prompts"] if normalizar_chave(valor) == normalizar_chave(p["id"])), None)
                if prompt and prompt["id"] not in vistos and prompt["id"] not in cobertos:
                    vistos.add(prompt["id"])
                    novos.append(prompt)
            if not novos:
                continue

            if self.modo_completo:
                # SPEC inteira: um CT por estado (em lotes de 12 prompts) com um step por prompt ainda nao ouvido,
                # em vez de um CT por prompt/variante — mantem 100% de cobertura sem milhares de CTs.
                def _ordem_prompt(p):
                    fam = _classificar(p["id"])[0]
                    return {"ini": 0, "rej": 1, "sil": 2}.get(fam, 3)

                novos_ord = sorted(novos, key=_ordem_prompt)
                caminho_e, perfil_e = self._bfs(self.spec_model, estado, perfil_entrada="aninao")
                if not caminho_e:
                    continue
                for ini_lote in range(0, len(novos_ord), 12):
                    lote = novos_ord[ini_lote:ini_lote + 12]
                    if not criado_bloco:
                        bloco_nome = f"Bloco {bloco_idx}"
                        self._blocos.append(
                            {"numero": bloco_idx, "nome": bloco_nome, "cor": self._cor_bloco(bloco_idx), "titulo": f"{bloco_nome} — Fraseologia"}
                        )
                        criado_bloco = True
                    steps_lote = [
                        {
                            "step_num": 0,
                            "acao": f"Ouvir o prompt {p['id']}",
                            "estado": estado,
                            "prompt_id": p["id"],
                            "prompt_texto": p["texto"] or "—",
                            "sp": p.get("sp"),
                            "resultado": (f"{p['sp'][0]}={p['sp'][1]} — " if p.get("sp") else "") + (p["texto"] or "—"),
                        }
                        for p in lote
                    ]
                    ids_lote = ", ".join(p["id"] for p in lote)
                    sps_lote = []
                    for p in lote:
                        if p.get("sp") and p["sp"] not in sps_lote:
                            sps_lote.append(p["sp"])
                    self._add_ct(
                        bloco_idx, f"Bloco {bloco_idx}", estado,
                        f"Fraseologia completa — prompts do estado ({len(lote)}): {ids_lote}",
                        perfil_e, caminho_e, sp_final=sps_lote[0] if sps_lote else None, sps_todos=sps_lote,
                        gherkin_override=f"Dado cliente {'ANINÃO' if perfil_e == 'aninao' else 'ANISIM'}, Quando chegar ao estado {estado}, "
                        f"Então devem tocar os prompts {lote[0]['id']}{' … ' + lote[-1]['id'] if len(lote) > 1 else ''} conforme a SPEC.",
                        steps_extra=steps_lote,
                    )
                cobertos.update(p["id"] for p in novos)
                continue

            grupos = {}
            for prompt in novos:
                familia, variante, n = _classificar(prompt["id"])
                chave = (variante, familia) if familia != "outro" else (prompt["id"], "outro")
                grupos.setdefault(chave, []).append((n, prompt))

            def _ordem(item):
                (variante, familia), _ps = item
                return (variante, ordem_familia.get(familia, 3))

            for (variante, familia), lista in sorted(grupos.items(), key=_ordem):
                lista.sort(key=lambda x: x[0])
                prompts = [p for _n, p in lista]
                ids = ", ".join(p["id"] for p in prompts)

                # Caminho: o da transicao que toca o INI/prompt dessa variante (traz Casa/Empresa etc.).
                referencia = prompts[0]
                if familia in ("rej", "sil"):
                    ini = next(
                        (p for p in state_data["prompts"]
                         if _classificar(p["id"])[:2] == ("ini", variante)),
                        None,
                    )
                    referencia = ini or prompts[0]
                origem, t_ref = self._transicao_que_toca_prompt(estado, referencia)
                if origem:
                    caminho_origem, perfil_efetivo = self._bfs(self.spec_model, origem, perfil_entrada="aninao")
                    caminho = (caminho_origem + [estado]) if caminho_origem else []
                else:
                    t_ref = None
                    caminho, perfil_efetivo = self._bfs(self.spec_model, estado, perfil_entrada="aninao")
                if not caminho:
                    caminho, perfil_efetivo = self._bfs(self.spec_model, estado, perfil_entrada="aninao")
                if not caminho:
                    continue
                perfil_txt = "ANINÃO" if perfil_efetivo == "aninao" else "ANISIM"

                steps_extra = []
                if familia in ("rej", "sil"):
                    for n, p in lista:
                        rotulo = (
                            f"Digitar entrada inválida ({n}ª tentativa — REJ{n})"
                            if familia == "rej"
                            else f"Permanecer em silêncio ({n}ª tentativa — SIL{n})"
                        )
                        sp_p = p.get("sp")
                        texto = p["texto"] or "—"
                        steps_extra.append(
                            {
                                "step_num": 0,
                                "acao": rotulo,
                                "estado": estado,
                                "prompt_id": p["id"],
                                "prompt_texto": texto,
                                "sp": sp_p,
                                "resultado": (f"{sp_p[0]}={sp_p[1]} — {texto}" if sp_p else texto),
                            }
                        )
                    quando = (
                        f"o cliente errar a entrada {len(lista)} vez(es)"
                        if familia == "rej"
                        else f"o cliente ficar em silêncio {len(lista)} vez(es)"
                    )
                    gherkin = f"Dado cliente {perfil_txt} no estado {estado}, Quando {quando}, Então devem tocar {ids}, na ordem, conforme a SPEC."
                    tipo_txt = "escada REJ" if familia == "rej" else "escada SIL"
                else:
                    if not origem:  # sem transicao dedicada: valida o prompt explicitamente
                        p = prompts[0]
                        steps_extra.append(
                            {
                                "step_num": 0,
                                "acao": "Aguardar a reprodução do prompt",
                                "estado": estado,
                                "prompt_id": p["id"],
                                "prompt_texto": p["texto"] or "—",
                                "sp": p.get("sp"),
                                "resultado": p["texto"] or "—",
                            }
                        )
                    gherkin = (
                        f"Dado cliente {perfil_txt} chega ao estado {estado}, Quando o prompt {ids} for reproduzido, "
                        f"Então a locução deve corresponder fielmente ao texto da SPEC."
                    )
                    tipo_txt = "prompt"

                if not criado_bloco:
                    bloco_nome = f"Bloco {bloco_idx}"
                    self._blocos.append(
                        {"numero": bloco_idx, "nome": bloco_nome, "cor": self._cor_bloco(bloco_idx), "titulo": f"{bloco_nome} — Fraseologia"}
                    )
                    criado_bloco = True

                sps_prompts = []
                for p in prompts:
                    if p.get("sp") and p["sp"] not in sps_prompts:
                        sps_prompts.append(p["sp"])
                self._add_ct(
                    bloco_idx,
                    f"Bloco {bloco_idx}",
                    estado,
                    f"Fraseologia nova (L9) — {tipo_txt}: {ids}",
                    perfil_efetivo,
                    caminho,
                    sp_final=sps_prompts[0] if sps_prompts else None,
                    sps_todos=sps_prompts,
                    gherkin_override=gherkin,
                    steps_extra=steps_extra,
                    transicao_final=t_ref,
                )
                cobertos.update(p["id"] for p in prompts)

    # ---------- L3/L5/L11: bloco REGRESSIVO ----------

    def gerar_regressao_dirigida(self, bloco_idx, bloco_nome):
        """
        Regressao baseada em risco, ligada ao que ESTA versao tocou (alem dos 2 CTs fixos):
          1. SAIDAS legadas: para cada estado alterado, uma transicao por estado de destino que
             nao ganhou CT funcional (prioriza as que ja tem SP de versao anterior);
          2. ENTRADAS alternativas: caminhos que chegam ao estado alterado por outro estado anterior;
          3. ANI SIM: o estado alterado tambem funciona para cliente identificado;
          4. CHAVES desativadas citadas nas condicoes do estado (comportamento legado).
        Limites por estado e no total mantem o volume razoavel.
        """
        CAP_SAIDAS_ESTADO, CAP_SAIDAS_TOTAL, CAP_ENTRADAS_TOTAL, CAP_CHAVES, CAP_ANI_SIM = 3, 12, 4, 3, 4
        estados_spec = self.spec_model["estados"]
        mapa = self.spec_model["mapa_rotas"]
        resumo = {"saídas legadas": 0, "entradas alternativas": 0, "ANI Sim": 0, "chaves desativadas": 0}

        alterados, vistos = [], set()
        for est in getattr(self, "_estados_alterados_ref", None) or []:
            nome_real = resolver_destino(mapa, est["nome"]) or est["nome"]
            if nome_real in estados_spec and nome_real not in vistos:
                vistos.add(nome_real)
                alterados.append(nome_real)
        if not alterados:
            return

        def _perfil_txt(perfil):
            return "ANINÃO" if perfil == "aninao" else "ANISIM"

        cobertos_saida = {
            (c["estado"], c["caminho_qa"][-1])
            for c in self.casos_teste
            if len(c.get("caminho_qa") or []) >= 2 and c["caminho_qa"][-1] != c["estado"]
        }
        chaves_usadas = set()
        for c in self.casos_teste:
            if c.get("regressivo"):
                m = re.search(r"chave\s+([A-Za-zÀ-ú0-9_]+)", c.get("alteracao_relatada") or "", re.IGNORECASE)
                if m:
                    chaves_usadas.add(m.group(1).lower())

        # 1) saidas legadas
        total_saidas = 0
        for nome in alterados:
            if total_saidas >= CAP_SAIDAS_TOTAL:
                break
            por_destino = {}
            for t in estados_spec[nome].get("transicoes", []):
                if _chave_grupo_retentativa(t) is not None or _eh_transicao_rej_sil(t["condicao"]):
                    continue
                destino = resolver_destino(mapa, t.get("destino"))
                if not destino or destino == nome or (nome, destino) in cobertos_saida:
                    continue
                sp = _sp_efetivo_transicao(self.spec_model, nome, t)
                if sp and self._sps_novos and sp[1] in self._sps_novos:
                    continue  # SP novo: ja tem CT funcional
                score = 2 if sp else 1
                atual = por_destino.get(destino)
                if atual is None or score > atual[0]:
                    por_destino[destino] = (score, t, sp)
            escolhidos = sorted(por_destino.items(), key=lambda kv: -kv[1][0])[:CAP_SAIDAS_ESTADO]
            for destino, (_score, t, sp) in escolhidos:
                if total_saidas >= CAP_SAIDAS_TOTAL:
                    break
                restr = extrair_restricoes_sessao(t["condicao"])
                caminho, perfil_ef = self._bfs(self.spec_model, nome, perfil_entrada=restr.get("ani", "aninao"), restricoes_extra=restr
                )
                if not caminho:
                    continue
                restr = dict(restr)
                restr["ani"] = perfil_ef
                completo = caminho + ([destino] if destino != caminho[-1] else [])
                cond_curta = (t["condicao"] or "")[-90:]
                gherkin = (
                    f"Dado cliente {_perfil_txt(perfil_ef)}, Quando seguir a condição '{cond_curta}' no estado {nome}, "
                    f"Então o fluxo segue para {destino}"
                    + (f" e o SP legado {sp[0]}={sp[1]} continua sendo registrado." if sp else " sem mudança de comportamento.")
                )
                caso = self._add_ct(
                    bloco_idx, bloco_nome, nome, f"Regressão — saída legada {nome} → {destino} preservada",
                    perfil_ef, completo, sp_final=sp, regressivo=True, gherkin_override=gherkin,
                    restricoes=restr, transicao_final=t if len(completo) > len(caminho) else None,
                )
                if caso:
                    total_saidas += 1
                    resumo["saídas legadas"] += 1
                    cobertos_saida.add((nome, destino))

        # 2) entradas alternativas + 3) ANI Sim
        total_entradas = 0
        for nome in alterados:
            sd = estados_spec[nome]
            usadas = {
                c["caminho_qa"][-2]
                for c in self.casos_teste
                if c["estado"] == nome and len(c.get("caminho_qa") or []) >= 2 and c["caminho_qa"][-1] == nome
            }
            feitas_estado = 0
            for ant in sd.get("estados_anteriores", []):
                if total_entradas >= CAP_ENTRADAS_TOTAL or feitas_estado >= 2:
                    break
                p = resolver_destino(mapa, ant) or ant
                if p in usadas or p == nome or p not in estados_spec:
                    continue
                t_ent = next(
                    (t for t in estados_spec[p].get("transicoes", []) if resolver_destino(mapa, t.get("destino")) == nome), None
                )
                if not t_ent:
                    continue
                cam_p, perfil_ef = self._bfs(self.spec_model, p, perfil_entrada="aninao")
                if not cam_p:
                    continue
                gherkin = (
                    f"Dado cliente {_perfil_txt(perfil_ef)}, Quando chegar ao estado {nome} vindo de {p}, "
                    "Então o estado deve se comportar como antes (entrada alternativa preservada)."
                )
                caso = self._add_ct(
                    bloco_idx, bloco_nome, nome, f"Regressão — entrada alternativa por {p}", perfil_ef,
                    cam_p + [nome], sp_final=_sp_efetivo_transicao(self.spec_model, p, t_ent), regressivo=True,
                    gherkin_override=gherkin, transicao_final=t_ent,
                )
                if caso:
                    total_entradas += 1
                    feitas_estado += 1
                    resumo["entradas alternativas"] += 1

            do_estado = [c for c in self.casos_teste if c["estado"] == nome and not c["regressivo"]]
            if do_estado and all(c["perfil"] == "ANINÃO" for c in do_estado) and resumo["ANI Sim"] < CAP_ANI_SIM:
                cam, perfil_ef = self._bfs(self.spec_model, nome, perfil_entrada="anisim")
                if cam and perfil_ef == "anisim":
                    gherkin = (
                        f"Dado cliente ANISIM, Quando percorrer o caminho de entrada até o estado {nome}, "
                        "Então o estado deve funcionar para cliente identificado, sem regressão."
                    )
                    caso = self._add_ct(
                        bloco_idx, bloco_nome, nome, "Regressão — cliente ANI Sim no estado alterado", perfil_ef,
                        cam, regressivo=True, gherkin_override=gherkin,
                    )
                    if caso:
                        resumo["ANI Sim"] += 1

        # 3b) entrada vinda de OUTRA URA (hand-off): o estado alterado tambem precisa funcionar
        total_cruzadas = 0
        hops_cruzados = set()
        start = _detectar_start_state(self.spec_model)
        for nome in alterados:
            if total_cruzadas >= 3 or not start:
                break
            cam_nat, _perf = self._bfs(self.spec_model, nome, perfil_entrada="aninao")
            cam_cru, perfil_ef = self._bfs(self.spec_model, nome, perfil_entrada="aninao", modo_entrada="cruzada")
            if not cam_cru or len(cam_cru) < 2 or (len(cam_nat) > 1 and cam_nat[1] == cam_cru[1]):
                continue
            hop = next(
                (t for t in estados_spec[start].get("transicoes", [])
                 if resolver_destino(mapa, t.get("destino")) == cam_cru[1] and _eh_entrada_cruzada(t, self.spec_model)),
                None,
            )
            origem_txt = (hop["condicao"][-90:] if hop else "outra URA")
            if origem_txt in hops_cruzados:
                continue  # um CT por hand-off distinto basta
            hops_cruzados.add(origem_txt)
            gherkin = (
                f"Dado cliente {_perfil_txt(perfil_ef)} vindo de outra URA ({origem_txt}), Quando chegar ao estado {nome}, "
                "Então o estado deve se comportar como na entrada nativa."
            )
            caso = self._add_ct(
                bloco_idx, bloco_nome, nome, f"Regressão — entrada vinda de outra URA ({origem_txt})", perfil_ef,
                cam_cru, regressivo=True, gherkin_override=gherkin,
            )
            if caso:
                total_cruzadas += 1
                resumo["entradas de outra URA"] = resumo.get("entradas de outra URA", 0) + 1

        # 4) chaves desativadas citadas nas condicoes dos estados alterados
        for nome in alterados:
            if resumo["chaves desativadas"] >= CAP_CHAVES:
                break
            for t in estados_spec[nome].get("transicoes", []):
                m = _CHAVE_DESATIVADA_RE.search(t["condicao"] or "")
                if not m or m.group(1).lower() in chaves_usadas:
                    continue
                chaves_usadas.add(m.group(1).lower())
                restr = extrair_restricoes_sessao(t["condicao"])
                caminho, perfil_ef = self._bfs(self.spec_model, nome, perfil_entrada=restr.get("ani", "aninao"), restricoes_extra=restr
                )
                if not caminho:
                    continue
                destino = resolver_destino(mapa, t.get("destino"))
                completo = caminho + ([destino] if destino and destino != caminho[-1] else [])
                gherkin = (
                    f"Dado chave {m.group(1)} DESATIVADA, Quando o cliente percorrer o estado {nome}, "
                    "Então o fluxo legado é preservado (sem o comportamento novo)."
                )
                caso = self._add_ct(
                    bloco_idx, bloco_nome, nome, f"Regressão (L5) — chave {m.group(1)} DESATIVADA: legado preservado",
                    perfil_ef, completo, sp_final=_sp_efetivo_transicao(self.spec_model, nome, t), regressivo=True,
                    gherkin_override=gherkin, restricoes=restr,
                    transicao_final=t if len(completo) > len(caminho) else None,
                )
                if caso:
                    resumo["chaves desativadas"] += 1
                break

        total = sum(resumo.values())
        if total:
            self.revisao_necessaria.append(
                {
                    "tipo": "info_regressao_dirigida",
                    "detalhe": f"Regressão baseada em risco: {total} CT(s) além dos 2 fixos — "
                    + ", ".join(f"{n} {k}" for k, n in resumo.items() if n)
                    + ". Cobrem as saídas legadas, entradas alternativas e perfil ANI Sim dos estados alterados. "
                    "Não cobrem estados que a versão não tocou nem VDNs/filas (testar à parte).",
                }
            )

    def gerar_bloco_regressivo(self):
        """
        Bloco REGRESSIVO enxuto e objetivo (L3): so o que e realmente
        necessario pra garantir que o fluxo legado nao regrediu — 1 CT de
        chave DESATIVADA (L5) + 1 CT de situacaoInstalacao (L11), sempre
        ligados aos estados/SPs que ESTA versao de fato tocou. Nao gera CT
        especulativo de VDN/MPL (L10) automaticamente, porque o EEP nao
        distingue "VDN nova desta versao" de "toda VDN mencionada no
        documento" — isso vira nota em Revisão Necessária, nao CT chutado.
        """
        bloco_idx = len(self._blocos) + 1
        bloco_nome = "Regressivo"
        self._blocos.append({"numero": bloco_idx, "nome": bloco_nome, "cor": REGRESSIVO_COR, "titulo": f"{bloco_nome} — Preservação do fluxo legado"})

        candidatos = [c for c in self.casos_teste if c.get("sp_final") and not c["regressivo"]]
        if candidatos:
            c = candidatos[0]
            m = re.search(r"chave\s+([A-Za-zÀ-ú0-9_]+)", c["alteracao_relatada"], re.IGNORECASE)
            chave = m.group(1) if m else "de elegibilidade"
            if m and any(
                "ramo oposto" in (x.get("alteracao_relatada") or "").lower() and chave.lower() in (x.get("alteracao_relatada") or "").lower()
                for x in self.casos_teste
            ):
                candidatos = []  # o ramo oposto (chave desativada) ja foi validado de verdade nos CTs funcionais
        if candidatos:
            c = candidatos[0]
            m = re.search(r"chave\s+([A-Za-zÀ-ú0-9_]+)", c["alteracao_relatada"], re.IGNORECASE)
            chave = m.group(1) if m else "de elegibilidade"
            gherkin = abreviar_gherkin(
                f"Dado chave {chave} DESATIVADA (L5), Quando o cliente repete a jornada até {c['estado']}, "
                f"Então o fluxo legado é preservado e o SP {c['sp_final']} NÃO deve ser registrado."
            )
            self._add_ct(
                bloco_idx,
                bloco_nome,
                c["estado"],
                f"Regressivo (L5) — validação de chave {chave} DESATIVADA",
                "aninao",
                c["caminho_qa"],
                regressivo=True,
                gherkin_override=gherkin,
            )

        estado_api = next((a for a in self.spec_model["lista_abas"] if "menu" in a.lower() or "identifica" in a.lower()), None)
        if estado_api:
            caminho, perfil_efetivo = self._bfs(self.spec_model, estado_api, perfil_entrada="anisim")
            perfil_txt = "ANISIM" if perfil_efetivo == "anisim" else "ANINÃO"
            gherkin = abreviar_gherkin(
                f"Dado cliente {perfil_txt} com situacaoInstalacaoProdutoServico diferente de ATIVO (L11), "
                f"Quando consultar a API de produto no estado {estado_api}, "
                "Então a URA não deve tratar o produto como elegível/ativo."
            )
            self._add_ct(
                bloco_idx,
                bloco_nome,
                estado_api,
                "Regressivo (L11) — situacaoInstalacaoProdutoServico != ATIVO",
                perfil_efetivo,
                caminho,
                regressivo=True,
                gherkin_override=gherkin,
            )

        self.gerar_regressao_dirigida(bloco_idx, bloco_nome)

        vdns = self.eep_model.get("vdns", [])
        if vdns:
            self.revisao_necessaria.append(
                {
                    "tipo": "info_vdns_nao_testadas_automaticamente",
                    "detalhe": f"{len(vdns)} VDN(s) foram extraídas do EEP, mas o motor não sabe distinguir "
                    "quais são realmente novas desta versão (L10) — nenhum CT de MPL/VDN foi gerado "
                    "automaticamente pra evitar teste especulativo. Se alguma VDN é nova nesta versão, "
                    "avalie incluir manualmente o CT de MPL correspondente.",
                }
            )

    def sps_regressao(self):
        """ScriptPoints JA EXISTENTES (producao) que os CTs regressivos conferem."""
        descricoes = {}
        for dados_estado in self.spec_model["estados"].values():
            for item in list(dados_estado.get("transicoes", [])) + list(dados_estado.get("prompts", [])):
                bruto = item.get("sp_raw") or ""
                sp = item.get("sp")
                m = re.match(r"^\s*(\d{3,8})\s*[-–]\s*(.+)$", bruto)
                if sp and m and m.group(1) == sp[1]:
                    descricoes.setdefault(sp[1], m.group(2).strip())
        return [
            {
                "codigo": r["codigo"],
                "tipo": r["tipo"],
                "descricao": descricoes.get(r["codigo"], "—"),
                "estado": ", ".join(r["estados"]),
                "ct": ", ".join(r["cts"]),
            }
            for r in sorted(self._sp_regressao.values(), key=lambda r: (r["tipo"], r["codigo"]))
        ]

    def bi_marcacoes(self):
        estado_do_ct = {c["ct_id"]: c["estado"] for c in self.casos_teste}

        def _estados_dos_cts(cts):
            vistos = []
            for ct in cts:
                e = estado_do_ct.get(ct)
                if e and e not in vistos:
                    vistos.append(e)
            return ", ".join(vistos) if vistos else "—"

        linhas = []
        for sp in self.spec_model.get("versionamento_bi", []):
            cts = self._sp_bi_cobertura.get(sp["codigo"], [])
            # Estado da marcacao: o da linha da VersionamentoBI; sem ele, o do(s) CT(s) que cobrem o SP.
            estado = (sp.get("estado") or "").strip() or _estados_dos_cts(cts)
            linhas.append(
                {"codigo": sp["codigo"], "descricao": sp["descricao"], "estado": estado, "ct": ", ".join(cts) if cts else "—"}
            )
        if not self._sps_novos:
            # Projeto SEM marcacoes de BI na VersionamentoBI (so prompts/fluxo): os SPs que aparecem
            # nos CTs sao de versoes anteriores, nao "marcacoes do projeto" — nada a listar.
            return linhas
        for codigo, cts in self._sp_bi_cobertura.items():
            if not any(l["codigo"] == codigo for l in linhas):
                linhas.append(
                    {
                        "codigo": codigo,
                        "descricao": "(marcado apenas na aba do estado, sem entrada correspondente em VersionamentoBI)",
                        "estado": _estados_dos_cts(cts),
                        "ct": ", ".join(cts),
                    }
                )
        return linhas

    def _consolidar_cts(self):
        """Com todo CT indo de ponta a ponta, CTs cujo caminho ja esta contido em outro (mesmos estados e mesmas
        transicoes, do inicio) viram UM so: o CT mais longo valida tudo o que o mais curto validava. Os SPs e as
        condicoes seguem nos steps; o texto do CT ganha "Tambem valida". Renumera os CTs e atualiza a cobertura."""
        if len(self.casos_teste) < 2:
            return
        finais = ("Encerrar a chamada", "Encerrar a chamada e validar o target")

        def assinatura(c):
            return tuple((st.get("estado"), st.get("acao")) for st in c["steps"] if st.get("acao") not in finais)

        ordem = sorted(range(len(self.casos_teste)), key=lambda i: -len(self.casos_teste[i]["steps"]))
        prefixos, fundidos, mantidos = {}, {}, set()
        for i in ordem:
            c = self.casos_teste[i]
            if c["ct_id"] in self._ids_fixos:
                mantidos.add(i)
                continue
            chave = (c["perfil"], bool(c["regressivo"]))
            sg = assinatura(c)
            sobrevivente = prefixos.get((chave, sg)) if sg else None
            if sobrevivente is not None:
                fundidos[i] = sobrevivente
                continue
            mantidos.add(i)
            for k in range(1, len(sg) + 1):
                prefixos.setdefault((chave, sg[:k]), i)
        if not fundidos:
            return

        # une as informacoes dos CTs fundidos no sobrevivente
        for i, j in sorted(fundidos.items()):
            a, b = self.casos_teste[i], self.casos_teste[j]
            b.setdefault("tambem_cobre", []).append(a["ct_id"])
            sps_b = [x.strip() for x in str(b.get("sp_final") or "").split(",") if x.strip()]
            for x in str(a.get("sp_final") or "").split(","):
                x = x.strip()
                if x and x not in sps_b:
                    sps_b.append(x)
            b["sp_final"] = ", ".join(sps_b) if sps_b else None
            alt_a = str(a.get("alteracao_relatada") or "").strip()
            if alt_a and alt_a not in str(b.get("alteracao_relatada") or ""):
                b["alteracao_relatada"] = (str(b.get("alteracao_relatada") or "") + f" | Também valida: {alt_a[:160]}").strip(" |")
            m = re.search(r"marcar o ScriptPoint ([^\s.]+)\.", b.get("gherkin") or "")
            if m and len(sps_b) > 1:
                b["gherkin"] = (b["gherkin"] or "").replace(
                    m.group(0), "marcar os ScriptPoints " + ", ".join(x.split("=")[-1] for x in sps_b) + ".", 1
                )

        # renumera
        novos = [i for i in range(len(self.casos_teste)) if i in mantidos]
        mapa_ids = {}
        for n, i in enumerate(novos, start=1):
            c = self.casos_teste[i]
            novo_id = f"CT-{n:02d}{'b' if c.get('sp_pendente') and self.tipo_a else ''}"
            mapa_ids[c["ct_id"]] = novo_id
        for i, j in fundidos.items():
            mapa_ids[self.casos_teste[i]["ct_id"]] = mapa_ids[self.casos_teste[j]["ct_id"]]
        for i in novos:
            c = self.casos_teste[i]
            c["ct_id"] = mapa_ids[c["ct_id"]]
            c["id"] = c["ct_id"].replace("CT-", "")
            c["tambem_cobre"] = [mapa_ids[x] for x in c.get("tambem_cobre", []) if x in mapa_ids]
        self.casos_teste = [self.casos_teste[i] for i in novos]
        for codigo, lista in list(self._sp_bi_cobertura.items()):
            vistos = []
            for x in lista:
                nx = mapa_ids.get(x, x)
                if nx not in vistos:
                    vistos.append(nx)
            self._sp_bi_cobertura[codigo] = vistos
        for reg in self._sp_regressao.values():
            vistos = []
            for x in reg["cts"]:
                nx = mapa_ids.get(x, x)
                if nx not in vistos:
                    vistos.append(nx)
            reg["cts"] = vistos
        self._consolidados = len(fundidos)
        self.revisao_necessaria.append(
            {
                "tipo": "info_cts_consolidados",
                "detalhe": f"{len(fundidos)} CT(s) foram unidos a outro porque todos os CTs vão de ponta a ponta e o caminho "
                "deles já estava contido no CT que os cobre (mesmos estados e transições): nada deixou de ser validado — os "
                "SPs e as condições continuam nos steps, e o texto do CT indica \"Também valida\".",
            }
        )

    def legenda_blocos(self):
        legenda = []
        for b in self._blocos:
            cts_do_bloco = [c["ct_id"] for c in self.casos_teste if c["bloco"] == b["numero"] and c["bloco_nome"] == b["nome"]]
            if not cts_do_bloco:
                continue
            sps = sorted({c["sp_final"] for c in self.casos_teste if c["bloco"] == b["numero"] and c["bloco_nome"] == b["nome"] and c["sp_final"]})
            legenda.append(
                {
                    "bloco": b["nome"],
                    "titulo": b["titulo"],
                    "cts": f"{cts_do_bloco[0]} a {cts_do_bloco[-1]}" if len(cts_do_bloco) > 1 else (cts_do_bloco[0] if cts_do_bloco else "—"),
                    "sps": ", ".join(sps) if sps else "Preservação sem novo SP",
                }
            )
        return legenda

    def _resumo_diag_versionamento(self):
        d = self.spec_model.get("diag_versionamento") or {}
        abas = ", ".join(d.get("abas") or []) or "nenhuma aba de versionamento encontrada"
        ivrs = ", ".join(d.get("ultimos_ivrs") or []) or "nenhum código IVR lido"
        sug = self.spec_model.get("ivr_sugerido")
        dica = (
            f" Pelo nome do projeto no EEP, parece ser o {sug}: troque o código no campo IVR (ou deixe em branco)."
            if sug
            else " Se você trocou de projeto, confira se o campo IVR e os arquivos (SPEC e EEP) são do mesmo projeto."
        )
        return f"[Diagnóstico] Abas de versionamento: {abas}. Últimos IVRs citados nelas: {ivrs}.{dica}"

    def gerar(self, itens_cor=None):
        if self.tipo_a:
            self.gerar_cts_tipo_a()
        else:
            self.gerar_cts_tipo_b()
        if not self.casos_teste and self.spec_model.get("ivr_resolvido"):
            return {
                "casos_teste": [],
                "revisao_necessaria": self.revisao_necessaria,
                "bi_marcacoes": self.bi_marcacoes(),
                "sps_regressao": [],
                "legenda": [],
                "blocos": [],
            }
        if self.tipo_a and not self.modo_completo and (self.eep_model.get("cenarios_transferencia") or []):
            # O EEP lista cenarios com TARGET/ID de transferencia ATH: alem dos CTs de navegacao do projeto,
            # cada cenario/target ganha o seu CT (todos precisam ser validados).
            self._progresso(78, "Gerando os CTs de transferência ATH dos cenários do EEP...")
            self.gerar_cts_transferencia()
        if not self.tipo_a:
            self._consolidar_cts()
            return {
                "casos_teste": self.casos_teste,
                "revisao_necessaria": self.revisao_necessaria,
                "bi_marcacoes": [],
                "sps_regressao": [],
                "legenda": self.legenda_blocos(),
                "blocos": self._blocos,
            }
        self._progresso(80, "Mapeando as variações de concat...")
        self.gerar_cts_concat()
        self._progresso(82, "Verificando fraseologia obrigatória (L9)...")
        self.gerar_cts_fraseologia(itens_cor or {})
        self._progresso(90, "Montando o bloco regressivo...")
        if not self.modo_completo:
            self.gerar_bloco_regressivo()
        else:
            com_ct = {c["estado"] for c in self.casos_teste}
            sem_ct = [n for n in self.spec_model["estados"] if n not in com_ct]
            if sem_ct:
                self.revisao_necessaria.append(
                    {
                        "tipo": "info_estados_sem_ct",
                        "detalhe": f"{len(sem_ct)} estado(s) da SPEC não geraram CT (sem transições, sem prompts ou só documentação): "
                        + ", ".join(sem_ct[:30]) + (" …" if len(sem_ct) > 30 else ""),
                    }
                )
        self._progresso(96, "Organizando blocos, legenda e BI...")
        if self._transicoes_fora_da_alteracao:
            self.revisao_necessaria.append(
                {
                    "tipo": "info_transicoes_fora_da_alteracao",
                    "detalhe": f"Sem ScriptPoint novo na VersionamentoBI, testei só as transições ligadas ao que o "
                    f"versionamento cita (prompts e chaves). {self._transicoes_fora_da_alteracao} transição(ões) "
                    "dos mesmos estados que não aparecem no changelog foram deixadas de fora (preservação do fluxo).",
                }
            )
        ignorados_cor = self.spec_model["versionamento"].get("ignorados_sem_cor") or []
        if ignorados_cor:
            self.revisao_necessaria.append(
                {
                    "tipo": "info_estados_sem_cor_ignorados",
                    "detalhe": "Só algumas linhas do bloco do projeto estão pintadas no versionamento; considerei apenas as "
                    "pintadas. Estados sem cor, fora do escopo: " + ", ".join(ignorados_cor) + ".",
                }
            )
        if self._transicoes_ignoradas_sp_antigo:
            self.revisao_necessaria.append(
                {
                    "tipo": "info_sp_ja_existentes_ignorados",
                    "detalhe": f"{self._transicoes_ignoradas_sp_antigo} transição(ões) com ScriptPoint já "
                    f"existente (de versão anterior, fora da lista de {len(self._sps_novos)} SP(s) novos da "
                    "VersionamentoBI) foram ignoradas — não geram CT novo por não fazerem parte do escopo desta versão.",
                }
            )
        if self._transicoes_ignoradas_sem_sp:
            self.revisao_necessaria.append(
                {
                    "tipo": "info_transicoes_sem_sp_ignoradas",
                    "detalhe": f"{self._transicoes_ignoradas_sem_sp} transição(ões) sem nenhuma marcação de "
                    "ScriptPoint foram ignoradas (não há sinal de que sejam parte desta versão — provavelmente "
                    "ramos legados do estado que nunca precisaram de SP). Se algum deles for de fato novo desta "
                    "versão mas ainda sem SP publicado (SP PENDENTE), inclua manualmente o CT correspondente.",
                }
            )
        self._consolidar_cts()
        return {
            "casos_teste": self.casos_teste,
            "revisao_necessaria": self.revisao_necessaria,
            "bi_marcacoes": self.bi_marcacoes(),
            "sps_regressao": self.sps_regressao(),
            "legenda": self.legenda_blocos(),
            "blocos": self._blocos,
        }


def gerar_plano_ct(spec_model, eep_model, tipo_a=True, itens_cor=None, progress_callback=None, modo_completo=False):
    gerador = GeradorCT(spec_model, eep_model, tipo_a=tipo_a, progress_callback=progress_callback, modo_completo=modo_completo)
    plano = gerador.gerar(itens_cor=itens_cor)
    plano["modo_completo"] = modo_completo
    return plano
