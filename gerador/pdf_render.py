"""Renderizador de documentos em PDF (ReportLab).

O layout espelha o do Word: cabeçalho institucional, título centralizado,
tabelas rótulo/valor, cláusulas numeradas, assinaturas em duas colunas e rodapé
com numeração de páginas.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .modelos import Bloco, Documento

ASSETS = Path(__file__).resolve().parent.parent / "assets"

AZUL = colors.HexColor("#004C8C")
CINZA = colors.HexColor("#5A5A5A")
CINZA_BORDA = colors.HexColor("#BFBFBF")
CINZA_FUNDO = colors.HexColor("#F2F2F2")

_LOCAIS_FONTE = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("C:/Windows/Fonts"),
    ASSETS / "fonts",
]
_ARQUIVOS_FONTE = {
    "DocSans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    "DocSansFallback": ("arial.ttf", "arialbd.ttf"),
}


def _registrar_fontes() -> tuple[str, str]:
    """Registra uma fonte com suporte a acentos e devolve (normal, negrito)."""
    for nome, (arquivo_normal, arquivo_negrito) in _ARQUIVOS_FONTE.items():
        for pasta in _LOCAIS_FONTE:
            normal, negrito = pasta / arquivo_normal, pasta / arquivo_negrito
            if normal.is_file():
                try:
                    pdfmetrics.registerFont(TTFont(nome, str(normal)))
                    pdfmetrics.registerFont(TTFont(f"{nome}-Bold", str(negrito)
                                                   if negrito.is_file() else str(normal)))
                    pdfmetrics.registerFontFamily(
                        nome, normal=nome, bold=f"{nome}-Bold", italic=nome,
                        boldItalic=f"{nome}-Bold",
                    )
                    return nome, f"{nome}-Bold"
                except Exception:  # fonte corrompida ou formato inesperado
                    continue
    return "Helvetica", "Helvetica-Bold"


FONTE, FONTE_NEGRITO = _registrar_fontes()


def _estilos() -> dict[str, ParagraphStyle]:
    base = dict(fontName=FONTE, fontSize=10, leading=14.5, textColor=colors.black)
    return {
        "titulo": ParagraphStyle("titulo", fontName=FONTE_NEGRITO, fontSize=13.5,
                                 leading=18, alignment=TA_CENTER, textColor=AZUL,
                                 spaceAfter=2),
        "subtitulo": ParagraphStyle("subtitulo", fontName=FONTE, fontSize=8, leading=11,
                                    alignment=TA_CENTER, textColor=CINZA,
                                    spaceAfter=4),
        "secao": ParagraphStyle("secao", fontName=FONTE_NEGRITO, fontSize=10,
                                leading=13, textColor=AZUL, spaceBefore=12, spaceAfter=4,
                                keepWithNext=1),
        "clausula": ParagraphStyle("clausula", fontName=FONTE_NEGRITO, fontSize=9.5,
                                   leading=13, spaceBefore=9, spaceAfter=2,
                                   keepWithNext=1),
        "corpo": ParagraphStyle("corpo", alignment=TA_JUSTIFY, spaceAfter=6, **base),
        "direita": ParagraphStyle("direita", alignment=TA_RIGHT, spaceAfter=6, **base),
        "rotulo": ParagraphStyle("rotulo", fontName=FONTE_NEGRITO, fontSize=8.5,
                                 leading=11, textColor=CINZA),
        "valor": ParagraphStyle("valor", fontName=FONTE, fontSize=9.5, leading=12.5),
        "celula": ParagraphStyle("celula", fontName=FONTE, fontSize=8.5, leading=11),
        "celula_cab": ParagraphStyle("celula_cab", fontName=FONTE_NEGRITO, fontSize=8.5,
                                     leading=11),
        "assinatura_nome": ParagraphStyle("assinatura_nome", fontName=FONTE_NEGRITO,
                                          fontSize=9, leading=12, alignment=TA_CENTER),
        "assinatura_papel": ParagraphStyle("assinatura_papel", fontName=FONTE, fontSize=8,
                                           leading=11, alignment=TA_CENTER, textColor=CINZA),
    }


def _escapar(texto: str) -> str:
    return (str(texto or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


class _LinhaHorizontal(Flowable):
    """Linha fina usada sob os títulos e nas assinaturas."""

    def __init__(self, largura, cor=CINZA_BORDA, espessura=0.6, espaco_antes=0):
        super().__init__()
        self.largura, self.cor = largura, cor
        self.espessura, self.espaco_antes = espessura, espaco_antes
        self.height = espaco_antes + espessura

    def draw(self):
        self.canv.setStrokeColor(self.cor)
        self.canv.setLineWidth(self.espessura)
        self.canv.line(0, 0, self.largura, 0)

    def wrap(self, largura_disponivel, altura_disponivel):
        return largura_disponivel, self.height


class _DocumentoPDF(BaseDocTemplate):
    """Template com cabeçalho/rodapé desenhados em toda página."""

    # Margens da página (em cm): esquerda, direita, topo, base.
    MARGEM_ESQUERDA = 2.5
    MARGEM_DIREITA = 2.0
    MARGEM_TOPO = 3.6
    MARGEM_BASE = 2.2

    def __init__(self, buffer, doc: Documento, largura_util: float, **kwargs):
        super().__init__(buffer, pagesize=A4, **kwargs)
        self.doc_gerado = doc
        self.largura_util = largura_util
        largura_pagina, altura_pagina = A4
        esquerda = self.MARGEM_ESQUERDA * cm
        direita = self.MARGEM_DIREITA * cm
        topo = self.MARGEM_TOPO * cm
        base = self.MARGEM_BASE * cm
        frame = Frame(
            esquerda, base,
            width=largura_pagina - esquerda - direita,
            height=altura_pagina - topo - base,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id="corpo",
        )
        self.addPageTemplates([PageTemplate(id="principal", frames=[frame],
                                            onPage=self._desenhar_pagina)])

    def _desenhar_pagina(self, canvas, doc):
        canvas.saveState()
        largura, altura = A4
        esquerda, direita = 2.5 * cm, 2.0 * cm

        # Cabeçalho: ocupa a faixa de 1,5 cm a 3,0 cm do topo da página.
        base_logo = altura - 2.55 * cm
        base_texto = altura - 2.3 * cm
        regua = altura - 3.05 * cm

        logo = next((p for p in (ASSETS / "logo.png", ASSETS / "logo.jpg") if p.is_file()), None)
        if logo:
            try:
                from reportlab.lib.utils import ImageReader
                imagem = ImageReader(str(logo))
                largura_img, altura_img = imagem.getSize()
                altura_logo = 1.0 * cm
                canvas.drawImage(str(logo), esquerda, base_logo,
                                 width=largura_img * (altura_logo / altura_img),
                                 height=altura_logo, mask="auto")
            except Exception:
                logo = None
        if not logo:
            canvas.setFillColor(AZUL)
            canvas.setFont(FONTE_NEGRITO, 16)
            canvas.drawString(esquerda, base_texto, "CEMIG")
            canvas.setFillColor(CINZA)
            canvas.setFont(FONTE, 8)
            canvas.drawString(esquerda + 3.1 * cm, base_texto,
                              "Companhia Energética de Minas Gerais")

        # Metadados à direita
        if self.doc_gerado.meta:
            canvas.setFillColor(CINZA)
            canvas.setFont(FONTE, 7.5)
            texto_meta = "   |   ".join(f"{k}: {v}" for k, v in self.doc_gerado.meta.items())
            canvas.drawRightString(largura - direita, base_texto, texto_meta)

        canvas.setStrokeColor(AZUL)
        canvas.setLineWidth(1.1)
        canvas.line(esquerda, regua, largura - direita, regua)

        # Rodapé
        canvas.setStrokeColor(CINZA_BORDA)
        canvas.setLineWidth(0.5)
        canvas.line(esquerda, 1.75 * cm, largura - direita, 1.75 * cm)
        canvas.setFillColor(CINZA)
        canvas.setFont(FONTE, 7)
        canvas.drawString(esquerda, 1.35 * cm,
                          f"CEMIG · Gerador de Documentos — {self.doc_gerado.nome}")
        canvas.drawRightString(largura - direita, 1.35 * cm,
                               f"página {doc.page}")
        canvas.restoreState()


# --------------------------------------------------------------------------- #
# Blocos
# --------------------------------------------------------------------------- #
def _tabela_campos(linhas: list[dict[str, str]], estilos, largura_util: float):
    dados = [[Paragraph(_escapar(linha["rotulo"]), estilos["rotulo"]),
              Paragraph(_escapar(linha["valor"]), estilos["valor"])] for linha in linhas]
    tabela = Table(dados, colWidths=[largura_util * 0.30, largura_util * 0.70])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), CINZA_FUNDO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, CINZA_BORDA),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, CINZA_BORDA),
        ("BOX", (0, 0), (-1, -1), 0.4, CINZA_BORDA),
    ]))
    return tabela


def _tabela_generica(cabecalho: list[str], linhas: list[list[str]], estilos, largura_util: float):
    total_colunas = max([len(cabecalho)] + [len(linha) for linha in linhas] or [1]) or 1
    largura_coluna = largura_util / total_colunas
    dados = []
    if cabecalho:
        dados.append([Paragraph(_escapar(c), estilos["celula_cab"]) for c in cabecalho])
    for linha in linhas:
        dados.append([Paragraph(_escapar(v), estilos["celula"]) for v in linha])
    tabela = Table(dados, colWidths=[largura_coluna] * total_colunas, repeatRows=1 if cabecalho else 0)
    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, CINZA_BORDA),
        ("BACKGROUND", (0, 0), (-1, 0), CINZA_FUNDO) if cabecalho else ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabela


def _bloco_lista(itens: list[str], estilos, largura_util: float):
    marcador = ParagraphStyle("marcador", parent=estilos["corpo"], leftIndent=14,
                              bulletIndent=2, spaceAfter=3)
    return [Paragraph(_escapar(item), marcador, bulletText="•") for item in itens]


def _tabela_assinaturas(assinaturas: list[dict[str, str]], estilos, largura_util: float):
    partes = []
    por_linha = 2
    for indice in range(0, len(assinaturas), por_linha):
        grupo = assinaturas[indice:indice + por_linha]
        celulas = []
        for assinatura in grupo:
            conteudo = [
                Spacer(1, 26),
                _LinhaHorizontal(largura_util * 0.42, colors.HexColor("#8C8C8C"), 0.7),
            ]
            if assinatura.get("nome"):
                conteudo.append(Paragraph(_escapar(assinatura["nome"]), estilos["assinatura_nome"]))
            conteudo.append(Paragraph(_escapar(assinatura.get("papel", "")), estilos["assinatura_papel"]))
            if assinatura.get("linha2"):
                conteudo.append(Paragraph(_escapar(assinatura["linha2"]), estilos["assinatura_papel"]))
            celulas.append(conteudo)
        while len(celulas) < por_linha:
            celulas.append("")
        partes.append(Table([celulas], colWidths=[largura_util / por_linha] * por_linha,
                            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                              ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)])))
        partes.append(Spacer(1, 10))
    return partes


def _render_blocos(blocos: list[Bloco], estilos, largura_util: float) -> list:
    fluxo: list = []
    for bloco in blocos:
        if bloco.tipo == "condicional":
            titulo = bloco.dados.get("titulo", "")
            if titulo:
                fluxo.append(Paragraph(_escapar(titulo.upper()), estilos["secao"]))
            fluxo.extend(_render_blocos(bloco.dados.get("blocos", []), estilos, largura_util))
        elif bloco.tipo == "p":
            fluxo.append(Paragraph(_escapar(bloco.dados["texto"]), estilos["corpo"]))
        elif bloco.tipo == "lista":
            fluxo.extend(_bloco_lista(bloco.dados["itens"], estilos, largura_util))
            fluxo.append(Spacer(1, 4))
        elif bloco.tipo == "clausula":
            titulo = bloco.dados.get("titulo", "")
            texto = bloco.dados.get("texto", "")
            if titulo:
                fluxo.append(Paragraph(_escapar(titulo.upper()), estilos["clausula"]))
            if texto:
                fluxo.append(Paragraph(_escapar(texto), estilos["corpo"]))
        elif bloco.tipo == "tabela_campos":
            fluxo.append(_tabela_campos(bloco.dados["linhas"], estilos, largura_util))
            fluxo.append(Spacer(1, 8))
        elif bloco.tipo == "tabela":
            fluxo.append(_tabela_generica(bloco.dados.get("cabecalho", []),
                                          bloco.dados.get("linhas", []), estilos, largura_util))
            fluxo.append(Spacer(1, 8))
    return fluxo


# --------------------------------------------------------------------------- #
# Ponto de entrada
# --------------------------------------------------------------------------- #
def renderizar(doc: Documento) -> bytes:
    buffer = BytesIO()
    largura, _ = A4
    largura_util = largura - 4.5 * cm
    estilos = _estilos()

    pdf = _DocumentoPDF(
        buffer, doc, largura_util,
        title=doc.titulo, author="CEMIG — Companhia Energética de Minas Gerais",
        subject=f"{doc.nome} — documento gerado automaticamente",
        creator="Gerador de Documentos CEMIG",
    )

    fluxo: list = [Spacer(1, 2), Paragraph(_escapar(doc.titulo), estilos["titulo"])]
    if doc.subtitulo:
        fluxo.append(Paragraph(_escapar(doc.subtitulo), estilos["subtitulo"]))
    fluxo.append(_LinhaHorizontal(largura_util, CINZA_BORDA, 0.5, espaco_antes=2))
    fluxo.append(Spacer(1, 6))

    for secao in doc.secoes:
        if secao.titulo:
            fluxo.append(Paragraph(_escapar(secao.titulo.upper()), estilos["secao"]))
        fluxo.extend(_render_blocos(secao.blocos, estilos, largura_util))

    if doc.encerramento:
        fluxo.append(Spacer(1, 8))
        fluxo.append(Paragraph(_escapar(doc.encerramento), estilos["corpo"]))

    if doc.fecho:
        fluxo.append(Spacer(1, 10))
        fluxo.append(Paragraph(_escapar(doc.fecho), estilos["direita"]))

    if doc.assinaturas:
        fluxo.append(Spacer(1, 14))
        fluxo.extend(_tabela_assinaturas(doc.assinaturas, estilos, largura_util))

    rodape = ParagraphStyle("rodape", fontName=FONTE, fontSize=6.8, leading=9,
                            alignment=TA_CENTER, textColor=CINZA)
    fluxo.append(Spacer(1, 10))
    fluxo.append(_LinhaHorizontal(largura_util, CINZA_BORDA, 0.4))
    fluxo.append(Paragraph(
        f"Documento gerado pelo Gerador de Documentos CEMIG em "
        f"{date.today().strftime('%d/%m/%Y')} · modelo: {_escapar(doc.nome)}", rodape))

    pdf.build(fluxo)
    return buffer.getvalue()
