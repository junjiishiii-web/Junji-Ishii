"""
Suporte a leitura de SPEC direto de um link do Google Sheets, sem precisar
baixar/exportar manualmente antes de enviar pro app.

Funciona apenas com planilhas compartilhadas como "Qualquer pessoa com o
link pode ver" — nao ha OAuth aqui, entao planilhas restritas a pessoas
especificas nao sao acessiveis (o Google devolve uma pagina de login em vez
da planilha, o que a validacao de assinatura zip detecta e rejeita com uma
mensagem clara).
"""
import re
import urllib.error
import urllib.request

_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_SHEETS_ID_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)")


class GoogleSheetsError(Exception):
    pass


def extrair_id(url):
    m = _SHEETS_ID_RE.search(url or "")
    return m.group(1) if m else None


def baixar_como_xlsx(url, timeout=25):
    """Baixa uma planilha do Google Sheets publica como bytes .xlsx."""
    file_id = extrair_id(url)
    if not file_id:
        raise GoogleSheetsError(
            "Isso não parece um link de Google Sheets. Copie o link da barra de endereço "
            "com a planilha aberta (algo como docs.google.com/spreadsheets/d/.../edit)."
        )

    export_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
    req = urllib.request.Request(export_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            conteudo = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise GoogleSheetsError(
                "Essa planilha não está acessível publicamente. No Google Sheets, clique em "
                "\"Compartilhar\" e mude para \"Qualquer pessoa com o link\" (Leitor), depois "
                "tente de novo."
            ) from e
        raise GoogleSheetsError(f"O Google Sheets recusou o pedido (HTTP {e.code}).") from e
    except urllib.error.URLError as e:
        raise GoogleSheetsError(f"Não consegui acessar o Google Sheets: {e.reason}") from e

    if not conteudo.startswith(_ZIP_MAGIC):
        raise GoogleSheetsError(
            "O conteúdo baixado não é uma planilha válida — provavelmente essa planilha não "
            "está compartilhada como \"Qualquer pessoa com o link pode ver\", ou o link não é "
            "de uma Planilha Google (Google Sheets)."
        )

    return conteudo, file_id
