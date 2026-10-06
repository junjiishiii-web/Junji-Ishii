"""
Motor de geracao de Casos de Teste (CTs) aplicando as licoes L1-L14 da skill
de modelagem QA URA/BDD (Mutant / Claro CRN e TLV).

Este modulo e 100% deterministico: nada aqui depende de um LLM. Quando uma
classificacao exigiria julgamento contextual que a heuristica nao consegue
resolver com confianca, o item vira uma entrada em `revisao_necessaria` em vez
de virar um CT "chutado".
"""
import difflib
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


def bfs_caminho_entrada(spec_model, destino_nome, perfil_entrada="aninao", restricoes_extra=None):
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
    """
    lista_abas = spec_model["lista_abas"]
    mapa_rotas = spec_model["mapa_rotas"]
    estados = spec_model["estados"]

    start_state = _detectar_start_state(spec_model)
    if not start_state:
        return [], perfil_entrada
    if start_state == destino_nome:
        return [start_state], perfil_entrada

    extras_sem_ani = dict(restricoes_extra or {})
    extras_sem_ani.pop("ani", None)

    def _busca(perfil_ani, bloquear_hubs):
        restricoes_iniciais = {"ani": perfil_ani}
        restricoes_iniciais.update(extras_sem_ani)
        fila = deque([([start_state], restricoes_iniciais)])
        visitados = {start_state}
        while fila:
            caminho, restricoes = fila.popleft()
            atual = caminho[-1]
            if atual == destino_nome:
                return caminho
            transicoes = estados.get(atual, {}).get("transicoes", [])
            for t in transicoes:
                real_dest = resolver_destino(mapa_rotas, t["destino"])
                if not real_dest or real_dest in visitados:
                    continue
                if bloquear_hubs and _is_hub(real_dest) and real_dest != destino_nome:
                    continue
                novas = extrair_restricoes_sessao(t["condicao"])
                if verificar_conflito_sessao(restricoes, novas):
                    continue
                atualizadas = dict(restricoes)
                atualizadas.update(novas)
                visitados.add(real_dest)
                fila.append((caminho + [real_dest], atualizadas))
        return []

    perfil_alternativo = "anisim" if perfil_entrada == "aninao" else "aninao"
    for perfil_ani in (perfil_entrada, perfil_alternativo):
        for bloquear_hubs in (True, False):
            caminho = _busca(perfil_ani, bloquear_hubs)
            if caminho:
                return caminho, perfil_ani
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


_INTERATIVO_RE = re.compile(r"\bdtmf\b|digitou|tecla", re.IGNORECASE)
_ELSE_RE = re.compile(r"\belse\b|caso contr[aá]rio", re.IGNORECASE)


def _steps_jornada(spec_model, estado_atual, visitados, limite=6):
    """Continua a jornada conforme a SPEC a partir do estado em que a
    chamada acabou de cair (ex.: depois da ultima tentativa de REJ/SIL/
    INV/INC que sai pra outro estado): segue a saida automatica de cada
    estado (preferindo o "Else"/caso padrao) ate chegar num fim — _End_, um
    estado sem saida — ou num estado que aguarda a escolha do usuario
    (menu/DTMF/REJ/SIL), onde a jornada passa a depender do que ele digitar."""
    steps = []
    atual = estado_atual
    for _ in range(limite):
        dados = spec_model["estados"].get(atual)
        if not dados or atual.lower() == "_end_":
            break
        transicoes = dados.get("transicoes", [])
        if any(_eh_transicao_rej_sil(t["condicao"]) or _INTERATIVO_RE.search(t["condicao"]) for t in transicoes):
            break
        candidatos = []
        for t in transicoes:
            destino = resolver_destino(spec_model["mapa_rotas"], t["destino"])
            if destino and destino != atual and destino not in visitados:
                candidatos.append((t, destino))
        if not candidatos:
            break
        t, destino = next((c for c in candidatos if _ELSE_RE.search(c[0]["condicao"])), candidatos[0])
        sp_t = _sp_efetivo_transicao(spec_model, atual, t)
        prompt, _dono = next(_candidatos_prompt_transicao(spec_model, atual, t), (None, None))
        prompt_id = prompt["id"] if prompt else "—"
        prompt_texto = prompt["texto"] if prompt else "—"
        if sp_t:
            resultado = f"{sp_t[0]}={sp_t[1]}" + (f" — {prompt_texto}" if prompt_texto != "—" else "")
        else:
            resultado = prompt_texto
        steps.append(
            {
                "step_num": 0,
                "acao": f"Seguir a jornada ({t['condicao']})",
                "estado": destino,
                "prompt_id": prompt_id,
                "prompt_texto": prompt_texto,
                "sp": sp_t,
                "resultado": resultado,
            }
        )
        visitados.add(destino)
        atual = destino
    return steps


def _step_retentativa(spec_model, estado_nome, t, sp_t):
    """Step de uma tentativa de REJ/SIL: mostra o prompt de retentativa
    (REJ1, REJ2, SIL1, SIL2, ... ou o prompt de saida da ultima tentativa),
    com seu texto e SP, e pra onde a chamada segue."""
    prompt, dono = next(_candidatos_prompt_transicao(spec_model, estado_nome, t), (None, None))
    prompt_id = prompt["id"] if prompt else "—"
    prompt_texto = prompt["texto"] if prompt else "—"
    path = t.get("path") or [t["condicao"]]
    folha = path[-1]
    acao = f"{_rotulo_tipo_retentativa(t['condicao'])} — {folha}"

    destino_real = resolver_destino(spec_model["mapa_rotas"], t.get("destino"))
    destino_txt = f"segue para {destino_real}" if destino_real and destino_real != estado_nome else "permanece no estado"
    if sp_t:
        resultado = f"{sp_t[0]}={sp_t[1]}" + (f" — {prompt_texto}" if prompt_texto != "—" else "")
    else:
        resultado = prompt_texto
    return {
        "step_num": 0,
        "acao": acao,
        "estado": dono or estado_nome,
        "prompt_id": prompt_id,
        "prompt_texto": prompt_texto,
        "sp": sp_t,
        "resultado": f"{resultado} | {destino_txt}",
    }


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
    for j, estado_nome in enumerate(caminho):
        prox_prompt_target = ""
        condicao = ""
        sp_hop = None
        if j == 0:
            condicao = ""
        else:
            anterior = caminho[j - 1]
            transicoes = spec_model["estados"].get(anterior, {}).get("transicoes", [])
            match_t = next(
                (t for t in transicoes if resolver_destino(spec_model["mapa_rotas"], t["destino"]) == estado_nome),
                None,
            )
            # O ultimo hop de um CT por transicao deve usar ESSA transicao
            # (nao a primeira que por acaso aponte pro mesmo destino).
            if transicao_final is not None and j == len(caminho) - 1:
                match_t = transicao_final
            if match_t:
                condicao = match_t["condicao"]
                prox_prompt_target = match_t.get("prox_prompt", "")
                sp_hop = match_t.get("sp")

        state_data = spec_model["estados"].get(estado_nome, {})
        prompt = _match_prompt(state_data, prox_prompt_target)
        prompt_id = prompt["id"] if prompt else "—"
        prompt_texto = prompt["texto"] if prompt else "—"

        if sp_hop:
            resultado_hop = f"{sp_hop[0]}={sp_hop[1]}" + (f" — {prompt_texto}" if prompt_texto != "—" else "")
        else:
            resultado_hop = prompt_texto

        steps.append(
            {
                "step_num": j + 1,
                "acao": _acao_para_step(j, condicao, perfil),
                "estado": estado_nome,
                "prompt_id": prompt_id,
                "prompt_texto": prompt_texto,
                "sp": sp_hop,
                "resultado": resultado_hop,
            }
        )
    return steps


def _resultado_final_texto(sp_final, destino_final):
    if sp_final:
        tipo, codigo = sp_final
        return f"{tipo}={codigo}"
    return None


def _formatar_resultado_esperado(steps, sp_final, sp_pendente):
    linhas = ["LOG", "CDR", "ScriptPoint"]
    marcados = [s["sp"] for s in steps if s.get("sp")]
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
    def __init__(self, spec_model, eep_model, tipo_a=True, progress_callback=None):
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
        self._transicoes_ignoradas_sp_antigo = 0
        self._transicoes_ignoradas_sem_sp = 0

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

    def _add_ct(self, bloco_num, bloco_nome, estado, alteracao, perfil, caminho, sp_final=None, regressivo=False, sp_pendente=False, gherkin_override=None, restricoes=None, sps_todos=None, steps_extra=None, transicao_final=None):
        if not caminho:
            self.revisao_necessaria.append(
                {
                    "tipo": "sem_caminho",
                    "estado": estado,
                    "detalhe": f"Não foi possível calcular um caminho de entrada ate o estado '{estado}' a partir do início do fluxo.",
                }
            )
            return None

        steps = montar_steps(self.spec_model, caminho, perfil, transicao_final=transicao_final)
        # Steps adicionais (ex.: tentativas REJ1/REJ2/... ou SIL1/SIL2/... da
        # mesma escada, num unico CT) entram depois do caminho ate o estado.
        for extra in steps_extra or []:
            novo = dict(extra)
            novo["step_num"] = len(steps) + 1
            steps.append(novo)
        sps_todos = [sp for sp in (sps_todos or []) if sp]
        if sps_todos and not sp_final:
            sp_final = sps_todos[0]
        sp_pendente = sp_pendente or (sp_final is None and self.tipo_a)

        resultado_txt = _formatar_resultado_esperado(steps, sp_final, sp_pendente)
        steps.append(
            {
                "step_num": len(steps) + 1,
                "acao": "Encerrar a chamada",
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
            prefixo = f"Dado cliente {perfil_txt} na jornada de homologação, Quando percorrer o caminho de entrada até o estado {estado} ("
            sufixo = f"), Então URA deve {resultado_gherkin}."
            gherkin = montar_gherkin(prefixo, alteracao or "garantia de fluxo", sufixo)

        sufixo = "b" if sp_pendente and self.tipo_a else ""
        ct_id = self._novo_id(sufixo)
        self._registrar_sp(sp_final, ct_id)
        for sp_extra in sps_todos:
            if sp_extra != sp_final:
                self._registrar_sp(sp_extra, ct_id)

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
        pre_req_partes.append(f"Alteração: {alteracao}" if alteracao else "Garantia de fluxo principal")
        pre_requisito = " | ".join(pre_req_partes)

        caso = {
            "id": ct_id.replace("CT-", ""),
            "ct_id": ct_id,
            "bloco": bloco_num,
            "bloco_nome": bloco_nome,
            "regressivo": regressivo,
            "estado": estado,
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
        }
        self.casos_teste.append(caso)
        return caso

    # ---------- L1-L4, L6-L8: CTs principais por estado alterado ----------

    def gerar_cts_tipo_a(self):
        estados_alterados = list(self.spec_model["versionamento"]["estados_alterados"])

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
                        {"numero": bloco_idx, "nome": bloco_nome, "cor": cor, "titulo": f"{bloco_nome} — {nome_real}"}
                    )
                    self.revisao_necessaria.append(
                        {
                            "tipo": "estado_nao_encontrado",
                            "estado": est["nome"],
                            "detalhe": f"Estado '{est['nome']}' citado no Versionamento não foi encontrado como aba na SPEC.",
                        }
                    )
                    continue

            self._blocos.append({"numero": bloco_idx, "nome": bloco_nome, "cor": cor, "titulo": f"{bloco_nome} — {nome_real}"})

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
            if not transicoes or (not self._sps_novos and len(transicoes) > LIMITE_TRANSICOES_SEM_SP):
                caminho, perfil_efetivo = bfs_caminho_entrada(self.spec_model, nome_real, perfil_entrada=perfil_base)
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
            def _avaliar(t):
                """(sp_efetivo, status) — status: 'ok' | 'antigo' | 'sem_sp'."""
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
                    return sp_t, "ok"
                if sp_t and sp_t[1] not in self._sps_novos:
                    # SP ja existia antes desta versao (nao esta na lista de
                    # novos da VersionamentoBI) — fora do escopo do teste.
                    return sp_t, "antigo"
                if not sp_t:
                    # Sem NENHUMA marcacao de SP, com a BI ja preenchida:
                    # nenhum sinal de que faz parte desta versao — pode ser
                    # so um ramo antigo do menu. Sem esse filtro, um estado
                    # grande com dezenas de ramos legados gera uma "SP
                    # PENDENTE" pra CADA UM (violando L3/L4).
                    return sp_t, "sem_sp"
                return sp_t, "ok"

            def _contar_ignorada(status):
                nonlocal sp_antigo_local, sem_sp_local
                if status == "antigo":
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
                    if status != "ok":
                        _contar_ignorada(status)
                        continue

                    assinatura = normalizar_chave(t["condicao"])
                    if assinatura in vistos_condicao:
                        continue
                    vistos_condicao.add(assinatura)

                    restr = extrair_restricoes_sessao(t["condicao"])
                    perfil = restr.get("ani", perfil_base)
                    caminho, perfil_efetivo = bfs_caminho_entrada(
                        self.spec_model, nome_real, perfil_entrada=perfil, restricoes_extra=restr
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
                    steps_jornada = []
                    if _eh_transicao_rej_sil(t["condicao"]) and destino_hop and destino_hop != nome_real:
                        steps_jornada = _steps_jornada(self.spec_model, destino_hop, set(caminho_completo))
                    self._add_ct(
                        bloco_idx, bloco_nome, nome_real, alteracao_txt, perfil, caminho_completo,
                        sp_final=sp_t, restricoes=restr, steps_extra=steps_jornada,
                        transicao_final=t if len(caminho_completo) > len(caminho) else None,
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
                caminho, perfil_efetivo = bfs_caminho_entrada(
                    self.spec_model, nome_real, perfil_entrada=perfil, restricoes_extra=restr
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

            if len(self.casos_teste) == cts_antes and transicoes:
                partes = []
                if sp_antigo_local:
                    partes.append(f"{sp_antigo_local} transição(ões) com SP antigo (fora da VersionamentoBI)")
                if sem_sp_local:
                    partes.append(f"{sem_sp_local} transição(ões) sem nenhuma marcação de SP")
                if sem_caminho_local:
                    partes.append(f"{sem_caminho_local} transição(ões) sem caminho de entrada encontrado (BFS)")
                motivo = (
                    ", ".join(partes) + "."
                    if partes
                    else "nenhuma transição gerou um CT válido (verifique a estrutura da aba manualmente)."
                )
                self.revisao_necessaria.append(
                    {
                        "tipo": "estado_sem_sp_novo",
                        "estado": nome_real,
                        "detalhe": f"Estado '{nome_real}' está no Versionamento, mas não gerou nenhum CT: {motivo} "
                        "Confira manualmente se o código IVR/cor detectados "
                        "estão corretos.",
                    }
                )

    # ---------- L12/L13: cobertura por produto (Tipo B, regra de transferencia pura) ----------

    def gerar_cts_tipo_b(self):
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
            caminho, perfil_efetivo = bfs_caminho_entrada(self.spec_model, estado_alvo, perfil_entrada="aninao")
            self._add_ct(
                bloco_idx,
                bloco_nome,
                estado_alvo,
                f"Regra de transferência especializada via chave {chave}",
                perfil_efetivo,
                caminho,
            )

    # ---------- L9: fraseologia obrigatoria p/ prompts na cor do projeto ----------

    def gerar_cts_fraseologia(self, itens_cor):
        if not itens_cor:
            return
        cobertos = {p["prompt_id"] for c in self.casos_teste for p in c["steps"] if p.get("prompt_id") not in (None, "—")}
        bloco_idx = len(self._blocos) + 1
        criado_bloco = False

        for aba, itens in itens_cor.items():
            estado = resolver_destino(self.spec_model["mapa_rotas"], aba) or aba
            state_data = self.spec_model["estados"].get(estado)
            if not state_data:
                continue
            for _row, _col, valor, _cont in itens:
                prompt = next((p for p in state_data["prompts"] if normalizar_chave(valor) == normalizar_chave(p["id"])), None)
                if not prompt or prompt["id"] in cobertos:
                    continue
                if not criado_bloco:
                    bloco_nome = f"Bloco {bloco_idx}"
                    self._blocos.append(
                        {"numero": bloco_idx, "nome": bloco_nome, "cor": self._cor_bloco(bloco_idx), "titulo": f"{bloco_nome} — Fraseologia"}
                    )
                    criado_bloco = True
                caminho, perfil_efetivo = bfs_caminho_entrada(self.spec_model, estado, perfil_entrada="aninao")
                perfil_txt = "ANINÃO" if perfil_efetivo == "aninao" else "ANISIM"
                gherkin = abreviar_gherkin(
                    f"Dado cliente {perfil_txt} chega ao estado {estado}, Quando o prompt {prompt['id']} for reproduzido, "
                    f"Então a locução deve corresponder fielmente ao texto marcado na SPEC."
                )
                self._add_ct(
                    bloco_idx,
                    f"Bloco {bloco_idx}",
                    estado,
                    f"Fraseologia obrigatória (L9) — prompt {prompt['id']} marcado na versão vigente",
                    perfil_efetivo,
                    caminho,
                    gherkin_override=gherkin,
                )
                cobertos.add(prompt["id"])

    # ---------- L3/L5/L11: bloco REGRESSIVO ----------

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
            caminho, perfil_efetivo = bfs_caminho_entrada(self.spec_model, estado_api, perfil_entrada="anisim")
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
                "legenda": [],
                "blocos": [],
            }
        self._progresso(82, "Verificando fraseologia obrigatória (L9)...")
        self.gerar_cts_fraseologia(itens_cor or {})
        self._progresso(90, "Montando o bloco regressivo...")
        self.gerar_bloco_regressivo()
        self._progresso(96, "Organizando blocos, legenda e BI...")
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
        return {
            "casos_teste": self.casos_teste,
            "revisao_necessaria": self.revisao_necessaria,
            "bi_marcacoes": self.bi_marcacoes(),
            "legenda": self.legenda_blocos(),
            "blocos": self._blocos,
        }


def gerar_plano_ct(spec_model, eep_model, tipo_a=True, itens_cor=None, progress_callback=None):
    gerador = GeradorCT(spec_model, eep_model, tipo_a=tipo_a, progress_callback=progress_callback)
    return gerador.gerar(itens_cor=itens_cor)
