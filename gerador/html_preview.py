"""Pré-visualização do documento em HTML (mesmos blocos do DOCX/PDF)."""

from __future__ import annotations

from html import escape

from .modelos import Bloco, Documento


def _escapar(texto: str) -> str:
    return escape(str(texto or ""))


def _render_blocos(blocos: list[Bloco]) -> str:
    partes: list[str] = []
    for bloco in blocos:
        if bloco.tipo == "condicional":
            if bloco.dados.get("titulo"):
                partes.append(f'<h3>{_escapar(bloco.dados["titulo"])}</h3>')
            partes.append(_render_blocos(bloco.dados.get("blocos", [])))
        elif bloco.tipo == "p":
            partes.append(f'<p>{_escapar(bloco.dados["texto"])}</p>')
        elif bloco.tipo == "lista":
            itens = "".join(f"<li>{_escapar(i)}</li>" for i in bloco.dados["itens"])
            partes.append(f"<ul>{itens}</ul>")
        elif bloco.tipo == "clausula":
            if bloco.dados.get("titulo"):
                partes.append(f'<h4>{_escapar(bloco.dados["titulo"])}</h4>')
            if bloco.dados.get("texto"):
                partes.append(f'<p>{_escapar(bloco.dados["texto"])}</p>')
        elif bloco.tipo == "tabela_campos":
            linhas = "".join(
                f'<tr><th>{_escapar(linha["rotulo"])}</th><td>{_escapar(linha["valor"])}</td></tr>'
                for linha in bloco.dados["linhas"]
            )
            partes.append(f'<table class="campos">{linhas}</table>')
        elif bloco.tipo == "tabela":
            cabecalho = "".join(f"<th>{_escapar(c)}</th>"
                                for c in bloco.dados.get("cabecalho", []))
            corpo = "".join(
                "<tr>" + "".join(f"<td>{_escapar(c)}</td>" for c in linha) + "</tr>"
                for linha in bloco.dados.get("linhas", [])
            )
            partes.append(f"<table>{cabecalho and f'<thead><tr>{cabecalho}</tr></thead>'}"
                          f"<tbody>{corpo}</tbody></table>")
    return "".join(partes)


def renderizar(doc: Documento) -> str:
    secoes = []
    for secao in doc.secoes:
        titulo = f'<h2>{_escapar(secao.titulo)}</h2>' if secao.titulo else ""
        secoes.append(f'<section>{titulo}{_render_blocos(secao.blocos)}</section>')

    assinaturas = "".join(
        '<div class="assinatura">'
        f'<span class="papel">{_escapar(a.get("papel", ""))}</span>'
        f'<strong>{_escapar(a.get("nome", ""))}</strong>'
        f'<small>{_escapar(a.get("linha2", ""))}</small>'
        "</div>"
        for a in doc.assinaturas
    )

    meta = "".join(f"<span>{_escapar(k)}: {_escapar(v)}</span>" for k, v in doc.meta.items())
    encerramento = f'<p class="encerramento">{_escapar(doc.encerramento)}</p>' if doc.encerramento else ""
    fecho = f'<p class="fecho">{_escapar(doc.fecho)}</p>' if doc.fecho else ""
    subtitulo = f'<p class="subtitulo">{_escapar(doc.subtitulo)}</p>' if doc.subtitulo else ""

    return f"""
    <div class="folha">
      <header class="folha-topo">
        <div class="marca">CEMIG<span>Companhia Energética de Minas Gerais</span></div>
        <div class="meta-doc">{meta}</div>
      </header>
      <h1>{_escapar(doc.titulo)}</h1>
      {subtitulo}
      {''.join(secoes)}
      {encerramento}
      {fecho}
      <div class="assinaturas">{assinaturas}</div>
      <p class="rodape-doc">Documento gerado pelo Gerador de Documentos CEMIG · modelo: {_escapar(doc.nome)}</p>
    </div>
    """
