"""
PDF da aba "Execucao dos Testes": a modelagem de cada CT (Gherkin, pre-requisito
e steps) seguida das evidencias anexadas. Cada evidencia vai EMBUTIDA no PDF
como anotacao de arquivo anexo (icone de clipe): ao clicar no icone, o leitor
de PDF abre/baixa o arquivo (funciona no Adobe Acrobat/Reader, Foxit e
Firefox; o visualizador do Chrome/Edge nao oferece esse clique).
"""
import datetime
import os
import re
import shutil
import tempfile
from urllib.parse import quote

from fpdf import FPDF, FontFace
from fpdf.enums import FileAttachmentAnnotationName, XPos, YPos

from ct_rules import BLOCO_PALETTE, REGRESSIVO_COR

# Fonte padrao do PDF (Helvetica) so cobre Latin-1: troca os simbolos fora
# dessa faixa (setas, travessao longo, reticencias, emoji) por equivalentes.
_SUBSTITUICOES = {
    "—": "-", "–": "-", "→": "->", "←": "<-", "…": "...", "“": '"', "”": '"',
    "‘": "'", "’": "'", "•": "*", "≠": "!=", "≤": "<=", "≥": ">=", "✓": "OK",
    "⚠️": "(!)", "⚠": "(!)", "📎": "", "​": "",
}


def _t(texto):
    s = "" if texto is None else str(texto)
    for k, v in _SUBSTITUICOES.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _rgb(hexa):
    h = hexa.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _tamanho(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


class _PDF(FPDF):
    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, f"Pagina {self.page_no()}/{{nb}}", align="C")


_STATUS = {
    "pendente": ("Pendente", (181, 137, 0)),
    "ok": ("OK", (26, 107, 26)),
    "nok": ("Não OK", (176, 0, 0)),
    "blocked": ("Bloqueado", (190, 120, 0)),
}


def gerar_pdf_execucao(dados, evidencias_por_ct, avaliacoes=None):
    """`dados`: resultado completo da modelagem (casos_teste, jira_ivr, ...).
    `evidencias_por_ct`: {ct_id: [{"nome", "dados": bytes}]}.
    `avaliacoes`: {ct_id: {"status", "comments"}} (status e bug aberto de cada
    CT). Devolve os bytes do PDF."""
    avaliacoes = avaliacoes or {}
    casos = dados.get("casos_teste") or []
    total_evid = sum(len(v) for v in evidencias_por_ct.values())
    contagem = {k: 0 for k in _STATUS}
    for c in casos:
        contagem[(avaliacoes.get(c["ct_id"]) or {}).get("status", "pendente")] += 1

    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(True, margin=14)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(31, 78, 121)
    pdf.cell(0, 9, _t("Execução dos Testes"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    cabecalho = [
        ("Projeto", dados.get("projeto_nome") or "-"),
        ("IVR / JIRA", dados.get("jira_ivr") or "-"),
        ("Gerado em", datetime.datetime.now().strftime("%d/%m/%Y %H:%M")),
        *([("Parte", dados["parte"])] if dados.get("parte") else []),
        ("Casos de teste", str(len(casos))),
        ("Evidências anexadas", str(total_evid)),
        ("Status", "  |  ".join(f"{_STATUS[k][0]}: {v}" for k, v in contagem.items())),
    ]
    for rotulo, valor in cabecalho:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(38, 5.5, _t(rotulo + ":"))
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5.5, _t(valor), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    tmp = tempfile.mkdtemp(prefix="modeler_pdf_")
    try:
        for caso in casos:
            _desenhar_caso(pdf, caso, evidencias_por_ct.get(caso["ct_id"], []), tmp, avaliacoes.get(caso["ct_id"]))
        return bytes(pdf.output())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _desenhar_caso(pdf, caso, evidencias, tmp, avaliacao=None):
    if pdf.will_page_break(55):
        pdf.add_page()
    cor = REGRESSIVO_COR if caso.get("regressivo") else BLOCO_PALETTE[(caso["bloco"] - 1) % len(BLOCO_PALETTE)]
    pdf.set_fill_color(*_rgb(cor["header"]))
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    titulo = f" {caso['ct_id']}  |  {caso['bloco_nome']}  |  Estado: {caso['estado']}  |  {caso.get('perfil', '')}"
    pdf.cell(0, 7, _t(titulo), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    status_nome, status_cor = _STATUS[(avaliacao or {}).get("status", "pendente")]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*status_cor)
    comentario = ((avaliacao or {}).get("comments") or "").strip()
    linha_status = f"Status: {status_nome}" + (f"   |   Bug / comentário: {comentario}" if comentario else "")
    pdf.multi_cell(0, 5, _t(linha_status), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(0, 4.8, _t(caso["gherkin"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if caso.get("sp_pendente"):
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(160, 100, 0)
        pdf.cell(0, 4.5, _t("SP PENDENTE - inserir o ScriptPoint após a publicação do BI"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 4.2, _t("PRÉ-REQUISITO: " + (caso.get("pre_requisito") or "-")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "", 7.5)
    cabecalho = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=(85, 85, 85))
    with pdf.table(
        col_widths=(10, 50, 34, 92),
        text_align=("CENTER", "LEFT", "LEFT", "LEFT"),
        line_height=3.9,
        headings_style=cabecalho,
        padding=0.8,
    ) as tabela:
        linha = tabela.row()
        for h in ("Step", "Ação", "Estado / Prompt", "Resultado esperado"):
            linha.cell(_t(h))
        for step in caso.get("steps", []):
            linha = tabela.row()
            estado_prompt = step.get("estado") or "-"
            if step.get("prompt_id") not in (None, "—", "-"):
                estado_prompt += f"\n[{step['prompt_id']}]"
            resultado = step.get("resultado", step.get("prompt_texto", "-"))
            linha.cell(str(step.get("step_num", "")))
            linha.cell(_t(step.get("acao")))
            linha.cell(_t(estado_prompt))
            linha.cell(_t(resultado))

    pdf.ln(1.5)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(31, 78, 121)
    if not evidencias:
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(0, 5, _t("Sem evidências anexadas."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(0, 5, _t(f"Evidências anexadas ({len(evidencias)}) - clique no nome para abrir (pasta evidencias/ do ZIP):"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(30, 30, 30)
        for i, ev in enumerate(evidencias):
            if pdf.will_page_break(7):
                pdf.add_page()
            pasta = os.path.join(tmp, f"{caso['ct_id']}_{i}")
            os.makedirs(pasta, exist_ok=True)
            caminho = os.path.join(pasta, ev["nome"])
            with open(caminho, "wb") as f:
                f.write(ev["dados"])
            y = pdf.get_y()
            pdf.file_attachment_annotation(caminho, x=pdf.l_margin + 1, y=y + 0.4, w=4.5, h=4.5, name=FileAttachmentAnnotationName.PAPERCLIP_TAG)
            pdf.set_x(pdf.l_margin + 8)
            # Link relativo: abre o arquivo da pasta evidencias/<CT>/ do ZIP exportado
            # junto (extraido ao lado do PDF); o clipe continua valendo no Adobe/Foxit/Firefox.
            pasta_ct = re.sub(r"[^\w-]", "_", caso["ct_id"])
            destino = f"evidencias/{pasta_ct}/{quote(ev['nome'])}"
            pdf.set_text_color(5, 80, 170)
            pdf.cell(0, 5.4, _t(f"{ev['nome']}  ({_tamanho(len(ev['dados']))})"), link=destino,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(30, 30, 30)
    pdf.ln(5)
