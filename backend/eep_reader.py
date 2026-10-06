"""
Mineracao do EEP (Especificacao de Escopo do Projeto) para extrair nome do
projeto, codigo JIRA, chaves de elegibilidade e VDNs de roteamento.

Aceita PDF (formato mais comum), com fallback para .xlsx/.docx quando o EEP
foi entregue nesses formatos.
"""
import io
import re


# Secoes do formulario padrao de EEP (FCG-FOR-038) e de EEPs mais simples. A chave
# e usada pelo planejamento; a regex casa o inicio do TITULO da secao.
_SECOES_EEP = [
    ("necessidade", r"qual a necessidade"),
    ("perfil", r"(?:\d+(?:\.\d+)*\.?\s*)?detalhamento do perfil"),
    ("as_is", r"(?:\d+(?:\.\d+)*\.?\s*)?(?:jornada atual|como a jornada funciona atualmente)"),
    ("regras", r"(?:\d+(?:\.\d+)*\.?\s*)?regras de neg[oó]cio"),
    ("solucao", r"(?:\d+(?:\.\d+)*\.?\s*)?descri[cç][aã]o geral"),
    ("solucao_detalhe", r"(?:\d+(?:\.\d+)*\.?\s*)?descri[cç][aã]o detalhada"),
    ("sucesso", r"(?:\d+(?:\.\d+)*\.?\s*)?par[aâ]metros de sucesso"),
    ("massa", r"(?:\d+(?:\.\d+)*\.?\s*)?massa de testes"),
    ("premissas", r"(?:\d+(?:\.\d+)*\.?\s*)?premissas"),
    ("restricoes", r"(?:\d+(?:\.\d+)*\.?\s*)?restri[cç][oõ]es"),
    ("resultados", r"quais os resultados desejados"),
    ("to_be", r"\d+\.\d+\.?\s*jornada da solu[cç][aã]o"),
    ("integracao", r"\d+\.\d+\.?\s*integra[cç][aã]o"),
    ("impactos", r"\d+\.\d+\.?\s*impactos e riscos"),
    # EEPs simples (texto livre)
    ("objetivo", r"objetivo(?: esperado)?\s*:?\s*$"),
    ("problemas", r"problemas observados"),
    ("validacao", r"como validar (?:o )?sucesso"),
    ("onde", r"onde ocorre"),
    ("impactados", r"quem [eé] impactado"),
]
_FIM_SECAO = re.compile(r"^(?:\d+\.?\s+[A-ZÇÃÕÁÉÍÓÚ ]{6,}|\d+\.?\s*controle de vers)", re.IGNORECASE)
_RUIDO_CABECALHO = re.compile(
    r"^(?:especifica[cç][aã]o de escopo de projeto.*|c[oó]digo:|fcg-for-\d+|[aá]rea:|performance|classifica[cç][aã]o:|"
    r"interno|revis[aã]o:|\d{1,2}|p[aá]ginas:|\d+\s+de\s+\d+|formul[aá]rio)$",
    re.IGNORECASE,
)


_MARCA_ITEM = "\x01"  # prefixo interno: a linha comeca um novo item/topico
_BULLET_RE = re.compile(r"^[\u2022\u25cf\u25aa\uf0b7\uf0a7\uf0d8\-\*]\s*")


def _linhas_limpas(texto):
    """Linhas do texto sem cabecalho/rodape do formulario. Linhas que iniciam um
    topico (bullet do PDF) ganham o prefixo _MARCA_ITEM; um bullet sozinho na linha
    marca a proxima linha de texto."""
    linhas, proximo_e_item, numero = [], False, ""
    for bruta in texto.splitlines():
        l = bruta.strip()
        if re.fullmatch(r"\d+(?:\.\d+)+\.?", l):
            numero = l + " "  # numero da secao sozinho na linha: cola no titulo que vem depois
            continue
        if numero and l:
            l, numero = numero + l, ""
        item = bool(_BULLET_RE.match(l)) or bool(re.match(r"^o\s{2,}\S", l))
        if item:
            l = _BULLET_RE.sub("", l)
            l = re.sub(r"^o\s{2,}", "", l).strip()
            if not l:
                proximo_e_item = True
                continue
        if not l or _RUIDO_CABECALHO.match(l):
            continue
        if l.lower().startswith(("a aprovação desse projeto", "a aprovacao desse projeto", "o cronograma de entrega")):
            continue
        if proximo_e_item:
            item, proximo_e_item = True, False
        linhas.append((_MARCA_ITEM if item else "") + l)
    return linhas


def _juntar_paragrafos(linhas):
    """O PDF quebra o texto em linhas curtas: junta as que sao continuacao da anterior
    (a nao ser que iniciem um topico ou a anterior termine em pontuacao)."""
    itens, atual = [], ""
    for bruta in linhas:
        novo_item = bruta.startswith(_MARCA_ITEM)
        l = bruta.lstrip(_MARCA_ITEM)
        continua = atual and not novo_item and not re.search(r"[.:;?!]$", atual)
        if continua:
            atual += " " + l
        else:
            if atual:
                itens.append(atual)
            atual = l
    if atual:
        itens.append(atual)
    return [re.sub(r"\s{2,}", " ", i).strip() for i in itens if len(i.strip()) > 2]


def _secoes_do_eep(texto):
    """{chave: [paragrafos]} das secoes reconhecidas. Titulos de secao nao entram no texto."""
    linhas = _linhas_limpas(texto)
    secoes, chave = {}, None
    for l_marcada in linhas:
        l = l_marcada.lstrip(_MARCA_ITEM)
        titulo = None
        if len(l) <= 110:
            for k, rx in _SECOES_EEP:
                if re.match(rx, l, re.IGNORECASE):
                    titulo = k
                    break
        if titulo:
            chave = titulo
            secoes.setdefault(chave, [])
            continue
        if _FIM_SECAO.match(l) and len(l) <= 90:
            chave = None
            continue
        if chave:
            secoes[chave].append(l_marcada)
    saida = {}
    for k, v in secoes.items():
        paragrafos = [p for p in _juntar_paragrafos(v) if not re.match(r"^complemento para ", p, re.IGNORECASE)]
        if paragrafos:
            saida[k] = paragrafos
    return saida


def _campos_do_formulario(texto):
    def pega(rotulo):
        m = re.search(rotulo + r"\s*:\s*\n*\s*([^\n]+)", texto, re.IGNORECASE)
        return m.group(1).strip() if m and m.group(1).strip() else None

    return {
        "produto_canal": pega(r"Produto/Canal"),
        "responsavel_cliente": pega(r"Respons[aá]vel Cliente"),
        "responsavel_mutant": pega(r"Respons[aá]vel Mutant"),
    }


def _minerar_texto(texto):
    nome_proj = re.search(r"Nome do Projeto:\s*(.*)", texto)
    jira_ivr = re.search(r"C[oó]digo do Projeto \(JIRA\):\s*(.*)", texto)
    if not jira_ivr:
        jira_ivr = re.search(r"\b((?:URA|IVR)-\d{5,7}(?:\s*/\s*(?:URA|IVR)-\d{5,7})?)\b", texto)

    words = re.findall(r"\b[a-zA-Z0-9_]{12,60}\b", texto)
    chaves_validas = []
    prefixos_chaves = (
        "Bases", "DDDHabilita", "BaseHabilita", "PrazoMaximo", "Segmentos",
        "Habilita", "DDDHabilitar", "Chave", "Switch",
    )
    ruido = ("projeto", "mutant", "responsavel", "formulario", "aprovacao", "documento", "versao")

    for w in words:
        if any(w.startswith(p) for p in prefixos_chaves):
            chaves_validas.append(w)
            continue
        maiusculas = sum(1 for c in w if c.isupper())
        if maiusculas >= 3 and not any(x in w.lower() for x in ruido):
            chaves_validas.append(w)

    chaves_finais = sorted(set(chaves_validas))

    vdns_minados = re.findall(r"(CHAVE\s*\d+\s*\([^)]+\))\s*-\s*[^-]+-\s*(VDN\s*\d+)", texto, re.IGNORECASE)
    if not vdns_minados:
        vdns_minados = re.findall(r"\b\d{7}\b|\b\d{2}\+base\+\d+\b", texto)

    try:
        secoes = _secoes_do_eep(texto or "")
        campos = _campos_do_formulario(texto or "")
    except Exception:
        secoes, campos = {}, {}

    return {
        "nome": nome_proj.group(1).strip() if nome_proj else None,
        "jira": jira_ivr.group(1).strip() if jira_ivr else None,
        "chaves": chaves_finais,
        "vdns": vdns_minados,
        "secoes": secoes,
        "campos": campos,
    }


def _minerar_pdf(pdf_bytes):
    from pdfminer.high_level import extract_text

    try:
        texto = extract_text(io.BytesIO(pdf_bytes))
    except Exception:
        texto = ""
    return _minerar_texto(texto)


def _minerar_xlsx(xlsx_bytes):
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    except Exception:
        return _minerar_texto("")
    partes = []
    for aba in wb.sheetnames:
        ws = wb[aba]
        for row in ws.iter_rows(values_only=True):
            for v in row:
                if v not in (None, ""):
                    partes.append(str(v))
    return _minerar_texto("\n".join(partes))


def _minerar_docx(docx_bytes):
    try:
        import docx
    except ImportError:
        return _minerar_texto("")
    try:
        doc = docx.Document(io.BytesIO(docx_bytes))
    except Exception:
        return _minerar_texto("")
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for row in tabela.rows:
            for cell in row.cells:
                partes.append(cell.text)
    return _minerar_texto("\n".join(partes))


def minerar_eep(eep_bytes, filename=""):
    """Detecta o formato pela extensao/assinatura e extrai os metadados do EEP."""
    nome_lower = (filename or "").lower()
    if nome_lower.endswith(".xlsx") or eep_bytes[:2] == b"PK" and nome_lower.endswith((".xlsx", ".docx")):
        if nome_lower.endswith(".docx"):
            dados = _minerar_docx(eep_bytes)
        else:
            dados = _minerar_xlsx(eep_bytes)
    elif nome_lower.endswith(".docx"):
        dados = _minerar_docx(eep_bytes)
    elif eep_bytes[:4] == b"%PDF":
        dados = _minerar_pdf(eep_bytes)
    else:
        dados = _minerar_pdf(eep_bytes)

    dados["nome"] = dados["nome"] or "Projeto sem nome identificado no EEP"
    dados["jira"] = dados["jira"] or "JIRA/IVR não identificado no EEP"
    dados["chaves"] = dados["chaves"] or []
    dados["vdns"] = dados["vdns"] or []
    dados["secoes"] = dados.get("secoes") or {}
    dados["campos"] = dados.get("campos") or {}
    return dados
