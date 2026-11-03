"""Renderizador de documentos em Word (.docx)."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .modelos import Bloco, Documento

ASSETS = Path(__file__).resolve().parent.parent / "assets"

AZUL = RGBColor(0x00, 0x4C, 0x8C)
CINZA = RGBColor(0x5A, 0x5A, 0x5A)
CINZA_CLARO = "D9D9D9"
CINZA_BORDA = "BFBFBF"


# --------------------------------------------------------------------------- #
# Auxiliares de baixo nível
# --------------------------------------------------------------------------- #
def _ajustar_fonte(run, nome="Arial", tamanho=None, negrito=None, italico=None, cor=None):
    run.font.name = nome
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for atributo in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(atributo), nome)
    if tamanho is not None:
        run.font.size = Pt(tamanho)
    if negrito is not None:
        run.bold = negrito
    if italico is not None:
        run.italic = italico
    if cor is not None:
        run.font.color.rgb = cor


def _borda(paragrafo, posicao="bottom", cor=CINZA_BORDA, tamanho=6, espaco=2):
    """Desenha uma linha no parágrafo (usada para títulos de seção e cabeçalho)."""
    ppr = paragrafo._p.get_or_add_pPr()
    bordas = ppr.find(qn("w:pBdr"))
    if bordas is None:
        bordas = OxmlElement("w:pBdr")
        ppr.append(bordas)
    elemento = OxmlElement(f"w:{posicao}")
    elemento.set(qn("w:val"), "single")
    elemento.set(qn("w:sz"), str(tamanho))
    elemento.set(qn("w:space"), str(espaco))
    elemento.set(qn("w:color"), cor)
    bordas.append(elemento)


def _borda_celula(celula, cor=CINZA_BORDA, tamanho=4, lados=("top", "bottom")):
    tcpr = celula._tc.get_or_add_tcPr()
    bordas = tcpr.find(qn("w:tcBorders"))
    if bordas is None:
        bordas = OxmlElement("w:tcBorders")
        tcpr.append(bordas)
    for lado in lados:
        elemento = OxmlElement(f"w:{lado}")
        elemento.set(qn("w:val"), "single")
        elemento.set(qn("w:sz"), str(tamanho))
        elemento.set(qn("w:space"), "0")
        elemento.set(qn("w:color"), cor)
        bordas.append(elemento)


def _sem_bordas(tabela):
    tbl_pr = tabela._tbl.tblPr
    bordas = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        elemento = OxmlElement(f"w:{lado}")
        elemento.set(qn("w:val"), "none")
        bordas.append(elemento)
    tbl_pr.append(bordas)


def _sombra_celula(celula, cor="F2F2F2"):
    tcpr = celula._tc.get_or_add_tcPr()
    sombra = OxmlElement("w:shd")
    sombra.set(qn("w:val"), "clear")
    sombra.set(qn("w:color"), "auto")
    sombra.set(qn("w:fill"), cor)
    tcpr.append(sombra)


def _espacamento(paragrafo, antes=0, depois=6, entrelinha=1.15):
    formato = paragrafo.paragraph_format
    formato.space_before = Pt(antes)
    formato.space_after = Pt(depois)
    formato.line_spacing = entrelinha


def _campo(paragrafo, instrucao: str):
    """Insere um campo do Word (ex.: PAGE, NUMPAGES)."""
    run = paragrafo.add_run()
    inicio = OxmlElement("w:fldChar")
    inicio.set(qn("w:fldCharType"), "begin")
    texto = OxmlElement("w:instrText")
    texto.set(qn("xml:space"), "preserve")
    texto.text = instrucao
    fim = OxmlElement("w:fldChar")
    fim.set(qn("w:fldCharType"), "end")
    run._r.append(inicio)
    run._r.append(texto)
    run._r.append(fim)
    return run


def _repetir_cabecalho(linha):
    tr_pr = linha._tr.get_or_add_trPr()
    cabecalho = OxmlElement("w:tblHeader")
    cabecalho.set(qn("w:val"), "true")
    tr_pr.append(cabecalho)


# --------------------------------------------------------------------------- #
# Cabeçalho, rodapé e capa
# --------------------------------------------------------------------------- #
def _montar_cabecalho(secao, doc: Documento):
    cabecalho = secao.header
    paragrafo = cabecalho.paragraphs[0]
    paragrafo.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _espacamento(paragrafo, antes=0, depois=0)

    logo = next((p for p in (ASSETS / "logo.png", ASSETS / "logo.jpg") if p.is_file()), None)
    if logo:
        run = paragrafo.add_run()
        run.add_picture(str(logo), height=Cm(1.15))
    else:
        run = paragrafo.add_run("CEMIG")
        _ajustar_fonte(run, tamanho=18, negrito=True, cor=AZUL)
        run = paragrafo.add_run("   Companhia Energética de Minas Gerais")
        _ajustar_fonte(run, tamanho=9, cor=CINZA)
    _borda(paragrafo, "bottom", cor="004C8C", tamanho=8, espaco=4)

    if doc.meta:
        linha_meta = cabecalho.add_paragraph()
        linha_meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _espacamento(linha_meta, antes=2, depois=0)
        texto = "   |   ".join(f"{chave}: {valor}" for chave, valor in doc.meta.items())
        run = linha_meta.add_run(texto)
        _ajustar_fonte(run, tamanho=8, cor=CINZA)


def _montar_rodape(secao, doc: Documento):
    rodape = secao.footer
    paragrafo = rodape.paragraphs[0]
    paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _espacamento(paragrafo, antes=0, depois=0)

    run = paragrafo.add_run(f"CEMIG · Gerador de Documentos — {doc.nome}  ·  página ")
    _ajustar_fonte(run, tamanho=7.5, cor=CINZA)
    run = _campo(paragrafo, "PAGE")
    _ajustar_fonte(run, tamanho=7.5, cor=CINZA)
    run = paragrafo.add_run(" de ")
    _ajustar_fonte(run, tamanho=7.5, cor=CINZA)
    run = _campo(paragrafo, "NUMPAGES")
    _ajustar_fonte(run, tamanho=7.5, cor=CINZA)


def _montar_titulo(docx: DocxDocument, doc: Documento):
    paragrafo = docx.add_paragraph()
    paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _espacamento(paragrafo, antes=10, depois=2)
    run = paragrafo.add_run(doc.titulo)
    _ajustar_fonte(run, tamanho=14, negrito=True, cor=AZUL)

    if doc.subtitulo:
        paragrafo = docx.add_paragraph()
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _espacamento(paragrafo, antes=0, depois=4)
        run = paragrafo.add_run(doc.subtitulo)
        _ajustar_fonte(run, tamanho=8.5, italico=True, cor=CINZA)
        _borda(paragrafo, "bottom", cor=CINZA_BORDA, tamanho=4, espaco=6)


# --------------------------------------------------------------------------- #
# Blocos
# --------------------------------------------------------------------------- #
def _paragrafo(docx: DocxDocument, texto: str, *, alinhamento=WD_ALIGN_PARAGRAPH.JUSTIFY,
               tamanho=10.5, negrito=False, italico=False, cor=None,
               antes=0, depois=6, indentacao=None):
    paragrafo = docx.add_paragraph()
    paragrafo.alignment = alinhamento
    _espacamento(paragrafo, antes=antes, depois=depois)
    if indentacao is not None:
        paragrafo.paragraph_format.left_indent = Cm(indentacao)
    run = paragrafo.add_run(texto)
    _ajustar_fonte(run, tamanho=tamanho, negrito=negrito, italico=italico, cor=cor)
    return paragrafo


def _titulo_secao(docx: DocxDocument, titulo: str):
    if not titulo:
        return
    paragrafo = docx.add_paragraph()
    paragrafo.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _espacamento(paragrafo, antes=14, depois=6)
    paragrafo.paragraph_format.keep_with_next = True
    run = paragrafo.add_run(titulo.upper())
    _ajustar_fonte(run, tamanho=10.5, negrito=True, cor=AZUL)
    _borda(paragrafo, "bottom", cor=CINZA_BORDA, tamanho=4, espaco=3)


def _render_lista(docx: DocxDocument, itens: list[str]):
    for item in itens:
        paragrafo = docx.add_paragraph()
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _espacamento(paragrafo, antes=0, depois=3)
        formato = paragrafo.paragraph_format
        formato.left_indent = Cm(0.9)
        formato.first_line_indent = Cm(-0.45)
        run = paragrafo.add_run("•\t")
        _ajustar_fonte(run, tamanho=10.5)
        run = paragrafo.add_run(item)
        _ajustar_fonte(run, tamanho=10.5)


def _render_tabela_campos(docx: DocxDocument, linhas: list[dict[str, str]]):
    tabela = docx.add_table(rows=0, cols=2)
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabela.autofit = False
    _sem_bordas(tabela)

    for linha in linhas:
        celulas = tabela.add_row().cells
        celulas[0].width = Cm(5.2)
        celulas[1].width = Cm(11.3)

        paragrafo = celulas[0].paragraphs[0]
        _espacamento(paragrafo, antes=3, depois=3)
        run = paragrafo.add_run(linha["rotulo"])
        _ajustar_fonte(run, tamanho=9, negrito=True, cor=CINZA)
        _sombra_celula(celulas[0])

        paragrafo = celulas[1].paragraphs[0]
        _espacamento(paragrafo, antes=3, depois=3)
        run = paragrafo.add_run(linha["valor"])
        _ajustar_fonte(run, tamanho=10)

        for celula in celulas:
            _borda_celula(celula, lados=("bottom",))


def _render_tabela_generica(docx: DocxDocument, cabecalho: list[str], linhas: list[list[str]]):
    total = max([len(cabecalho)] + [len(linha) for linha in linhas] or [1])
    tabela = docx.add_table(rows=0, cols=max(total, 1))
    tabela.style = "Table Grid"
    if cabecalho:
        celulas = tabela.add_row().cells
        _repetir_cabecalho(tabela.rows[0])
        for indice, titulo in enumerate(cabecalho):
            paragrafo = celulas[indice].paragraphs[0]
            run = paragrafo.add_run(titulo)
            _ajustar_fonte(run, tamanho=9, negrito=True)
            _sombra_celula(celulas[indice], "EDEDED")
    for linha in linhas:
        celulas = tabela.add_row().cells
        for indice, valor in enumerate(linha):
            if indice >= len(celulas):
                break
            run = celulas[indice].paragraphs[0].add_run(str(valor))
            _ajustar_fonte(run, tamanho=9)


def _render_clausula(docx: DocxDocument, titulo: str, texto: str):
    if titulo:
        paragrafo = docx.add_paragraph()
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _espacamento(paragrafo, antes=10, depois=2)
        paragrafo.paragraph_format.keep_with_next = True
        run = paragrafo.add_run(titulo.upper())
        _ajustar_fonte(run, tamanho=9.5, negrito=True)
    if texto:
        _paragrafo(docx, texto, tamanho=10.5)


def _render_blocos(docx: DocxDocument, blocos: list[Bloco]):
    for bloco in blocos:
        if bloco.tipo == "condicional":
            _titulo_secao(docx, bloco.dados.get("titulo", ""))
            _render_blocos(docx, bloco.dados.get("blocos", []))
        elif bloco.tipo == "p":
            _paragrafo(docx, bloco.dados["texto"])
        elif bloco.tipo == "lista":
            _render_lista(docx, bloco.dados["itens"])
        elif bloco.tipo == "clausula":
            _render_clausula(docx, bloco.dados.get("titulo", ""), bloco.dados.get("texto", ""))
        elif bloco.tipo == "tabela_campos":
            _render_tabela_campos(docx, bloco.dados["linhas"])
        elif bloco.tipo == "tabela":
            _render_tabela_generica(docx, bloco.dados.get("cabecalho", []),
                                    bloco.dados.get("linhas", []))


# --------------------------------------------------------------------------- #
# Assinaturas
# --------------------------------------------------------------------------- #
def _render_assinaturas(docx: DocxDocument, doc: Documento):
    if not doc.assinaturas:
        return

    espaco = docx.add_paragraph()
    _espacamento(espaco, antes=0, depois=0)

    por_linha = 2
    tabela = docx.add_table(rows=0, cols=por_linha)
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabela.autofit = False
    _sem_bordas(tabela)

    for indice in range(0, len(doc.assinaturas), por_linha):
        celulas = tabela.add_row().cells
        for posicao, celula in enumerate(celulas):
            celula.width = Cm(8.2)
            if indice + posicao >= len(doc.assinaturas):
                continue
            assinatura = doc.assinaturas[indice + posicao]

            vazia = celula.paragraphs[0]
            _espacamento(vazia, antes=18, depois=2)
            run = vazia.add_run("_" * 44)
            _ajustar_fonte(run, tamanho=10, cor=CINZA)
            vazia.alignment = WD_ALIGN_PARAGRAPH.CENTER

            if assinatura.get("nome"):
                paragrafo = celula.add_paragraph()
                paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _espacamento(paragrafo, antes=0, depois=0)
                run = paragrafo.add_run(assinatura["nome"])
                _ajustar_fonte(run, tamanho=9.5, negrito=True)

            paragrafo = celula.add_paragraph()
            paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _espacamento(paragrafo, antes=0, depois=0)
            run = paragrafo.add_run(assinatura.get("papel", ""))
            _ajustar_fonte(run, tamanho=8.5, cor=CINZA)

            if assinatura.get("linha2"):
                paragrafo = celula.add_paragraph()
                paragrafo.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _espacamento(paragrafo, antes=0, depois=0)
                run = paragrafo.add_run(assinatura["linha2"])
                _ajustar_fonte(run, tamanho=8, cor=CINZA)


# --------------------------------------------------------------------------- #
# Ponto de entrada
# --------------------------------------------------------------------------- #
def renderizar(doc: Documento) -> bytes:
    docx = DocxDocument()

    # Estilo base
    estilo = docx.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(10.5)
    estilo.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")

    secao = docx.sections[0]
    secao.page_width, secao.page_height = Cm(21), Cm(29.7)
    secao.top_margin, secao.bottom_margin = Cm(2.0), Cm(2.0)
    secao.left_margin, secao.right_margin = Cm(2.5), Cm(2.0)
    secao.header_distance, secao.footer_distance = Cm(1.0), Cm(1.0)

    _montar_cabecalho(secao, doc)
    _montar_rodape(secao, doc)
    _montar_titulo(docx, doc)

    for sessao in doc.secoes:
        _titulo_secao(docx, sessao.titulo)
        _render_blocos(docx, sessao.blocos)

    if doc.encerramento:
        _paragrafo(docx, doc.encerramento, antes=12)

    if doc.fecho:
        _paragrafo(docx, doc.fecho, alinhamento=WD_ALIGN_PARAGRAPH.RIGHT, antes=10, depois=6)

    _render_assinaturas(docx, doc)

    # Linha final discreta
    final = docx.add_paragraph()
    final.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _espacamento(final, antes=16, depois=0)
    _borda(final, "top", cor=CINZA_BORDA, tamanho=4, espaco=6)
    run = final.add_run(
        f"Documento gerado pelo Gerador de Documentos CEMIG em "
        f"{date.today().strftime('%d/%m/%Y')} · modelo: {doc.nome}"
    )
    _ajustar_fonte(run, tamanho=7, italico=True, cor=CINZA)

    buffer = BytesIO()
    docx.save(buffer)
    return buffer.getvalue()
