"""
Modelagem ENCADEADA: um projeto que comeca numa SPEC (ex.: URA Identificadora) e continua em outra (ex.: URA CRN /
Rogue). As SPECs lidas viram UM modelo so, e as transicoes que "migram" para a outra SPEC viram saltos reais:

 - na SPEC de origem a coluna "Observacoes" da transicao diz "MIGRACAO SPEC CRN" (ou MOVEL - TOPO, TLV, SEGMENTOS...);
   o estado de destino passa a ser o estado de MESMO NOME da SPEC citada (se ela foi anexada);
 - destinos que nao existem na SPEC de origem mas existem em exatamente uma das outras tambem viram saltos;
 - saidas para uma SPEC que NAO foi anexada terminam num estado sintetico "Destino (SPEC X)" — a jornada acaba ali.

Estados de mesmo nome em SPECs diferentes (ex.: PedeID) ganham o sufixo "(ROTULO)" na SPEC seguinte, para nao se misturarem.
"""
import re

from spec_reader import normalizar_chave, resolver_destino

_OBS_MIGRACAO_RE = re.compile(r"migra[cç][aã]o\s+(?:de\s+|da\s+|para\s+)?spec\s+([^\n|]+)", re.IGNORECASE)

# (rotulo, padrao no texto normalizado sem acentos)
_ROTULOS = (
    ("CRN", r"crn"),
    ("TLV", r"tlv|televendas"),
    ("MÓVEL", r"movel|mobile"),
    ("SEGMENTOS", r"segmento"),
    ("EMPRESAS", r"empresas"),
    ("URAID", r"uraid|identificadora|uraidentif"),
)
_PRIORIDADE_ENTRADA = ("URAID",)


def _sem_acento(txt):
    return normalizar_chave(txt).replace("_", "")


def rotulo_canonico(texto):
    """Rotulo da SPEC (CRN, URAID, TLV, MÓVEL, SEGMENTOS...) citado num nome de arquivo ou numa observacao."""
    n = _sem_acento(texto)
    for rotulo, padrao in _ROTULOS:
        if re.search(padrao, n):
            return rotulo
    return None


def rotulo_do_arquivo(nome_arquivo):
    stem = re.sub(r"\.[a-z0-9]+$", "", str(nome_arquivo or ""), flags=re.IGNORECASE)
    return rotulo_canonico(stem) or (re.sub(r"[^A-Za-z0-9]+", " ", stem).strip().upper()[:14] or "SPEC")


def ordenar_specs(specs):
    """specs: [(bytes, nome)]. A SPEC de entrada (URAID) vem primeiro; as demais mantem a ordem recebida."""
    def chave(item):
        rot = rotulo_canonico(re.sub(r"\.[a-z0-9]+$", "", str(item[1] or ""), flags=re.IGNORECASE))
        return 0 if rot in _PRIORIDADE_ENTRADA else 1

    return sorted(specs, key=chave)  # sorted e estavel


def rotulos_unicos(nomes):
    rotulos, vistos = [], {}
    for nome in nomes:
        r = rotulo_do_arquivo(nome)
        vistos[r] = vistos.get(r, 0) + 1
        rotulos.append(r if vistos[r] == 1 else f"{r} {vistos[r]}")
    return rotulos


def combinar_specs(itens):
    """
    itens: [{"modelo": modelo de spec_reader.read_spec, "rotulo": "URAID", "arquivo": "x.xlsx", "itens_cor": {...}}].
    O primeiro e a SPEC de ENTRADA do fluxo. Devolve (modelo_combinado, itens_cor_combinado).
    """
    usados = set()
    renomes = []
    for it in itens:
        m, ren = it["modelo"], {}
        for nome in m["lista_abas"]:
            novo = nome
            n = 2
            while normalizar_chave(novo) in usados:
                novo = f"{nome} ({it['rotulo']})" if n == 2 else f"{nome} ({it['rotulo']} {n})"
                n += 1
            usados.add(normalizar_chave(novo))
            ren[nome] = novo
        renomes.append(ren)

    combinado = {
        "lista_abas": [],
        "estados": {},
        "mapa_rotas": {},
    }
    for it, ren in zip(itens, renomes):
        m = it["modelo"]
        for nome in m["lista_abas"]:
            combinado["lista_abas"].append(ren[nome])
            dados = m["estados"][nome]
            dados["nome"] = ren[nome]
            dados["spec"] = it["rotulo"]
            dados["nome_original"] = nome
            combinado["estados"][ren[nome]] = dados
        for chave, real in m["mapa_rotas"].items():
            novo = ren.get(real, real)
            if chave not in combinado["mapa_rotas"]:
                combinado["mapa_rotas"][chave] = novo
        for novo in ren.values():
            combinado["mapa_rotas"].setdefault(normalizar_chave(novo), novo)

    # destinos de cada SPEC passam a apontar para os nomes do modelo combinado
    for it, ren in zip(itens, renomes):
        m = it["modelo"]
        for nome in m["lista_abas"]:
            for t in combinado["estados"][ren[nome]].get("transicoes", []):
                real = resolver_destino(m["mapa_rotas"], t.get("destino"))
                if real in ren:
                    t["destino_original"] = t.get("destino")
                    t["destino"] = ren[real]

    # saltos entre SPECs
    por_rotulo = {it["rotulo"]: k for k, it in enumerate(itens)}
    externos = {}   # (rotulo citado, destino) -> nome do estado sintetico
    saltos = {}     # (origem, destino) -> quantidade
    for k, it in enumerate(itens):
        m, ren = it["modelo"], renomes[k]
        for nome in m["lista_abas"]:
            for t in combinado["estados"][ren[nome]].get("transicoes", []):
                bruto = t.get("destino_original") or t.get("destino")
                if not bruto:
                    continue
                achou = _OBS_MIGRACAO_RE.search(t.get("obs") or "")
                rotulo_obs = rotulo_canonico(achou.group(1)) if achou else None
                alvo = None
                if rotulo_obs and rotulo_obs != it["rotulo"]:
                    j = por_rotulo.get(rotulo_obs)
                    if j is not None:
                        real_j = resolver_destino(itens[j]["modelo"]["mapa_rotas"], bruto)
                        if real_j:
                            alvo = (j, renomes[j][real_j])
                        # estado inexistente na SPEC citada: a observacao e so informativa, segue local
                    else:
                        chave = (rotulo_obs, bruto)
                        if chave not in externos:
                            sintetico = f"{bruto} (SPEC {rotulo_obs})"
                            externos[chave] = sintetico
                            combinado["estados"][sintetico] = {
                                "nome": sintetico, "spec": rotulo_obs, "estados_anteriores": [], "obs": "",
                                "prompts": [], "transicoes": [], "concat_exemplos": [], "destinos_unicos": [],
                                "externo": True,
                            }
                            combinado["mapa_rotas"][normalizar_chave(sintetico)] = sintetico
                        t["destino"] = externos[chave]
                        t["handoff"] = rotulo_obs
                        t["handoff_txt"] = achou.group(0).strip()[:120]
                        t["handoff_externo"] = True
                        saltos[(it["rotulo"], f"{rotulo_obs} (não anexada)")] = saltos.get((it["rotulo"], f"{rotulo_obs} (não anexada)"), 0) + 1
                        continue
                elif resolver_destino(m["mapa_rotas"], bruto) is None and len(re.sub(r"[^a-z]", "", normalizar_chave(bruto))) >= 6 \
                        and not normalizar_chave(bruto).startswith("transfer"):
                    # nao existe nesta SPEC: se so UMA das outras tem o estado, e o salto para ela
                    candidatos = [
                        (j, renomes[j][resolver_destino(itens[j]["modelo"]["mapa_rotas"], bruto)])
                        for j in range(len(itens))
                        if j != k and resolver_destino(itens[j]["modelo"]["mapa_rotas"], bruto)
                    ]
                    if len(candidatos) == 1:
                        alvo = candidatos[0]
                if alvo is not None:
                    j, novo_nome = alvo
                    t["destino"] = novo_nome
                    t["handoff"] = itens[j]["rotulo"]
                    t["handoff_txt"] = (achou.group(0).strip()[:120] if achou else f"MIGRAÇÃO SPEC {itens[j]['rotulo']}")
                    saltos[(it["rotulo"], itens[j]["rotulo"])] = saltos.get((it["rotulo"], itens[j]["rotulo"]), 0) + 1

    # versionamento / BI: estados com o nome do modelo combinado e a SPEC de origem
    principal = itens[0]["modelo"]
    estados_alterados, bi, cores_estados = [], [], []
    for it, ren in zip(itens, renomes):
        m = it["modelo"]
        for e in m["versionamento"].get("estados_alterados", []):
            real = resolver_destino(m["mapa_rotas"], e["nome"])
            novo = dict(e)
            novo["nome"] = ren.get(real, e["nome"])
            novo["spec"] = it["rotulo"]
            estados_alterados.append(novo)
        for sp in m.get("versionamento_bi", []):
            real = resolver_destino(m["mapa_rotas"], sp.get("estado"))
            novo = dict(sp)
            if real in ren:
                novo["estado"] = ren[real]
            novo["spec"] = it["rotulo"]
            bi.append(novo)
        for c in m["versionamento"].get("cores_estados", []):
            if c not in cores_estados:
                cores_estados.append(c)
    versionamento = dict(principal["versionamento"])
    versionamento["estados_alterados"] = estados_alterados
    versionamento["cores_estados"] = cores_estados
    combinado["versionamento"] = versionamento
    combinado["versionamento_bi"] = bi
    for chave in ("ivr_resolvido", "ivr_origem", "diag_versionamento", "ivr_sugerido"):
        combinado[chave] = principal.get(chave)
    # o IVR pode estar so numa das SPECs
    if not combinado.get("ivr_resolvido"):
        combinado["ivr_resolvido"] = next((it["modelo"].get("ivr_resolvido") for it in itens if it["modelo"].get("ivr_resolvido")), None)
    combinado["_specs"] = [
        {
            "rotulo": it["rotulo"],
            "arquivo": it["arquivo"],
            "estados": len(it["modelo"]["lista_abas"]),
            "alterados": sum(1 for e in estados_alterados if e["spec"] == it["rotulo"]),
            "sps_novos": sum(1 for s in bi if s["spec"] == it["rotulo"]),
        }
        for it in itens
    ]
    combinado["_saltos_specs"] = [{"de": a, "para": b, "quantidade": q} for (a, b), q in sorted(saltos.items())]

    # cores por aba (itens_cor) acompanham os nomes novos
    cores = {}
    for it, ren in zip(itens, renomes):
        for aba, lista in (it.get("itens_cor") or {}).items():
            cores.setdefault(ren.get(aba, aba), []).extend(lista)
    return combinado, cores
