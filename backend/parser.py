"""
Orquestrador fino: liga spec_reader -> color_utils -> eep_reader -> ct_rules
-> xlsx_writer -> jira_fix -> validator, e adapta o resultado para o formato
que o frontend (index.html) e o app.py ja esperam.
"""
import io
import re
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import color_utils
import eep_reader
import jira_fix
import spec_reader
import specs_encadeadas
import validator
import xlsx_writer
from ct_rules import gerar_plano_ct
from planejamento import montar_planejamento


def _bytes_of(obj):
    if hasattr(obj, "read"):
        return obj.read()
    return obj


def _sem_callback(pct, etapa):
    pass


def _ct_start(spec_model):
    from ct_rules import _detectar_start_state

    return _detectar_start_state(spec_model)


_TERMOS_100 = {"mapear100", "mapear100%", "100", "100%", "completa", "specinteira", "specCompleta".lower(), "tudo", "todos", "all"}


def pede_spec_completa(ivr_code, tem_eep):
    """Campo IVR "Mapear 100%" (ou parecido), ou vazio SEM EEP => mapear a SPEC inteira."""
    texto = re.sub(r"[^a-z0-9%]", "", (ivr_code or "").lower())
    if not texto:
        return not tem_eep
    return texto in _TERMOS_100 or texto.startswith("mapear")


def gerar_modelagem_testes_completa(spec_bytes, eep_bytes, tipo_a=True, ivr_code=None,
                                     eep_filename="", spec_bytes_empresas=None, progress_callback=None,
                                     modo_completo=False, spec_filename="", specs_encadeadas_lista=None):
    avisar = progress_callback or _sem_callback
    spec_raw = _bytes_of(spec_bytes)
    eep_raw = _bytes_of(eep_bytes) if eep_bytes else b""

    sem_eep = not eep_raw
    modo_completo = modo_completo or (tipo_a and pede_spec_completa(ivr_code, not sem_eep))
    if not tipo_a and sem_eep:
        raise ValueError("Transferência pura precisa do EEP (tabela de cenários com os IDs/targets de transferência).")
    if modo_completo:
        ivr_code = None  # SPEC completa: nao ha projeto/IVR para localizar
        tipo_a = True
    if sem_eep:
        # Incidente/correcao: sem EEP, so a SPEC + codigo IVR para localizar o projeto.
        avisar(2, "Sem EEP: usando só a SPEC e o código IVR...")
        eep_model = {
            "nome": "Projeto sem nome identificado no EEP",
            "jira": "JIRA/IVR não identificado no EEP",
            "chaves": [],
            "vdns": [],
            "secoes": {},
            "campos": {},
        }
    else:
        avisar(2, "Lendo o EEP...")
        eep_model = eep_reader.minerar_eep(eep_raw, eep_filename)

    avisar(6, "Lendo a SPEC...")
    # SPECs encadeadas (ex.: URA Identificadora -> CRN): a de ENTRADA do fluxo vem primeiro.
    lista_specs = [(spec_raw, spec_filename or "SPEC")] + [(_bytes_of(b), n) for b, n in (specs_encadeadas_lista or [])]
    lista_specs = specs_encadeadas.ordenar_specs(lista_specs)
    encadeado = len(lista_specs) > 1
    spec_raw = lista_specs[0][0]
    spec_model = spec_reader.read_spec(
        io.BytesIO(spec_raw), ivr_code=ivr_code,
        eep_nome=eep_model.get("nome"), eep_filename=eep_filename, eep_jira=eep_model.get("jira"),
    )
    # Codigo efetivo: o informado ou, se vazio, o descoberto pelo nome do projeto.
    ivr_efetivo = spec_model.get("ivr_resolvido") or ivr_code
    modelos_encadeados = [spec_model]
    if encadeado:
        for n_spec, (raw_n, nome_n) in enumerate(lista_specs[1:], start=2):
            avisar(7 + n_spec, f"Lendo a SPEC {n_spec} ({nome_n})...")
            modelos_encadeados.append(
                spec_reader.read_spec(
                    io.BytesIO(raw_n), ivr_code=ivr_efetivo,
                    eep_nome=eep_model.get("nome"), eep_filename=eep_filename, eep_jira=eep_model.get("jira"),
                )
            )

    # EEP com tabela de cenarios/targets de transferencia e projeto que nao aparece na SPEC (nao houve alteracao de
    # navegacao): trata como projeto de transferencia, mesmo que o seletor esteja em "Alteracao de SPEC".
    transferencia_auto = False
    if tipo_a and not modo_completo and (eep_model.get("cenarios_transferencia") or []):
        sem_projeto_na_spec = not spec_model.get("ivr_resolvido") or not spec_model["versionamento"].get("estados_alterados")
        if sem_projeto_na_spec:
            tipo_a = False
            transferencia_auto = True

    avisar(12, "Detectando a(s) cor(es) da versão vigente...")

    def _cores_e_itens(raw_x, modelo_x):
        cores_x = [] if (modo_completo or not tipo_a) else color_utils.detectar_cores_projeto(io.BytesIO(raw_x), ivr_efetivo)
        # Cores que marcam as linhas dos estados no versionamento (ex.: amarelo) tambem identificam as
        # celulas alteradas nas abas de estado, mesmo quando o cabecalho do bloco usa outra cor.
        for cor_estado in modelo_x["versionamento"].get("cores_estados", []):
            if cor_estado not in cores_x:
                cores_x = list(cores_x) + [cor_estado]
        itens_x = color_utils.scan_all_sheets_for_color(io.BytesIO(raw_x), cores_x) if cores_x else {}
        return cores_x, itens_x

    cores_detectadas, itens_cor = _cores_e_itens(spec_raw, spec_model)
    cor_detectada = cores_detectadas[0] if cores_detectadas else None
    if encadeado:
        rotulos = specs_encadeadas.rotulos_unicos([n for _b, n in lista_specs])
        itens_comb = [
            {"modelo": spec_model, "rotulo": rotulos[0], "arquivo": lista_specs[0][1], "itens_cor": itens_cor}
        ]
        for k in range(1, len(lista_specs)):
            _c, itens_k = _cores_e_itens(lista_specs[k][0], modelos_encadeados[k])
            itens_comb.append({"modelo": modelos_encadeados[k], "rotulo": rotulos[k], "arquivo": lista_specs[k][1], "itens_cor": itens_k})
        inicio_entrada = _ct_start(spec_model)
        spec_model, itens_cor = specs_encadeadas.combinar_specs(itens_comb)
        spec_model["_start_state_resolvido"] = inicio_entrada

    def _sub_progresso(pct_interno, etapa):
        # A geracao de CTs relata seu proprio progresso 0-100; remapeia para
        # a fatia 20%-90% do progresso geral desta funcao.
        avisar(20 + (max(0, min(100, pct_interno)) / 100) * 70, etapa)

    plano = gerar_plano_ct(
        spec_model, eep_model, tipo_a=tipo_a, itens_cor=itens_cor, progress_callback=_sub_progresso, modo_completo=modo_completo
    )

    spec_model_empresas = plano_empresas = None
    if spec_bytes_empresas:
        avisar(91, "Processando a segunda SPEC (ClaroEmpresas)...")
        spec_raw_2 = _bytes_of(spec_bytes_empresas)
        spec_model_empresas = spec_reader.read_spec(
            io.BytesIO(spec_raw_2), ivr_code=ivr_efetivo,
            eep_nome=eep_model.get("nome"), eep_filename=eep_filename, eep_jira=eep_model.get("jira"),
        )
        cores_2 = color_utils.detectar_cores_projeto(io.BytesIO(spec_raw_2), ivr_efetivo)
        for cor_estado in spec_model_empresas["versionamento"].get("cores_estados", []):
            if cor_estado not in cores_2:
                cores_2 = list(cores_2) + [cor_estado]
        itens_cor_2 = color_utils.scan_all_sheets_for_color(io.BytesIO(spec_raw_2), cores_2) if cores_2 else {}
        plano_empresas = gerar_plano_ct(spec_model_empresas, eep_model, tipo_a=tipo_a, itens_cor=itens_cor_2)

    avisar(98, "Finalizando...")

    if transferencia_auto:
        plano["revisao_necessaria"].append(
            {
                "tipo": "info_transferencia_detectada",
                "detalhe": "O EEP traz uma tabela de cenários com IDs/targets de transferência e o projeto não aparece no "
                "versionamento da SPEC: modelei como projeto de TRANSFERÊNCIA (1 CT por cenário do EEP, percorrendo a SPEC "
                "até a transferência ATH).",
            }
        )
    if encadeado:
        specs_txt = " → ".join(f"{x['rotulo']} ({x['arquivo']})" for x in spec_model.get("_specs", []))
        saltos = spec_model.get("_saltos_specs") or []
        saltos_txt = "; ".join(f"{x['de']} → {x['para']}: {x['quantidade']} saída(s)" for x in saltos) or "nenhuma saída marcada como migração"
        plano["revisao_necessaria"].append(
            {
                "tipo": "info_specs_encadeadas",
                "detalhe": f"Modelagem encadeada: {specs_txt}. O fluxo começa na primeira SPEC e continua na seguinte nas saídas "
                f"marcadas como MIGRAÇÃO SPEC (coluna Observações). Saltos encontrados: {saltos_txt}. Estados de mesmo nome em SPECs "
                "diferentes aparecem com o sufixo da SPEC, ex.: \"PedeID (CRN)\". Saídas para uma SPEC que não foi anexada terminam "
                "a jornada no estado \"Destino (SPEC X)\".",
            }
        )
    if sem_eep and not modo_completo:
        plano["revisao_necessaria"].append(
            {
                "tipo": "info_sem_eep",
                "detalhe": "Modelagem feita sem EEP (incidente/correção): o escopo, o objetivo e as regras vêm do "
                "versionamento da SPEC para o IVR informado. Chaves sistêmicas e VDNs do EEP não foram lidos.",
            }
        )
    if spec_model.get("ivr_origem") and spec_model.get("ivr_origem") != "informado pelo usuario":
        plano["revisao_necessaria"].append(
            {
                "tipo": "info_ivr_identificado",
                "detalhe": f"Código do IVR não informado: usei {spec_model['ivr_resolvido']}, identificado pelo "
                f"{spec_model['ivr_origem']}. Se não for esse o projeto, informe o código IVR e gere de novo.",
            }
        )

    jira_eep = eep_model.get("jira") if "não identificado" not in str(eep_model.get("jira") or "") else None
    jira_ivr = "SPEC-COMPLETA" if modo_completo else (jira_eep if (not tipo_a and jira_eep) else None) or (
        ivr_efetivo or spec_model["versionamento"].get("ivr") or eep_model.get("jira") or "IVR não identificado"
    )

    return {
        "modo_completo": modo_completo,
        "projeto_nome": "Cobertura completa da SPEC" if modo_completo else (
            re.sub(r"^\s*IVR\W*\d{5,7}\s*[-–:]*\s*", "", str(spec_model["versionamento"].get("ivr") or "")).strip() or eep_model.get("nome")
            if sem_eep
            else eep_model.get("nome")
        ),
        "sem_eep": sem_eep,
        "jira_ivr": jira_ivr,
        "chaves_api": eep_model.get("chaves", []),
        "vdns_roteamento": eep_model.get("vdns", []),
        "historico_versionamento": spec_model["versionamento"].get("estados_alterados", []),
        "cor_detectada": cor_detectada,
        "casos_teste": plano["casos_teste"],
        "revisao_necessaria": plano["revisao_necessaria"],
        "bi_marcacoes": plano["bi_marcacoes"],
        "sps_regressao": plano.get("sps_regressao") or [],
        "legenda": plano["legenda"],
        "planejamento": montar_planejamento(plano, eep_model, spec_model, ivr_efetivo, tipo_a),
        "versao_spec": spec_model["versionamento"].get("versao"),
        "titulo_ivr_spec": spec_model["versionamento"].get("ivr"),
        "casos_teste_empresas": plano_empresas["casos_teste"] if plano_empresas else None,
        "specs_encadeadas": spec_model.get("_specs") if encadeado else None,
        # Campos internos, usados apenas por exportar_planilha_para_bytes:
        "_plano": plano,
        "_plano_empresas": plano_empresas,
        "_spec_model": spec_model,
        "_eep_model": eep_model,
        "_ivr_code": ivr_code,
    }


def dados_para_frontend(dados):
    """Remove os campos internos (prefixo `_`) antes de responder ao frontend."""
    return {k: v for k, v in dados.items() if not k.startswith("_")}


def filtrar_dados_por_spec(dados, specs):
    """Exportacao FILTRADA: so os CTs que passam por uma das SPECs escolhidas (CRN, MOVEL...). Legenda, marcacoes de BI
    e SPs de regressao acompanham o recorte; o planejamento completo (de todos os CTs) sai da planilha."""
    specs = {str(x) for x in (specs or []) if x}
    if not specs:
        return dados
    todos = dados.get("casos_teste") or []
    casos = [c for c in todos if any((s or {}).get("spec") in specs for s in (c.get("steps") or []))]
    ids = {c["ct_id"] for c in casos}

    def _filtrar(lista):
        saida = []
        for linha in lista or []:
            cts = [x.strip() for x in str(linha.get("ct") or "").split(",") if x.strip() in ids]
            if cts:
                saida.append({**linha, "ct": ", ".join(cts)})
        return saida

    legenda = []
    for b in dados.get("legenda") or []:
        do_bloco = [c for c in casos if c.get("bloco_nome") == b.get("bloco")]
        if not do_bloco:
            continue
        sps = sorted({c["sp_final"] for c in do_bloco if c.get("sp_final")})
        cts = [c["ct_id"] for c in do_bloco]
        legenda.append({**b, "cts": f"{cts[0]} a {cts[-1]}" if len(cts) > 1 else cts[0], "sps": ", ".join(sps) if sps else "Preservação sem novo SP"})
    novo = dict(dados)
    novo.update(
        casos_teste=casos,
        legenda=legenda,
        bi_marcacoes=_filtrar(dados.get("bi_marcacoes")),
        sps_regressao=_filtrar(dados.get("sps_regressao")),
        planejamento=None,
        filtro_descricao=f"SPEC {', '.join(sorted(specs))} — {len(casos)} de {len(todos)} CTs",
    )
    return novo


def dados_do_navegador_para_exportacao(dados):
    """Reconstroi o que o gerador de xlsx precisa a partir do JSON que o proprio
    navegador guardou (resultado da modelagem) — assim o xlsx sai mesmo quando o
    servidor perdeu a SPEC/EEP da sessao (reinicio/outra maquina)."""
    casos = dados["casos_teste"]
    legenda = dados.get("legenda") or []
    plano = {
        "casos_teste": casos,
        "revisao_necessaria": dados.get("revisao_necessaria") or [],
        "bi_marcacoes": dados.get("bi_marcacoes") or [],
        "sps_regressao": dados.get("sps_regressao") or [],
        "legenda": legenda,
        "blocos": [{"titulo": l.get("titulo", "")} for l in legenda],
        "filtro_descricao": dados.get("filtro_descricao"),
    }
    plano_empresas = {"casos_teste": dados["casos_teste_empresas"]} if dados.get("casos_teste_empresas") else None
    return {
        "_plano": plano,
        "_plano_empresas": plano_empresas,
        "_eep_model": {
            "nome": dados.get("projeto_nome") or "—",
            "chaves": dados.get("chaves_api") or [],
            "vdns": dados.get("vdns_roteamento") or [],
        },
        "_spec_model": {"versionamento": {"versao": dados.get("versao_spec"), "ivr": dados.get("titulo_ivr_spec")}},
        "_ivr_code": dados.get("jira_ivr"),
        "planejamento": dados.get("planejamento"),
    }


def exportar_planilha_para_bytes(dados):
    """Gera o xlsx final (com JIRA fix aplicado) e roda a validacao pos-geracao."""
    aba_extra = None
    if dados.get("_plano_empresas"):
        aba_extra = ("Cenarios_ClaroEmpresas", dados["_plano_empresas"]["casos_teste"])

    wb = xlsx_writer.exportar_modelagem_para_xlsx(
        dados["_plano"],
        dados["_eep_model"],
        dados["_spec_model"],
        ivr_code=dados.get("_ivr_code"),
        aba_extra=aba_extra,
        planejamento=dados.get("planejamento"),
    )

    buffer = io.BytesIO()
    wb.save(buffer)
    xlsx_bytes = jira_fix.apply_jira_fix(buffer.getvalue())

    abas_ct = ["Cenarios_MERGE", "Cenarios_ClaroEmpresas"] if aba_extra else ["Cenarios"]
    relatorio = validator.validar_xlsx(xlsx_bytes, abas_ct=abas_ct)

    return xlsx_bytes, relatorio
