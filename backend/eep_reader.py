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
    # EEPs simples / modelos antigos ("1. OBJETIVO DO PROJETO:", "2. ESCOPO", "JUSTIFICATIVA"...)
    ("objetivo", r"objetivos?(?:\s+(?:do\s+projeto|geral|esperado|principal))?\s*:?\s*$"),
    ("escopo", r"escopo(?:\s+do\s+projeto)?\s*:?\s*$"),
    ("fora_escopo", r"(?:fora\s+(?:do\s+)?escopo|n[aã]o\s+escopo)\s*:?\s*$"),
    ("necessidade", r"(?:justificativa|motiva[cç][aã]o|contexto(?:\s+do\s+projeto)?|situa[cç][aã]o\s+atual)\s*:?\s*$"),
    ("solucao", r"(?:descri[cç][aã]o\s+do\s+projeto|solu[cç][aã]o\s+proposta)\s*:?\s*$"),
    ("regras", r"regras?\s*:?\s*$"),
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
            # o titulo pode vir numerado ("1.  OBJETIVO DO PROJETO:"): testa com e sem a numeracao
            sem_numero = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", l)
            for k, rx in _SECOES_EEP:
                if re.match(rx, l, re.IGNORECASE) or (sem_numero != l and re.match(rx, sem_numero, re.IGNORECASE)):
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


_ALVO_RE = re.compile(r"\b(?:target|vdn|id\s*(?:de\s*)?transfer\w*|destino|fila|skill)\b", re.IGNORECASE)


def _limpa(c):
    return re.sub(r"\s+", " ", str(c if c is not None else "")).strip()


def _cenarios_de_tabela(linhas):
    """Tabelas do EEP com uma coluna de TARGET/VDN/ID de transferencia: cada linha vira um cenario
    {cenario, alvo, campos:[(coluna, valor)]}. Celulas mescladas (Grupo/Criterio que valem para varias linhas)
    sao propagadas para as linhas seguintes."""
    linhas = [[_limpa(c) for c in l] for l in linhas if l]
    cab_idx = next((i for i, l in enumerate(linhas[:3]) if any(_ALVO_RE.fullmatch(c.strip(": ")) or _ALVO_RE.match(c) for c in l if c)), None)
    if cab_idx is None:
        return []
    cab = linhas[cab_idx]
    idx_alvo = next(i for i, c in enumerate(cab) if c and (_ALVO_RE.fullmatch(c.strip(": ")) or _ALVO_RE.match(c)))
    rotulo_alvo = cab[idx_alvo]
    # cabecalho pode ocupar 2 linhas ("Cliente Claro" / "Movel")
    rotulos = [c for c in cab if c]
    if cab_idx + 1 < len(linhas):
        extra = [c for c in linhas[cab_idx + 1] if c]
        if extra and not any(re.search(r"\d{4,}", c) for c in extra) and len(extra) <= 2:
            # junta a 2a linha de cabecalho ao rotulo anterior mais proximo
            for e in extra:
                for k, r in enumerate(rotulos):
                    if r.lower().endswith("claro"):
                        rotulos[k] = f"{r} {e}"
                        break
                else:
                    rotulos[-1] = f"{rotulos[-1]} {e}"
            dados = linhas[cab_idx + 2:]
        else:
            dados = linhas[cab_idx + 1:]
    else:
        dados = []
    ultimo = {}
    cenarios = []
    for l in dados:
        if not any(l):
            continue
        l = list(l) + [""] * (len(cab) - len(l))
        alvo = l[idx_alvo] if idx_alvo < len(l) else ""
        if not alvo:
            alvo = next((c for c in reversed(l) if c), "")
        if not re.search(r"\d{3,}", alvo):
            continue
        preenchida = []
        for i, c in enumerate(l):
            if c:
                ultimo[i] = c
                preenchida.append(c)
            elif i in ultimo and i < idx_alvo and any(l[j] for j in range(i + 1, len(l))):
                preenchida.append(ultimo[i])
        valores = preenchida
        if len(valores) != len(rotulos):
            rotulos_l = [f"Coluna {n + 1}" for n in range(len(valores))]
        else:
            rotulos_l = rotulos
        campos = [(r, v) for r, v in zip(rotulos_l, valores) if v and v != alvo]
        numero = valores[0] if valores and re.fullmatch(r"\d{1,3}", valores[0]) else str(len(cenarios) + 1)
        cenarios.append({"cenario": numero, "alvo": alvo, "rotulo_alvo": rotulo_alvo, "campos": campos})
    return cenarios if len(cenarios) >= 2 else []


def _cenarios_de_tabelas(tabelas):
    for tb in tabelas:
        cs = _cenarios_de_tabela(tb)
        if cs:
            return cs
    return []


def _tabelas_pdf(pdf_bytes):
    try:
        import pdfplumber

        saida = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                for tb in page.extract_tables():
                    saida.append(tb)
        return saida
    except Exception:
        return []


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
    indicadores = []
    for m_ind in re.finditer(r"indicadores?(?:\s+de\s+atendimento)?\s+((?:\d{1,3}\s*(?:,|/|e|ou)?\s*)+)", texto or "", re.IGNORECASE):
        for n in re.findall(r"\d{1,3}", m_ind.group(1)):
            if n not in indicadores:
                indicadores.append(n)

    return {
        "nome": nome_proj.group(1).strip() if nome_proj else None,
        "jira": jira_ivr.group(1).strip() if jira_ivr else None,
        "chaves": chaves_finais,
        "vdns": vdns_minados,
        "secoes": secoes,
        "campos": campos,
        "indicadores": indicadores,
    }


def _minerar_pdf(pdf_bytes):
    from pdfminer.high_level import extract_text

    try:
        texto = extract_text(io.BytesIO(pdf_bytes))
    except Exception:
        texto = ""
    dados = _minerar_texto(texto)
    dados["cenarios_transferencia"] = _cenarios_de_tabelas(_tabelas_pdf(pdf_bytes))
    return dados


def _minerar_xlsx(xlsx_bytes):
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    except Exception:
        return _minerar_texto("")
    partes, tabelas = [], []
    for aba in wb.sheetnames:
        ws = wb[aba]
        tabela = []
        for row in ws.iter_rows(values_only=True):
            tabela.append(list(row))
            for v in row:
                if v not in (None, ""):
                    partes.append(str(v))
        tabelas.append(tabela)
    dados = _minerar_texto("\n".join(partes))
    dados["cenarios_transferencia"] = _cenarios_de_tabelas(tabelas)
    return dados


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
    tabelas = []
    for tabela in doc.tables:
        linhas = []
        for row in tabela.rows:
            linhas.append([cell.text for cell in row.cells])
            for cell in row.cells:
                partes.append(cell.text)
        tabelas.append(linhas)
    dados = _minerar_texto("\n".join(partes))
    dados["cenarios_transferencia"] = _cenarios_de_tabelas(tabelas)
    return dados


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
    dados["cenarios_transferencia"] = dados.get("cenarios_transferencia") or []
    dados["secoes"] = dados.get("secoes") or {}
    dados["campos"] = dados.get("campos") or {}
    return dados
