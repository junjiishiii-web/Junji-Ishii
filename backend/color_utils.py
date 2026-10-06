"""
Deteccao de cor de celula em planilhas SPEC (openpyxl / OOXML cru).

A Claro marca visualmente, por versao da SPEC, quais celulas mudaram usando o
preenchimento (fill) de fundo. Cada nova versao usa uma cor diferente da
anterior. Este modulo le o XML interno do xlsx (fills/estilos) para descobrir
a cor real de cada celula -- openpyxl nao expoe isso de forma direta e barata
para varrer o arquivo inteiro, entao lemos o zip/XML diretamente, como a
skill de modelagem QA URA/BDD documenta.
"""
import re
import zipfile
from collections import Counter

from lxml import etree

from spec_reader import _padrao_ivr, celula_casa_ivr

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def get_fill_maps(spec_path_or_bytes):
    """Retorna (fill_colors: {fillId: 'AARRGGBB'}, xf_to_fill: {styleIndex: fillId})."""
    with zipfile.ZipFile(spec_path_or_bytes, "r") as z:
        styles = etree.fromstring(z.read("xl/styles.xml"))
    fills = styles.findall(f".//{{{NS}}}fills/{{{NS}}}fill")
    fill_colors = {}
    for i, fill in enumerate(fills):
        fg = fill.find(f".//{{{NS}}}fgColor")
        if fg is not None:
            rgb = fg.get("rgb", "")
            if not rgb and fg.get("theme") is not None:
                rgb = f"theme:{fg.get('theme')}"
            fill_colors[i] = rgb
    xfs = styles.findall(f".//{{{NS}}}cellXfs/{{{NS}}}xf")
    xf_to_fill = {i: int(xf.get("fillId", "0")) for i, xf in enumerate(xfs)}
    return fill_colors, xf_to_fill


def is_project_color(cell, xf_to_fill, fill_colors, target_rgb):
    s = cell.get("s")
    if not s:
        return False
    return fill_colors.get(xf_to_fill.get(int(s), 0), "") == target_rgb


def cell_color(cell, xf_to_fill, fill_colors):
    s = cell.get("s")
    if not s:
        return ""
    return fill_colors.get(xf_to_fill.get(int(s), 0), "")


def _sheet_name_to_part(spec_bytes, sheet_name):
    with zipfile.ZipFile(spec_bytes, "r") as z:
        wb_tree = etree.fromstring(z.read("xl/workbook.xml"))
        sheet_map = {
            sh.get("name"): sh.get(f"{{{NS_R}}}id")
            for sh in wb_tree.findall(f".//{{{NS}}}sheets/{{{NS}}}sheet")
        }
        rid = sheet_map.get(sheet_name)
        if not rid:
            return None
        rels_tree = etree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rels = {
            r.get("Id"): r.get("Target")
            for r in rels_tree.findall(f".//{{{NS_REL}}}Relationship")
        }
        target = rels.get(rid, "")
        if target.startswith("/"):
            target = target[1:]
        return target if target.startswith("xl/") else "xl/" + target


def _shared_strings(spec_bytes):
    with zipfile.ZipFile(spec_bytes, "r") as z:
        if "xl/sharedStrings.xml" not in z.namelist():
            return []
        ss_tree = etree.fromstring(z.read("xl/sharedStrings.xml"))
    return [
        "".join(t.text or "" for t in si.findall(f".//{{{NS}}}t"))
        for si in ss_tree.findall(f"{{{NS}}}si")
    ]


def detectar_cores_projeto(spec_bytes, ivr_code, aba_versionamento="_Versionamento_"):
    """Todas as cores de fundo dos cabecalhos de bloco do IVR informado, na
    ordem de frequencia. Um mesmo IVR pode ter varios blocos em cores
    diferentes (ex.: versao inicial em rosa e a atualizacao em amarelo) e
    todos entram no escopo. Compara pelos digitos do codigo (tolera "IVR-N" e
    "IVR- N") e ignora o branco de fundo. Sem codigo, usa a cor mais frequente
    da aba; com codigo nao encontrado, devolve [] (nada de adivinhar a cor de
    outro projeto)."""
    part = _sheet_name_to_part(spec_bytes, aba_versionamento)
    if not part:
        for alt in ("Versionamento", "VersionamentoBI", "_VersionamentoBI_"):
            part = _sheet_name_to_part(spec_bytes, alt)
            if part:
                break
    if not part:
        return []

    fill_colors, xf_to_fill = get_fill_maps(spec_bytes)
    shared = _shared_strings(spec_bytes)
    with zipfile.ZipFile(spec_bytes, "r") as z:
        sheet_xml = etree.fromstring(z.read(part))

    def get_val(cell):
        if cell.get("t") == "inlineStr":
            return "".join(t.text or "" for t in cell.findall(f".//{{{NS}}}t"))
        v = cell.find(f"{{{NS}}}v")
        if v is None or v.text is None:
            return ""
        if cell.get("t") == "s":
            idx = int(v.text)
            return shared[idx] if idx < len(shared) else ""
        return v.text

    SEM_COR = ("", "00000000", "FFFFFFFF")
    alvo, padrao = _padrao_ivr(ivr_code)
    contagem = Counter()
    for row in sheet_xml.findall(f".//{{{NS}}}row"):
        cores_linha = Counter()
        casou = False
        for cell in row.findall(f"{{{NS}}}c"):
            if alvo and celula_casa_ivr(str(get_val(cell)).strip().upper(), alvo, padrao):
                casou = True
            cor = cell_color(cell, xf_to_fill, fill_colors)
            if cor not in SEM_COR:
                cores_linha[cor] += 1
        if alvo:
            if casou and cores_linha:
                contagem[cores_linha.most_common(1)[0][0]] += 1
        else:
            contagem.update(cores_linha)
    if not alvo:
        return [c for c, _ in contagem.most_common(1)]
    return [c for c, _ in contagem.most_common()]


def detectar_cor_projeto(spec_bytes, ivr_code, aba_versionamento="_Versionamento_"):
    cores = detectar_cores_projeto(spec_bytes, ivr_code, aba_versionamento)
    return cores[0] if cores else None


def scan_all_sheets_for_color(spec_bytes, target_color):
    """Retorna {aba: [(row, col, valor, conteudo_adjacente)]} para celulas na cor alvo."""
    if not target_color:
        return {}
    alvos = {target_color} if isinstance(target_color, str) else set(target_color)
    fill_colors, xf_to_fill = get_fill_maps(spec_bytes)
    shared = _shared_strings(spec_bytes)

    with zipfile.ZipFile(spec_bytes, "r") as z:
        wb_tree = etree.fromstring(z.read("xl/workbook.xml"))
        sheet_map = {
            sh.get("name"): sh.get(f"{{{NS_R}}}id")
            for sh in wb_tree.findall(f".//{{{NS}}}sheets/{{{NS}}}sheet")
        }
        rels_tree = etree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rels = {
            r.get("Id"): r.get("Target")
            for r in rels_tree.findall(f".//{{{NS_REL}}}Relationship")
        }

        def get_val(cell):
            if cell.get("t") == "inlineStr":
                return "".join(t.text or "" for t in cell.findall(f".//{{{NS}}}t"))
            v = cell.find(f"{{{NS}}}v")
            if v is None or v.text is None:
                return ""
            if cell.get("t") == "s":
                idx = int(v.text)
                return shared[idx] if idx < len(shared) else ""
            return v.text

        resultados = {}
        for aba, rid in sheet_map.items():
            target_file = rels.get(rid, "")
            if target_file.startswith("/"):
                target_file = target_file[1:]
            key = target_file if target_file.startswith("xl/") else "xl/" + target_file
            try:
                xml = z.read(key)
            except KeyError:
                continue
            tree = etree.fromstring(xml)
            itens = []
            for row in tree.findall(f".//{{{NS}}}row"):
                cells = row.findall(f"{{{NS}}}c")
                for ci, cell in enumerate(cells):
                    if cell.get("s") and fill_colors.get(xf_to_fill.get(int(cell.get("s")), 0), "") in alvos:
                        val = str(get_val(cell)).strip()
                        if val:
                            cont = str(get_val(cells[ci + 1])) if ci + 1 < len(cells) else ""
                            itens.append((row.get("r", "?"), ci + 1, val, cont[:160]))
            if itens:
                resultados[aba] = itens
    return resultados


def cell_ref_to_row(ref):
    """'A17' -> 17. Usado para casar (row, col) do XML cru com openpyxl."""
    m = re.match(r"[A-Z]+(\d+)", ref or "")
    return int(m.group(1)) if m else None
