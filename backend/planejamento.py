"""
Planejamento de homologacao (aba "Planejamento"): monta, de forma deterministica,
um plano de testes no estilo de um QA senior a partir do que a ferramenta ja sabe:
secoes do EEP (objetivo, regras, premissas, restricoes...), versionamento da SPEC,
CTs gerados, marcacoes de BI e itens de revisao.

Cada bloco carrega a FONTE ("EEP" quando o texto vem do documento de escopo,
"SPEC/CTs" quando e calculado pela ferramenta), para ficar claro o que e dado do
projeto e o que e inferencia. Quando o EEP e pobre de informacao, o que faltou
vai para "lacunas" em vez de ser inventado.
"""
import re
from collections import Counter

_PERFIL_ROTULO = {
    "ANINÃO": "ANI Não (cliente não identificado pelo número de origem)",
    "ANISIM": "ANI Sim (cliente identificado pelo número de origem)",
}


def _numero(detalhe, padrao):
    m = re.search(padrao, detalhe or "")
    return int(m.group(1)) if m else 0


def _unico(lista):
    vistos, saida = set(), []
    for x in lista:
        x = (x or "").strip()
        if x and x.lower() not in vistos:
            vistos.add(x.lower())
            saida.append(x)
    return saida


def _truncar(texto, n=420):
    texto = (texto or "").strip()
    return texto if len(texto) <= n else texto[: n - 1].rstrip() + "…"


def montar_planejamento(plano, eep_model, spec_model, ivr_code=None, tipo_a=True):
    eep = eep_model or {}
    secoes = eep.get("secoes") or {}
    campos = eep.get("campos") or {}
    casos = plano.get("casos_teste") or []
    revisao = plano.get("revisao_necessaria") or []
    bi = plano.get("bi_marcacoes") or []
    legenda = plano.get("legenda") or []
    versionamento = (spec_model or {}).get("versionamento") or {}
    estados_alterados = versionamento.get("estados_alterados") or []
    ivr = ivr_code or (spec_model or {}).get("ivr_resolvido") or versionamento.get("ivr") or "—"
    lacunas = []

    # ── números de apoio ────────────────────────────────────────────
    total = len(casos)
    regressivos = [c for c in casos if c.get("regressivo")]
    funcionais = total - len(regressivos)
    sp_pendentes = [c["ct_id"] for c in casos if c.get("sp_pendente")]
    bi_sem_ct = [sp for sp in bi if sp.get("ct") == "—"]
    bi_cobertos = len(bi) - len(bi_sem_ct)
    perfis = Counter(c.get("perfil") or "—" for c in casos)
    estados_com_ct = _unico(c.get("estado") for c in casos)
    # palavras todas em maiuscula (ex.: COMPLEMENTARES) sao ruido da mineracao, nao chaves de ativacao
    chaves = [c for c in (eep.get("chaves") or []) if c and not c.isupper()]
    vdns = eep.get("vdns") or []
    ignorados_sp_antigo = sum(_numero(r.get("detalhe"), r"(\d+) transi") for r in revisao if r.get("tipo") == "info_sp_ja_existentes_ignorados")
    ignorados_sem_sp = sum(_numero(r.get("detalhe"), r"(\d+) transi") for r in revisao if r.get("tipo") == "info_transicoes_sem_sp_ignoradas")
    estados_nao_achados = [r.get("estado") for r in revisao if r.get("tipo") == "estado_nao_encontrado" and r.get("estado")]
    estados_sem_ct = [r.get("estado") for r in revisao if r.get("tipo") == "estado_sem_sp_novo" and r.get("estado")]

    # ── identificação ───────────────────────────────────────────────
    nome = eep.get("nome")
    nome = nome if nome and "sem nome" not in nome.lower() else None
    nome_eep = bool(nome)
    if not nome:  # titulo do bloco do projeto na SPEC: "IVR-246110 - [CLARO ...] Fluxo ..."
        m_titulo = re.search(r"IVR\W*\d{5,7}\s*[-–:]*\s*(.+)", str(versionamento.get("ivr") or ""), re.IGNORECASE)
        nome = m_titulo.group(1).strip() if m_titulo and m_titulo.group(1).strip() else None
    jira_eep = eep.get("jira") if eep.get("jira") and "não identificado" not in (eep.get("jira") or "").lower() else None
    identificacao = [
        ("Projeto", (nome + ("" if nome_eep else " (título na SPEC)")) if nome else "Não identificado"),
        ("IVR (SPEC)", ivr),
    ]
    if jira_eep:
        identificacao.append(("Código EEP (JIRA)", jira_eep))
    if campos.get("produto_canal"):
        identificacao.append(("Produto / Canal", campos["produto_canal"]))
    if campos.get("responsavel_cliente"):
        identificacao.append(("Responsável Cliente", campos["responsavel_cliente"]))
    if campos.get("responsavel_mutant"):
        identificacao.append(("Responsável Mutant", campos["responsavel_mutant"]))
    identificacao.append(("Tipo de projeto", "Alteração de SPEC" if tipo_a else "Transferência pura"))
    identificacao.append(("Abrangência dos testes", f"{total} CT(s) em {len(legenda) or 1} bloco(s)"))

    # ── objetivo / contexto / regras (EEP, com plano B pela SPEC) ─────
    objetivo, fonte_obj = [], "EEP"
    for k in ("solucao", "resultados", "objetivo"):
        if secoes.get(k):
            objetivo += secoes[k]
    objetivo = [o for o in objetivo if not o.rstrip().endswith(":")]
    if not objetivo and secoes.get("validacao"):
        objetivo = secoes["validacao"]
    if not objetivo:
        fonte_obj = "SPEC"
        lacunas.append("Objetivo do projeto: o EEP não traz uma seção de objetivo/solução reconhecível — o texto abaixo foi inferido do versionamento da SPEC.")
        if estados_alterados:
            objetivo = [
                f"Validar as alterações da versão {ivr} em {len(estados_alterados)} estado(s) da URA: "
                + ", ".join(e["nome"] for e in estados_alterados[:8])
                + ("…" if len(estados_alterados) > 8 else "")
                + "."
            ]
        else:
            objetivo = [f"Validar o fluxo da URA do projeto {ivr}."]

    contexto = []
    for k in ("necessidade", "problemas", "perfil", "onde", "impactados", "as_is"):
        for p in secoes.get(k, []):
            rotulo = {"problemas": "Problema observado: ", "onde": "Onde ocorre: ", "impactados": "Impactado: ",
                      "perfil": "Perfil/canais: ", "as_is": "Hoje (AS IS): "}.get(k, "")
            contexto.append(rotulo + p)
    contexto = [c for c in contexto if not c.rstrip().endswith(":")]
    if not contexto:
        lacunas.append("Contexto/necessidade: não encontrei a descrição do problema no EEP.")

    regras = list(secoes.get("regras") or [])
    fonte_regras = "EEP"
    if not regras and secoes.get("solucao_detalhe"):
        regras = list(secoes["solucao_detalhe"])
    if not regras:
        fonte_regras = "SPEC"
        lacunas.append("Regras de negócio: o EEP não traz regras — listei as alterações descritas no versionamento da SPEC.")
        regras = [f"{e['nome']}: {e['alteracao']}" for e in estados_alterados if e.get("alteracao")]

    # ── escopo ──────────────────────────────────────────────────────
    dentro = [{"estado": e["nome"], "alteracao": e.get("alteracao") or "—"} for e in estados_alterados]
    fora = []
    if ignorados_sp_antigo:
        fora.append(f"{ignorados_sp_antigo} transição(ões) com ScriptPoint já existente (versões anteriores): fora do escopo novo; cobertas só pela regressão.")
    if ignorados_sem_sp:
        fora.append(f"{ignorados_sem_sp} transição(ões) sem marcação de ScriptPoint: tratadas como ramos legados, sem CT próprio.")
    for e in estados_nao_achados:
        fora.append(f"Estado '{e}' citado no versionamento mas sem aba correspondente na SPEC: não foi modelado.")
    for e in estados_sem_ct:
        fora.append(f"Estado '{e}' consta no versionamento mas não gerou CT (sem SP novo): confirmar manualmente.")
    for r in secoes.get("restricoes", []):
        if not re.match(r"^\d+\.\d+", r):
            fora.append("Restrição do EEP: " + _truncar(r, 300))

    # ── estratégia ──────────────────────────────────────────────────
    estrategia = [
        "Teste funcional caixa-preta por ligação em HML: cada CT percorre o caminho da SPEC até o estado alterado e valida o ScriptPoint e o prompt esperados.",
        f"Cobertura baseada em risco: {funcionais} CT(s) funcionais cobrem as transições novas da versão (marcadas na SPEC/Versionamento BI)"
        + (f", mais {len(regressivos)} CT(s) regressivos que protegem fluxos já existentes." if regressivos else "."),
        "Cada CT segue a jornada até o desfecho (transferência, encerramento ou mudança de estado) — não para no estado alterado.",
        "Tentativas de erro (REJ/SIL/INV/INC) são agrupadas em um único CT por escada, com o prompt de cada tentativa.",
        "Evidência por CT: LOG da URA, CDR e ScriptPoint registrado; anexadas na aba Execução dos Testes e exportadas em PDF.",
    ]
    if perfis:
        estrategia.append(
            "Perfis de entrada exercitados: "
            + "; ".join(f"{_PERFIL_ROTULO.get(p, p)}: {n} CT(s)" for p, n in perfis.most_common())
            + "."
        )

    cobertura = {
        "total": total,
        "funcionais": funcionais,
        "regressivos": len(regressivos),
        "estados": estados_com_ct,
        "sps_marcados": len(bi),
        "sps_cobertos": bi_cobertos,
        "sps_sem_ct": [sp["codigo"] for sp in bi_sem_ct],
        "sp_pendentes": sp_pendentes,
        "blocos": [{"bloco": b.get("bloco"), "titulo": b.get("titulo"), "cts": b.get("cts"), "sps": b.get("sps")} for b in legenda],
    }

    # ── massa de testes e dados ─────────────────────────────────────
    massa = []
    for p in secoes.get("massa", []):
        massa.append("EEP: " + _truncar(p, 360))
    if perfis:
        massa.append("Perfis necessários: " + ", ".join(f"{_PERFIL_ROTULO.get(p, p).split(' (')[0]}" for p in perfis) + ".")
    if chaves:
        massa.append("Chaves/parâmetros que condicionam o fluxo: " + ", ".join(chaves[:12]) + (" …" if len(chaves) > 12 else "") + ".")
    else:
        lacunas.append("Chaves sistêmicas: nenhuma chave identificada no EEP — confirmar com o time quais chaves/flags precisam estar ativas.")
    if vdns:
        massa.append(f"{len(vdns)} VDN(s) de transferência citados no EEP (ver aba Legenda).")
    if not secoes.get("massa"):
        massa.append("O EEP não detalha a massa: solicitar à Claro contratos/linhas para cada perfil acima (pedir também cenários complementares, se necessário).")

    # ── premissas / restrições ──────────────────────────────────────
    premissas = [p for p in secoes.get("premissas", [])]
    restricoes = [r for r in secoes.get("restricoes", []) if not re.match(r"^\d+\.\d+", r)]
    impactos = list(secoes.get("impactos") or [])
    prazos = []
    for texto in restricoes + impactos:
        for d in re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto):
            prazos.append(d)
    prazos = _unico(prazos)

    # ── riscos (calculados + EEP) ───────────────────────────────────
    riscos = []
    if bi_sem_ct:
        riscos.append(("alto", f"{len(bi_sem_ct)} ScriptPoint(s) marcado(s) no BI sem CT de cobertura: {', '.join(sp['codigo'] for sp in bi_sem_ct[:8])}"
                       + (" …" if len(bi_sem_ct) > 8 else "") + ". Podem ficar sem validação."))
    if sp_pendentes:
        riscos.append(("medio", f"{len(sp_pendentes)} CT(s) com SP pendente ({', '.join(sp_pendentes[:6])}"
                       + (" …" if len(sp_pendentes) > 6 else "") + "): o ScriptPoint só poderá ser conferido após a publicação do BI."))
    if estados_nao_achados or estados_sem_ct:
        riscos.append(("medio", "Estados do versionamento sem CT: "
                       + ", ".join(_unico(estados_nao_achados + estados_sem_ct)[:6]) + ". Verificar se há alteração real a testar."))
    if not chaves:
        riscos.append(("baixo", "Nenhuma chave sistêmica foi identificada no EEP: risco de testar com flag/DDD desativado."))
    if str((spec_model or {}).get("ivr_origem") or "").startswith(("nome", "codigo")):
        riscos.append(("medio", f"O código do IVR não foi informado: usei {ivr} (identificado pelo {spec_model.get('ivr_origem')}). Confirmar o projeto."))
    for r in impactos:
        riscos.append(("alto", "EEP — " + _truncar(r, 360)))
    if prazos:
        riscos.append(("alto", "Prazo/data limite citado no EEP: " + ", ".join(prazos) + ". Planejar a execução e a evidência com folga."))
    if not riscos:
        riscos.append(("baixo", "Nenhum risco crítico identificado automaticamente. Reavaliar após a primeira rodada de execução."))

    # ── critérios ───────────────────────────────────────────────────
    entrada = [
        "Ambiente de HML disponível e estável (barramento/webservices acessíveis).",
        f"SPEC do projeto {ivr} publicada em HML na versão testada, com as marcações de BI ({len(bi)} ScriptPoint(s)) publicadas.",
        "Massa de testes liberada para todos os perfis do plano (ver Massa de testes).",
    ]
    if chaves:
        entrada.append("Chaves/parâmetros ativos no ambiente: " + ", ".join(chaves[:8]) + (" …" if len(chaves) > 8 else "") + ".")
    entrada += [f"EEP: {_truncar(p, 200)}" for p in premissas[:3]]
    saida = [
        f"100% dos {total} CT(s) executados, com status OK ou bug justificado e aceito.",
        f"Todos os {len(bi)} ScriptPoint(s) marcados conferidos no log/CDR" + (f" (hoje {bi_cobertos} cobertos por CT)." if bi else "."),
        "Evidências (LOG, CDR, ScriptPoint) anexadas em cada CT e PDF de execução exportado.",
        "Nenhum bug crítico/bloqueante em aberto; regressivos sem falhas.",
    ]
    for p in (secoes.get("sucesso") or [])[:2]:
        saida.append("EEP — parâmetro de sucesso: " + _truncar(p, 260))
    falha = [
        "ScriptPoint esperado não registrado, ou registrado em estado/ordem diferente da SPEC.",
        "Prompt reproduzido diferente do especificado (texto/ID).",
        "Transferência para VDN/fila incorreto, ou jornada encerrada antes do desfecho esperado.",
        "Regressão: fluxo já existente com comportamento alterado.",
    ]
    if chaves:
        falha.append("Comportamento não responde à chave de ativação/desativação (" + chaves[0] + (", …" if len(chaves) > 1 else "") + ").")

    # ── resumo executivo ────────────────────────────────────────────
    rotulo_proj = f"{nome} ({ivr})" if nome else ivr
    partes = [f"O projeto {rotulo_proj} altera {len(estados_alterados)} estado(s) da URA." if estados_alterados
              else f"O projeto {rotulo_proj} foi modelado a partir da SPEC."]
    partes.append(f"Foram modelados {total} CT(s) ({funcionais} funcionais e {len(regressivos)} regressivos)"
                  + (f", cobrindo {bi_cobertos} de {len(bi)} ScriptPoint(s) marcados no BI." if bi else "."))
    if lacunas:
        partes.append(f"Atenção: {len(lacunas)} informação(ões) não constam no EEP e foram complementadas pela SPEC ou ficam como pendência (ver “Lacunas”).")

    return {
        "resumo": " ".join(partes),
        "identificacao": [{"rotulo": a, "valor": b} for a, b in identificacao],
        "objetivo": {"fonte": fonte_obj, "itens": [_truncar(p, 700) for p in objetivo[:8]]},
        "contexto": {"fonte": "EEP", "itens": [_truncar(p, 600) for p in contexto[:10]]},
        "regras": {"fonte": fonte_regras, "itens": [_truncar(p, 600) for p in regras[:25]]},
        "escopo": {"dentro": dentro, "fora": fora},
        "estrategia": estrategia,
        "cobertura": cobertura,
        "massa": massa,
        "premissas": [_truncar(p, 400) for p in premissas[:12]],
        "restricoes": [_truncar(p, 500) for p in restricoes[:8]],
        "riscos": [{"nivel": n, "texto": t} for n, t in riscos],
        "criterios": {"entrada": entrada, "saida": saida, "falha": falha},
        "lacunas": lacunas,
    }
