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


def detectar_cor_projeto(spec_bytes, ivr_code, aba_versionamento="_Versionamento_"):
    """
    Localiza o bloco do IVR informado na aba de Versionamento e devolve a cor de
    fundo (AARRGGBB) predominante das celulas daquele bloco. Se nao encontrar o
    codigo IVR ou nenhuma cor marcada, devolve None (o chamador deve tratar como
    "sem filtro de cor", cobrindo tudo o que estiver na aba).
    """
    part = _sheet_name_to_part(spec_bytes, aba_versionamento)
    if not part:
        for alt in ("Versionamento", "VersionamentoBI", "_VersionamentoBI_"):
            part = _sheet_name_to_part(spec_bytes, alt)
            if part:
                break
    if not part:
        return None

    fill_colors, xf_to_fill = get_fill_maps(spec_bytes)
    shared = _shared_strings(spec_bytes)

    with zipfile.ZipFile(spec_bytes, "r") as z:
        sheet_xml = etree.fromstring(z.read(part))

    def get_val(cell):
        v = cell.find(f"{{{NS}}}v")
        if v is None or v.text is None:
            return ""
        if cell.get("t") == "s":
            idx = int(v.text)
            return shared[idx] if idx < len(shared) else ""
        return v.text

    ivr_norm = (ivr_code or "").strip().upper()
    colors_found = Counter()
    found_target_row = False

    for row in sheet_xml.findall(f".//{{{NS}}}row"):
        row_has_target = False
        row_colors = []
        for cell in row.findall(f"{{{NS}}}c"):
            val = str(get_val(cell))
            color = cell_color(cell, xf_to_fill, fill_colors)
            if color and color not in ("00000000", ""):
                row_colors.append(color)
            if ivr_norm and ivr_norm in val.strip().upper():
                row_has_target = True
        if row_has_target:
            found_target_row = True
            colors_found.update(row_colors)

    if not found_target_row or not colors_found:
        # Sem codigo IVR encontrado (ou linha sem marcacao de cor): varre a
        # planilha inteira e usa a cor mais frequente entre as celulas
        # marcadas, assumindo que seja a versao vigente.
        colors_found = Counter()
        for row in sheet_xml.findall(f".//{{{NS}}}row"):
            for cell in row.findall(f"{{{NS}}}c"):
                color = cell_color(cell, xf_to_fill, fill_colors)
                if color and color not in ("00000000", ""):
                    colors_found.update([color])

    if not colors_found:
        return None
    return colors_found.most_common(1)[0][0]


def scan_all_sheets_for_color(spec_bytes, target_color):
    """Retorna {aba: [(row, col, valor, conteudo_adjacente)]} para celulas na cor alvo."""
    if not target_color:
        return {}
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
                    if is_project_color(cell, xf_to_fill, fill_colors, target_color):
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
