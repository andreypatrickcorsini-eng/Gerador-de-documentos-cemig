"""Modelos de documento: carregamento, validação e montagem dos blocos.

Os arquivos ``modelos/*.json`` descrevem tanto o formulário (lista de campos)
quanto o conteúdo do documento (lista de seções e blocos). Este módulo lê os
JSONs, valida os dados recebidos e produz uma representação intermediária —
uma lista de blocos tipados — que os renderizadores de DOCX e PDF desenham.

Blocos suportados
-----------------
``p``              parágrafo corrido (``texto``).
``lista``          lista marcada (``itens``).
``lista_campo``    lista marcada a partir de um campo multilinha.
``clausula``       parágrafo com título em negrito e texto justificado.
``tabela_campos``  tabela rótulo/valor; campos vazios são omitidos.
``tabela``         tabela genérica headless (``cabecalho`` + ``linhas``).
``condicional``    renderiza ``blocos`` apenas se ``campo`` estiver preenchido.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import util

DIR_MODELOS = Path(__file__).resolve().parent.parent / "modelos"

# Rótulos amigáveis para unidades usadas na formatação de números.
SUFIXOS = {
    "tensao_kv": " kV",
    "extensao_m": " m",
    "vao_m": " m",
    "altura_livre": " m",
    "postes": "",
    "prazo_dias": " dias",
    "area_m2": " m²",
    "area_ha": " ha",
    "prazo_recuperacao": " meses",
}

# Campos de CPF/CNPJ recebem validação de dígito verificador.
CAMPOS_DOCUMENTO = {"interessado_documento", "procurador_documento"}


class ModeloNaoEncontrado(Exception):
    """Modelo inexistente em ``modelos/``."""


class DadosInvalidos(Exception):
    """Dados do formulário reprovados na validação."""

    def __init__(self, erros: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in erros.items()))
        self.erros = erros


@dataclass
class Modelo:
    id: str
    nome: str
    descricao: str
    titulo_documento: str
    campos: list[dict[str, Any]]
    secoes: list[dict[str, Any]]
    bruto: dict[str, Any] = field(repr=False, default_factory=dict)

    # -- conveniências ----------------------------------------------------- #
    @property
    def icone(self) -> str:
        return self.bruto.get("icone", "📄")

    @property
    def subtitulo(self) -> str:
        return self.bruto.get("subtitulo", "")

    @property
    def encerramento(self) -> str:
        return self.bruto.get("encerramento", "")

    def campo(self, chave: str) -> dict[str, Any] | None:
        return next((c for c in self.campos if c["chave"] == chave), None)

    def grupos(self) -> list[str]:
        vistos: list[str] = []
        for campo in self.campos:
            grupo = campo.get("grupo", "Dados")
            if grupo not in vistos:
                vistos.append(grupo)
        return vistos

    def resumo(self) -> dict[str, Any]:
        """Metadados usados pela interface (sem o corpo do documento)."""
        return {
            "id": self.id,
            "nome": self.nome,
            "icone": self.icone,
            "descricao": self.descricao,
            "titulo_documento": self.titulo_documento,
            "subtitulo": self.subtitulo,
            "campos": self.campos,
            "grupos": self.grupos(),
        }


# --------------------------------------------------------------------------- #
# Carregamento
# --------------------------------------------------------------------------- #
def _caminho_modelo(modelo_id: str) -> Path:
    if not modelo_id or not modelo_id.replace("-", "").replace("_", "").isalnum():
        raise ModeloNaoEncontrado(modelo_id)
    return DIR_MODELOS / f"{modelo_id}.json"


def carregar_modelo(modelo_id: str) -> Modelo:
    caminho = _caminho_modelo(modelo_id)
    if not caminho.is_file():
        raise ModeloNaoEncontrado(modelo_id)
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return Modelo(
        id=bruto.get("id", modelo_id),
        nome=bruto.get("nome", modelo_id.title()),
        descricao=bruto.get("descricao", ""),
        titulo_documento=bruto.get("titulo_documento", "DOCUMENTO"),
        campos=bruto.get("campos", []),
        secoes=bruto.get("secoes", []),
        bruto=bruto,
    )


def listar_modelos() -> list[Modelo]:
    modelos = []
    for caminho in sorted(DIR_MODELOS.glob("*.json")):
        try:
            modelos.append(carregar_modelo(caminho.stem))
        except (json.JSONDecodeError, ModeloNaoEncontrado):
            continue
    return modelos


# --------------------------------------------------------------------------- #
# Normalização e validação
# --------------------------------------------------------------------------- #
def _sufixo(campo: dict[str, Any]) -> str:
    if campo.get("sufixo") is not None:
        return campo["sufixo"]
    return SUFIXOS.get(campo["chave"], "")


def _normalizar_campo(campo: dict[str, Any], valor: Any) -> str:
    """Devolve o valor já formatado para exibição no documento."""
    tipo = campo.get("tipo", "texto")
    if valor is None:
        return ""
    if not util.valor_preenchido(valor):
        return ""

    if tipo == "data":
        return util.formatar_data(valor)
    if tipo == "documento":
        return util.formatar_cpf_cnpj(str(valor))
    if tipo == "telefone":
        return util.formatar_telefone(str(valor))
    if tipo == "email":
        return str(valor).strip()
    if tipo == "numero":
        casas = campo.get("casas_decimais")
        if casas is None:
            casas = util.casas_decimais_do_valor(valor)
        texto = util.formatar_decimal(valor, casas=casas)
        return f"{texto}{_sufixo(campo)}" if texto else ""
    return util.limpar_espacos(str(valor))


def _campos_dependentes(modelo: Modelo, chave: str) -> list[str]:
    return [c["chave"] for c in modelo.campos if chave in (c.get("origem") or [])]


def _aplicar_padroes(modelo: Modelo, valores: dict[str, Any]) -> dict[str, Any]:
    """Preenche com o valor ``padrao`` do modelo os campos deixados em branco."""
    dados = dict(valores)
    for campo in modelo.campos:
        if util.valor_preenchido(dados.get(campo["chave"])):
            continue
        if campo.get("padrao") not in (None, ""):
            dados[campo["chave"]] = campo["padrao"]
    return dados


def _aplicar_calculos(modelo: Modelo, valores: dict[str, Any]) -> dict[str, Any]:
    """Preenche campos marcados com ``calculado`` quando vazios."""
    dados = dict(valores)
    for campo in modelo.campos:
        regra = campo.get("calculado")
        if not regra or util.valor_preenchido(dados.get(campo["chave"])):
            continue
        origem = [dados.get(chave) for chave in campo.get("origem", [])]
        if regra == "dias_entre":
            inicio, fim = util.para_data(origem[0]), util.para_data(origem[1])
            if inicio and fim:
                dados[campo["chave"]] = (fim - inicio).days
        elif regra == "m2_para_ha":
            numero = util.para_decimal(origem[0])
            if numero is not None:
                dados[campo["chave"]] = numero / 10000
    return dados


def dados_efetivos(modelo: Modelo, valores: dict[str, Any]) -> dict[str, Any]:
    """Aplica padrões e cálculos — o conjunto de dados que o documento verá."""
    return _aplicar_calculos(modelo, _aplicar_padroes(modelo, valores or {}))


def pendencias(modelo: Modelo, valores: dict[str, Any]) -> list[str]:
    """Campos obrigatórios ainda em branco (usado pela pré-visualização)."""
    dados = dados_efetivos(modelo, valores)
    return [campo["chave"] for campo in modelo.campos
            if campo.get("obrigatorio") and not util.valor_preenchido(dados.get(campo["chave"]))]


def _validar_data(campo: dict[str, Any], valor: Any) -> str | None:
    if not util.para_data(valor):
        return "Informe uma data válida (dd/mm/aaaa)."
    return None


def validar(modelo: Modelo, valores: dict[str, Any]) -> dict[str, str]:
    """Confere os dados do formulário e devolve ``{campo: mensagem}``."""
    erros: dict[str, str] = {}
    for campo in modelo.campos:
        chave, tipo = campo["chave"], campo.get("tipo", "texto")
        valor = valores.get(chave)

        if campo.get("obrigatorio") and not util.valor_preenchido(valor):
            erros[chave] = "Campo obrigatório."
            continue
        if not util.valor_preenchido(valor):
            continue

        if tipo == "data":
            mensagem = _validar_data(campo, valor)
            if mensagem:
                erros[chave] = mensagem

        elif tipo == "documento":
            digitos = util.apenas_digitos(str(valor))
            if len(digitos) == 11:
                if not util.validar_cpf(digitos):
                    erros[chave] = "CPF inválido — confira os dígitos."
            elif len(digitos) == 14:
                if not util.validar_cnpj(digitos):
                    erros[chave] = "CNPJ inválido — confira os dígitos."
            else:
                erros[chave] = "Informe um CPF (11 dígitos) ou CNPJ (14 dígitos)."

        elif tipo == "email":
            if not util.validar_email(str(valor)):
                erros[chave] = "E-mail inválido."

        elif tipo == "telefone":
            if len(util.apenas_digitos(str(valor))) not in (10, 11):
                erros[chave] = "Telefone deve ter DDD + 8 ou 9 dígitos."

        elif tipo == "numero":
            numero = util.para_decimal(valor)
            if numero is None:
                erros[chave] = "Informe um número."
            elif numero < 0 and not campo.get("permite_negativo"):
                erros[chave] = "O valor não pode ser negativo."

        elif tipo == "selecao":
            opcoes = campo.get("opcoes") or []
            if opcoes and str(valor).strip() not in opcoes:
                erros[chave] = "Selecione uma das opções disponíveis."

    # Coerência de datas
    inicio = util.para_data(valores.get("data_inicio"))
    fim = util.para_data(valores.get("data_conclusao"))
    if inicio and fim and fim < inicio:
        erros["data_conclusao"] = "A conclusão não pode ser anterior ao início."
    embargo = util.para_data(valores.get("data_embargo"))
    documento = util.para_data(valores.get("data_documento"))
    if embargo and documento and embargo > documento:
        erros["data_embargo"] = "O embargo não pode ser posterior ao requerimento."

    return erros


# --------------------------------------------------------------------------- #
# Interpolação de textos
# --------------------------------------------------------------------------- #
def _formatar_com_filtro(valor: Any, filtro: str, campo: dict[str, Any] | None) -> str:
    if valor is None or not util.valor_preenchido(valor):
        return ""
    if filtro in ("cpfcnpj", "documento"):
        return util.formatar_cpf_cnpj(str(valor))
    if filtro == "data":
        return util.formatar_data(valor)
    if filtro == "data_extenso":
        return util.data_extenso_curta(valor)
    if filtro in ("numero", "moeda", "decimal"):
        campo = campo or {}
        casas = campo.get("casas_decimais")
        if casas is None:
            casas = util.casas_decimais_do_valor(valor)
        texto = util.formatar_decimal(valor, casas=casas)
        if filtro == "moeda":
            return f"R$ {texto}"
        return texto
    if filtro == "maiusculo":
        return str(valor).upper()
    if filtro == "minusculo":
        # Baixa apenas a primeira letra — preserva nomes próprios e siglas:
        # "Intervenção em Área de Preservação Permanente — APP" vira
        # "intervenção em Área de Preservação Permanente — APP".
        texto = str(valor)
        return texto[:1].lower() + texto[1:]
    if filtro in ("titulo", "title"):
        return util.titulo_case(str(valor))
    if filtro == "extenso":
        return util.numero_por_extenso(valor)
    return str(valor)


def interpolar(texto: str, modelo: Modelo, valores: dict[str, Any], formatados: dict[str, str],
               marcador: str = "") -> str:
    """Substitui ``{{campo}}`` e ``{{campo|filtro}}`` no texto do modelo.

    ``marcador`` é usado no lugar de campos vazios — a pré-visualização mostra
    sublinhados onde falta informação, os documentos finais ficam limpos.
    """
    import re

    # Trechos condicionais primeiro: {{?campo}}texto{{/campo}} só aparecem
    # quando o campo tem conteúdo — evita vírgulas e "nº" soltos no documento.
    padrao_condicional = re.compile(r"\{\{\?(\w[\w-]*)\}\}(.*?)\{\{/\1\}\}", re.S)
    texto = padrao_condicional.sub(
        lambda m: m.group(2) if util.valor_preenchido(valores.get(m.group(1))) else "",
        texto or "",
    )

    def substituir(match: re.Match) -> str:
        expressao = match.group(1).strip()
        chave, _, filtro = expressao.partition("|")
        chave, filtro = chave.strip(), filtro.strip()
        campo = modelo.campo(chave)
        valor = valores.get(chave)
        # Só sinaliza na prévia o que é obrigatório; campos opcionais vazios
        # simplesmente desaparecem do texto, como no documento final.
        substituto = marcador if (campo or {}).get("obrigatorio") else ""
        if filtro:
            return _formatar_com_filtro(valor, filtro, campo) or substituto
        preenchido = formatados.get(chave, "")
        return preenchido if preenchido else substituto

    resultado = re.sub(r"\{\{(?!\?|/)(.+?)\}\}", substituir, texto or "")
    # Evita espaços duplos e " ," quando algum campo ficou vazio.
    if not marcador:
        resultado = re.sub(r"[ \t]{2,}", " ", resultado)
        resultado = re.sub(r"\s+([,.;:])", r"\1", resultado)
    return resultado.strip()


# --------------------------------------------------------------------------- #
# Montagem dos blocos
# --------------------------------------------------------------------------- #
@dataclass
class Bloco:
    tipo: str
    dados: dict[str, Any] = field(default_factory=dict)


@dataclass
class Secao:
    titulo: str
    blocos: list[Bloco] = field(default_factory=list)


@dataclass
class Documento:
    """Representação intermediária pronta para renderização."""

    modelo_id: str
    nome: str
    titulo: str
    subtitulo: str
    meta: dict[str, str]
    secoes: list[Secao]
    encerramento: str
    fecho: str
    assinaturas: list[dict[str, str]]
    nome_arquivo: str


def _rotulo(campo: dict[str, Any]) -> str:
    return campo.get("rotulo", campo["chave"])


def _montar_bloco(bloco_json: dict[str, Any], modelo: Modelo, valores: dict[str, Any],
                  formatados: dict[str, str], marcador: str = "") -> Bloco | None:
    tipo = bloco_json.get("tipo", "p")

    if tipo == "condicional":
        if not util.valor_preenchido(valores.get(bloco_json.get("campo", ""))):
            return None
        internos = [
            b for b in (_montar_bloco(b, modelo, valores, formatados, marcador)
                        for b in bloco_json.get("blocos", []))
            if b is not None
        ]
        if not internos:
            return None
        return Bloco("condicional", {
            "titulo": bloco_json.get("titulo", ""),
            "blocos": internos,
        })

    if tipo == "tabela_campos":
        linhas = []
        for chave in bloco_json.get("campos", []):
            campo = modelo.campo(chave)
            if campo is None:
                continue
            valor = formatados.get(chave, "")
            if not valor and not (marcador and campo.get("obrigatorio")):
                continue  # campos não preenchidos não aparecem no documento final
            linhas.append({"rotulo": _rotulo(campo), "valor": valor or marcador})
        if not linhas:
            return None
        return Bloco("tabela_campos", {"linhas": linhas})

    if tipo == "lista":
        itens = [interpolar(i, modelo, valores, formatados, marcador)
                          for i in bloco_json.get("itens", [])]
        itens = [i for i in itens if i]
        return Bloco("lista", {"itens": itens}) if itens else None

    if tipo == "lista_campo":
        chave = bloco_json.get("campo", "")
        bruto = str(valores.get(chave) or "")
        itens = [util.limpar_espacos(linha.lstrip("-•* ")) for linha in bruto.splitlines()]
        itens = [i for i in itens if i]
        return Bloco("lista", {"itens": itens}) if itens else None

    if tipo == "clausula":
        if bloco_json.get("condicao_campo") and not util.valor_preenchido(
                valores.get(bloco_json["condicao_campo"])):
            return None
        return Bloco("clausula", {
            "titulo": bloco_json.get("titulo", ""),
            "texto": interpolar(bloco_json.get("texto", ""), modelo, valores, formatados, marcador),
        })

    if tipo == "tabela":
        return Bloco("tabela", {
            "cabecalho": bloco_json.get("cabecalho", []),
            "linhas": bloco_json.get("linhas", []),
        })

    texto = interpolar(bloco_json.get("texto", ""), modelo, valores, formatados, marcador)
    if not texto:
        return None
    return Bloco("p", {"texto": texto, "estilo": bloco_json.get("estilo", "")})


def montar_documento(modelo: Modelo, valores: dict[str, Any],
                     validar_dados: bool = True, marcador_vazio: str = "") -> Documento:
    """Aplica cálculos, valida e devolve o documento pronto para render.

    Com ``validar_dados=False`` a montagem segue mesmo com campos obrigatórios
    vazios — usado pela pré-visualização em tempo real.
    """
    dados = dados_efetivos(modelo, valores)
    if validar_dados:
        erros = validar(modelo, dados)
        if erros:
            raise DadosInvalidos(erros)

    formatados = {c["chave"]: _normalizar_campo(c, dados.get(c["chave"])) for c in modelo.campos}

    secoes = []
    for secao_json in modelo.secoes:
        blocos = [
            b for b in (_montar_bloco(bj, modelo, dados, formatados, marcador_vazio)
                        for bj in secao_json.get("blocos", []))
            if b is not None
        ]
        if blocos:
            secoes.append(Secao(titulo=secao_json.get("titulo", ""), blocos=blocos))

    assinaturas = []
    for assinatura in modelo.bruto.get("assinaturas", []):
        assinaturas.append({
            "papel": interpolar(assinatura.get("papel", ""), modelo, dados, formatados, marcador_vazio),
            "nome": interpolar(assinatura.get("nome", ""), modelo, dados, formatados, marcador_vazio),
            "linha2": interpolar(assinatura.get("linha2", ""), modelo, dados, formatados, marcador_vazio),
        })

    meta = {}
    if formatados.get("protocolo"):
        meta["Protocolo"] = formatados["protocolo"]
    if formatados.get("data_documento"):
        meta["Data"] = formatados["data_documento"]

    identificacao = formatados.get("empreendimento") or formatados.get("interessado_nome")
    identificador = util.nome_arquivo_seguro(f"{modelo.nome}-{identificacao}")
    if formatados.get("protocolo"):
        identificador += "-" + util.nome_arquivo_seguro(formatados["protocolo"], 20)

    return Documento(
        modelo_id=modelo.id,
        nome=modelo.nome,
        titulo=modelo.titulo_documento,
        subtitulo=modelo.subtitulo,
        meta=meta,
        secoes=secoes,
        encerramento=interpolar(modelo.encerramento, modelo, dados, formatados, marcador_vazio),
        fecho=interpolar(modelo.bruto.get("fecho_local", ""), modelo, dados, formatados, marcador_vazio),
        assinaturas=assinaturas,
        nome_arquivo=identificador,
    )


def clonar(valores: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(valores or {}))


def ferramentas_frontend() -> dict[str, Any]:
    """Configurações que o formulário usa para máscaras e cálculos no navegador."""
    return {
        "sufixos": SUFIXOS,
        "campos_documento": sorted(CAMPOS_DOCUMENTO),
        "ufs": ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
                "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
                "SP", "SE", "TO"],
    }
