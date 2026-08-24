"""
JIRA fix: converte celulas inlineStr -> sharedStrings para compatibilidade
com a importacao de planilhas no XRAY/JIRA. Porte quase literal do que a
skill de modelagem QA URA/BDD documenta.
"""
import io
import zipfile

from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def apply_jira_fix(src_bytes):
    """Recebe bytes de um .xlsx (openpyxl grava inlineStr por padrao) e devolve
    bytes com todas as strings convertidas para sharedStrings.xml."""
    with zipfile.ZipFile(io.BytesIO(src_bytes), "r") as zin:
        contents = {n: zin.read(n) for n in zin.namelist()}

    sheets = [n for n in contents if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    shared_list = []
    shared_idx = {}

    def get_index(text):
        if text not in shared_idx:
            shared_idx[text] = len(shared_list)
            shared_list.append(text)
        return shared_idx[text]

    total_cells = 0
    for sheet_name in sheets:
        tree = etree.fromstring(contents[sheet_name])
        for row in tree.findall(f".//{{{NS}}}row"):
            for cell in row.findall(f"{{{NS}}}c"):
                if cell.get("t") == "inlineStr":
                    is_el = cell.find(f"{{{NS}}}is")
                    if is_el is not None:
                        t_el = is_el.find(f"{{{NS}}}t")
                        text = (t_el.text or "") if t_el is not None else ""
                        if text.startswith('"'):
                            text = text[1:]
                        idx = get_index(text)
                        cell.remove(is_el)
                        cell.set("t", "s")
                        v = etree.SubElement(cell, f"{{{NS}}}v")
                        v.text = str(idx)
                        total_cells += 1
                if cell.get("t") == "n":
                    if cell.find(f"{{{NS}}}v") is None and cell.find(f"{{{NS}}}is") is None:
                        if "t" in cell.attrib:
                            del cell.attrib["t"]
        contents[sheet_name] = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)

    sst_root = etree.Element(f"{{{NS}}}sst", nsmap={None: NS})
    sst_root.set("count", str(total_cells))
    sst_root.set("uniqueCount", str(len(shared_list)))
    for text in shared_list:
        si = etree.SubElement(sst_root, f"{{{NS}}}si")
        t_el = etree.SubElement(si, f"{{{NS}}}t")
        if text and ("\n" in text or text[:1] == " " or text[-1:] == " "):
            t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t_el.text = text
    contents["xl/sharedStrings.xml"] = etree.tostring(sst_root, xml_declaration=True, encoding="UTF-8", standalone=True)

    ct_tree = etree.fromstring(contents["[Content_Types].xml"])
    if not any(p.get("PartName") == "/xl/sharedStrings.xml" for p in ct_tree.findall(f"{{{CT_NS}}}Override")):
        override = etree.SubElement(ct_tree, f"{{{CT_NS}}}Override")
        override.set("PartName", "/xl/sharedStrings.xml")
        override.set("ContentType", "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml")
        contents["[Content_Types].xml"] = etree.tostring(ct_tree, xml_declaration=True, encoding="UTF-8", standalone=True)

    rels_tree = etree.fromstring(contents["xl/_rels/workbook.xml.rels"])
    if not any("sharedStrings" in r.get("Type", "") for r in rels_tree.findall(f"{{{REL_NS}}}Relationship")):
        ids = [r.get("Id", "") for r in rels_tree.findall(f"{{{REL_NS}}}Relationship")]
        max_id = max((int(i[3:]) for i in ids if i.startswith("rId") and i[3:].isdigit()), default=0)
        rel = etree.SubElement(rels_tree, f"{{{REL_NS}}}Relationship")
        rel.set("Id", f"rId{max_id + 1}")
        rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings")
        rel.set("Target", "sharedStrings.xml")
        contents["xl/_rels/workbook.xml.rels"] = etree.tostring(rels_tree, xml_declaration=True, encoding="UTF-8", standalone=True)

    out_buffer = io.BytesIO()
    with zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in contents.items():
            zout.writestr(name, data)
    return out_buffer.getvalue()
