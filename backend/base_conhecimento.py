"""
Base de conhecimento da massa de testes (Atendimento CRN) — vem da planilha "Documentação importante" da squad:
codigos de Segmento, Status do Contrato, Status de identificacao, forma de pagamento, Status da Fatura e Status de VT
que o servico de identificacao (Identificar Contrato) devolve. Usada para dizer, em cada CT, QUAL massa o cliente precisa ter.

Regra da squad: estado ou chave com "CM" no nome = cliente ComboMulti.
"""
import re

SEGMENTOS = {
    "BLACK": 1, "BLUE": 2, "RED": 3, "WHITE": 4, "SEM SEGMENTO (BSDO)": 5, "PME": 6, "BLACK VIP": 7, "BLACK JOVEM": 8,
    "JOVEM": 9, "NETCLARO (CM)": 10, "COMBOMULTI3G (CM)": 13, "COMBOMULTI_PME (CM)": 14, "PME_SLA": 15,
    "PURPLE_PME_PF_SLA (CM)": 16, "GREY": 17, "OTHERSEGMENTO": 0,
}
SEGMENTOS_CM_TXT = ("cliente ComboMulti (CM): possui produto(s) Residencial (Internet, TV...) E também uma linha de celular — "
                    "segmento 10 (NETCLARO); também são CM: 13 (COMBOMULTI3G), 14 (COMBOMULTI_PME) e 16 (PURPLE_PME_PF_SLA)")
PRODUTOS_CM_TXT = "possuir produto Residencial (Internet / TV / ...) E linha de celular (cliente ComboMulti)"

# Projetos cujo proprio escopo exige cliente CM (ex.: ativacao de chip Claro Multi)
RX_PROJETO_CM = re.compile(r"ativa[cç][aã]o\s+de\s+chip|ativacao_?chip|chip[\s_]*cm\b|combo\s*multi|claro\s*multi", re.IGNORECASE)


def projeto_exige_cm(*textos):
    return any(RX_PROJETO_CM.search(str(t or "")) or eh_cm(t) for t in textos)


SEGMENTOS_NAO_CM_TXT = "NÃO é ComboMulti (segmento diferente de 10, 13, 14 e 16)"

# (padrao no texto da condicao, descricao do segmento com o codigo)
SEGMENTOS_POR_TEXTO = (
    (r"black\s*vip", "BLACK VIP = segmento 7"),
    (r"black\s*jovem", "BLACK JOVEM = segmento 8 (não usado mais)"),
    (r"\bblack\b", "BLACK = segmento 1"),
    (r"\bblue\b", "BLUE = segmento 2"),
    (r"\bred\b", "RED = segmento 3"),
    (r"\bwhite\b", "WHITE = segmento 4"),
    (r"sem segmento|\bbsdo\b", "SEM SEGMENTO (BSDO) = segmento 5"),
    (r"pme[\s_]*sla", "PME_SLA = segmento 15"),
    (r"\bpme\b", "PME = segmento 6"),
    (r"\bjovem\b", "JOVEM = segmento 9"),
    (r"\bgrey\b", "GREY = segmento 17"),
)

STATUS_CONTRATO_CONECTADO = "1 (CONECTADO)"
STATUS_CONTRATO_POR_TEXTO = (
    (r"inadimpl\w*\s+total", "23 (DESCONECTADO INADIMPLÊNCIA TOTAL)"),
    (r"inadimpl\w*\s+bt\b", "32 (DESCONECTADO INADIMPLÊNCIA BT)"),
    (r"inadimpl\w*\s+bp\b", "34 (DESCONECTADO INADIMPLÊNCIA BP)"),
    (r"desconect\w*|inadimpl\w*", "29 (DESCONECTADO INADIMPLÊNCIA) — variantes: 23 total, 32 BT, 34 BP"),
    (r"desabilitad\w*\s+parcial|parcialmente\s+desabilit\w*", "36 (DESABILITADO PARCIAL) — variantes: 35, 37, 41, 26"),
    (r"desabilit\w*", "24 (DESABILITADO)"),
)

IDENTIFICACAO_NAO = "1 (NÃO IDENTIFICADO — CustomerContract e IdentificarContrato falham)"
IDENTIFICACAO_SIM = "4 (IDENTIFICADO — CustomerContract e Orquestração obrigatória Topo com sucesso); 5 se pela contingência (IdentificarContrato)"

PAGAMENTO_POR_TEXTO = (
    (r"d[eé]bito\s+folha", "5 (DEBITO FOLHA)"),
    (r"d[eé]bito\s+(?:em\s+conta|autom[aá]tico)", "2 (DEBITO EM CONTA)"),
    (r"cart[aã]o\s+de\s+cr[eé]dito", "3 (CARTÃO DE CRÉDITO)"),
    (r"local\s+caixa", "4 (LOCAL CAIXA)"),
    (r"boleto", "1 (BOLETO)"),
)

FATURA_POR_TEXTO = (
    (r"fatura\s+(?:em\s+aberto)|em\s+aberto", "1 (EM ABERTO)"),
    (r"fatura\s+paga|\bpaga\b", "2 (PAGA)"),
    (r"fatura\s+cancelada", "3 (FATURA CANCELADA)"),
)

VT_POR_TEXTO = (
    (r"reagendad\w*", "R (REAGENDADA)"),
    (r"agendad\w*", "A (AGENDADA)"),
    (r"criad\w*", "C (CRIADA)"),
    (r"despachad\w*", "D (DESPACHADA)"),
    (r"executad\w*", "E (EXECUTADA)"),
    (r"cancelad\w*", "X (CANCELADA)"),
)

# "CM" no NOME de estado/chave (ChuteAtivacaoChip_CM, MenuPrincipal_CM, CM_Algo) ou a palavra ComboMulti / Claro Multi
RX_NOME_CM = re.compile(r"_CM(?![A-Za-z])|(?<![A-Za-z])CM_|(?<![A-Za-z])CM(?![A-Za-z])|combo\s*multi|claro\s*multi", re.IGNORECASE)
RX_NOME_CM_SENSIVEL = re.compile(r"_CM(?![A-Za-z])|(?<![A-Za-z])CM_|(?<![A-Za-z])CM(?![A-Za-z])")
RX_NAO_CM = re.compile(r"n[aã]o\s+(?:[eé]\s+)?(?:cliente\s+)?(?:combo\s*multi|cm\b)|combo\s*multi\s*=\s*n[aã]o", re.IGNORECASE)


def eh_cm(texto):
    """True se o texto (nome de estado/chave ou condicao) indica cliente ComboMulti."""
    t = str(texto or "")
    return bool(RX_NOME_CM_SENSIVEL.search(t) or re.search(r"combo\s*multi|claro\s*multi", t, re.IGNORECASE))
