"""Formatação, validação e conversão de valores para documentos."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

_UNIDADES = (
    "zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito",
    "nove", "dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis",
    "dezessete", "dezoito", "dezenove",
)
_DEZENAS = (
    "", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta",
    "oitenta", "noventa",
)
_CENTENAS = (
    "", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
    "seiscentos", "setecentos", "oitocentos", "novecentos",
)


# --------------------------------------------------------------------------- #
# Texto
# --------------------------------------------------------------------------- #
def sem_acento(texto: str) -> str:
    """Remove acentos preservando as letras."""
    normalizado = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def limpar_espacos(texto: str) -> str:
    return re.sub(r"[ \t]+", " ", (texto or "").replace("\xa0", " ")).strip()


def nome_arquivo_seguro(texto: str, limite: int = 60) -> str:
    """Converte um texto livre em trecho seguro para nome de arquivo."""
    base = sem_acento(texto or "").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return (base[:limite].strip("-") or "documento")


def titulo_case(texto: str) -> str:
    """Coloca em Caixa Alta as iniciais, preservando conectivos."""
    minusculas = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "para", "com"}
    palavras = []
    for i, palavra in enumerate((texto or "").split()):
        baixa = palavra.lower()
        if i and baixa in minusculas:
            palavras.append(baixa)
        else:
            palavras.append(baixa[:1].upper() + baixa[1:])
    return " ".join(palavras)


def apenas_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


# --------------------------------------------------------------------------- #
# Documentos (CPF / CNPJ)
# --------------------------------------------------------------------------- #
def formatar_cpf(valor: str) -> str:
    d = apenas_digitos(valor)
    if len(d) != 11:
        return (valor or "").strip()
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def formatar_cnpj(valor: str) -> str:
    d = apenas_digitos(valor)
    if len(d) != 14:
        return (valor or "").strip()
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def formatar_cpf_cnpj(valor: str) -> str:
    d = apenas_digitos(valor)
    if len(d) == 11:
        return formatar_cpf(d)
    if len(d) == 14:
        return formatar_cnpj(d)
    return (valor or "").strip()


def validar_cpf(valor: str) -> bool:
    d = apenas_digitos(valor)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if digito != int(d[tamanho]):
            return False
    return True


def validar_cnpj(valor: str) -> bool:
    d = apenas_digitos(valor)
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    pesos2 = (6,) + pesos1
    for pesos, posicao in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(d[i]) * pesos[i] for i in range(posicao))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(d[posicao]):
            return False
    return True


def formatar_telefone(valor: str) -> str:
    d = apenas_digitos(valor)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return (valor or "").strip()


# --------------------------------------------------------------------------- #
# Números e moeda
# --------------------------------------------------------------------------- #
def para_decimal(valor) -> Decimal | None:
    """Converte texto digitado no padrão brasileiro em Decimal.

    Aceita ``1.234,56``, ``1234,56``, ``1234.56``, ``R$ 1.234,56`` e ``1e3``.
    Devolve ``None`` quando não é possível interpretar.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))

    texto = str(valor).strip().replace("R$", "").replace(" ", "").replace("\xa0", "")
    if not texto:
        return None
    if "," in texto and "." in texto:
        # O separador que aparece por último é o decimal.
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def formatar_decimal(valor, casas: int = 2, agrupar: bool = True) -> str:
    numero = para_decimal(valor)
    if numero is None:
        return ""
    quantizado = numero.quantize(Decimal(10) ** -casas, rounding=ROUND_HALF_UP)
    texto = f"{quantizado:,.{casas}f}"
    if agrupar:
        return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return texto.replace(".", ",")


def casas_decimais_do_valor(valor, maximo: int = 6) -> int:
    """Quantas casas decimais o número realmente precisa (12.5 → 1, 12.50 → 1)."""
    numero = para_decimal(valor)
    if numero is None:
        return 0
    expoente = numero.normalize().as_tuple().exponent
    return max(0, min(-int(expoente), maximo))


def formatar_moeda(valor) -> str:
    texto = formatar_decimal(valor, 2)
    return f"R$ {texto}" if texto else ""


def metros_quadrados_para_hectares(valor) -> str:
    numero = para_decimal(valor)
    if numero is None:
        return ""
    return formatar_decimal(numero / Decimal(10000), 4)


# --------------------------------------------------------------------------- #
# Datas
# --------------------------------------------------------------------------- #
def para_data(valor) -> date | None:
    """Interpreta ``AAAA-MM-DD``, ``DD/MM/AAAA`` e ``DD/MM/AA``."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = (valor or "").strip()
    if not texto:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def formatar_data(valor, formato: str = "%d/%m/%Y") -> str:
    data = para_data(valor)
    return data.strftime(formato) if data else (str(valor).strip() if valor else "")


def _extenso_ate_999(numero: int) -> str:
    if numero == 0:
        return "zero"
    if numero == 100:
        return "cem"
    partes = []
    centena, resto = divmod(numero, 100)
    if centena:
        partes.append(_CENTENAS[centena])
    if resto:
        if resto < 20:
            partes.append(_UNIDADES[resto])
        else:
            dezena, unidade = divmod(resto, 10)
            partes.append(_DEZENAS[dezena] + (" e " + _UNIDADES[unidade] if unidade else ""))
    return " e ".join(partes)


def numero_por_extenso(valor) -> str:
    """Escreve um inteiro em português (até 999.999.999)."""
    numero = int(para_decimal(valor) or 0)
    if numero < 0:
        return "menos " + numero_por_extenso(-numero)
    if numero == 0:
        return "zero"
    if numero < 1000:
        return _extenso_ate_999(numero)

    milhar, resto = divmod(numero, 1000)
    if milhar == 1:
        texto = "mil"
    elif milhar < 1000:
        texto = _extenso_ate_999(milhar) + " mil"
    else:
        milhoes, milhar_resto = divmod(milhar, 1000)
        texto = _extenso_ate_999(milhoes) + (" milhão" if milhoes == 1 else " milhões")
        if milhar_resto:
            texto += " " + _extenso_ate_999(milhar_resto) + " mil"

    if resto:
        conector = " e " if resto < 100 or resto % 100 == 0 else " "
        texto += conector + _extenso_ate_999(resto)
    return texto


def data_por_extenso(valor) -> str:
    """Devolve ``aos três dias do mês de novembro de dois mil e vinte e seis``."""
    data = para_data(valor)
    if not data:
        return formatar_data(valor)
    return (
        f"aos {numero_por_extenso(data.day)} dias do mês de "
        f"{MESES[data.month - 1]} de {numero_por_extenso(data.year)}"
    )


def data_extenso_curta(valor) -> str:
    """Devolve ``3 de novembro de 2026``."""
    data = para_data(valor)
    if not data:
        return formatar_data(valor)
    return f"{data.day} de {MESES[data.month - 1]} de {data.year}"


# --------------------------------------------------------------------------- #
# Validações simples
# --------------------------------------------------------------------------- #
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def validar_email(valor: str) -> bool:
    return bool(_RE_EMAIL.match((valor or "").strip()))


def valor_preenchido(valor) -> bool:
    if valor is None:
        return False
    if isinstance(valor, str):
        return bool(valor.strip())
    if isinstance(valor, (list, tuple, dict, set)):
        return len(valor) > 0
    return True
