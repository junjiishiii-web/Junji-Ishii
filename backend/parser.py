"""
Orquestrador fino: liga spec_reader -> color_utils -> eep_reader -> ct_rules
-> xlsx_writer -> jira_fix -> validator, e adapta o resultado para o formato
que o frontend (index.html) e o app.py ja esperam.
"""
import io
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import color_utils
import eep_reader
import jira_fix
import spec_reader
import validator
import xlsx_writer
from ct_rules import gerar_plano_ct


def _bytes_of(obj):
    if hasattr(obj, "read"):
        return obj.read()
    return obj


def _sem_callback(pct, etapa):
    pass


def gerar_modelagem_testes_completa(spec_bytes, eep_bytes, tipo_a=True, ivr_code=None,
                                     eep_filename="", spec_bytes_empresas=None, progress_callback=None):
    avisar = progress_callback or _sem_callback
    spec_raw = _bytes_of(spec_bytes)
    eep_raw = _bytes_of(eep_bytes)

    avisar(2, "Lendo a SPEC...")
    spec_model = spec_reader.read_spec(io.BytesIO(spec_raw), ivr_code=ivr_code)

    avisar(10, "Detectando a cor da versão vigente...")
    cor_detectada = color_utils.detectar_cor_projeto(io.BytesIO(spec_raw), ivr_code)
    itens_cor = color_utils.scan_all_sheets_for_color(io.BytesIO(spec_raw), cor_detectada) if cor_detectada else {}

    avisar(15, "Lendo o EEP...")
    eep_model = eep_reader.minerar_eep(eep_raw, eep_filename)

    def _sub_progresso(pct_interno, etapa):
        # A geracao de CTs relata seu proprio progresso 0-100; remapeia para
        # a fatia 20%-90% do progresso geral desta funcao.
        avisar(20 + (max(0, min(100, pct_interno)) / 100) * 70, etapa)

    plano = gerar_plano_ct(spec_model, eep_model, tipo_a=tipo_a, itens_cor=itens_cor, progress_callback=_sub_progresso)

    spec_model_empresas = plano_empresas = None
    if spec_bytes_empresas:
        avisar(91, "Processando a segunda SPEC (ClaroEmpresas)...")
        spec_raw_2 = _bytes_of(spec_bytes_empresas)
        spec_model_empresas = spec_reader.read_spec(io.BytesIO(spec_raw_2), ivr_code=ivr_code)
        cor_2 = color_utils.detectar_cor_projeto(io.BytesIO(spec_raw_2), ivr_code)
        itens_cor_2 = color_utils.scan_all_sheets_for_color(io.BytesIO(spec_raw_2), cor_2) if cor_2 else {}
        plano_empresas = gerar_plano_ct(spec_model_empresas, eep_model, tipo_a=tipo_a, itens_cor=itens_cor_2)

    avisar(98, "Finalizando...")

    jira_ivr = ivr_code or spec_model["versionamento"].get("ivr") or eep_model.get("jira") or "IVR não identificado"

    return {
        "projeto_nome": eep_model.get("nome"),
        "jira_ivr": jira_ivr,
        "chaves_api": eep_model.get("chaves", []),
        "vdns_roteamento": eep_model.get("vdns", []),
        "historico_versionamento": spec_model["versionamento"].get("estados_alterados", []),
        "cor_detectada": cor_detectada,
        "casos_teste": plano["casos_teste"],
        "revisao_necessaria": plano["revisao_necessaria"],
        "bi_marcacoes": plano["bi_marcacoes"],
        "legenda": plano["legenda"],
        "casos_teste_empresas": plano_empresas["casos_teste"] if plano_empresas else None,
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
    )

    buffer = io.BytesIO()
    wb.save(buffer)
    xlsx_bytes = jira_fix.apply_jira_fix(buffer.getvalue())

    abas_ct = ["Cenarios_MERGE", "Cenarios_ClaroEmpresas"] if aba_extra else ["Cenarios"]
    relatorio = validator.validar_xlsx(xlsx_bytes, abas_ct=abas_ct)

    return xlsx_bytes, relatorio
