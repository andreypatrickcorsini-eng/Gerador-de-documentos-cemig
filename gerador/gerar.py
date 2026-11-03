"""Fachada de geração: um documento por vez, pacote ZIP ou lote em disco."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

from . import docx_render, pdf_render
from .modelos import DadosInvalidos, Modelo, ModeloNaoEncontrado, montar_documento

FORMATOS = ("docx", "pdf")


@dataclass
class DocumentoGerado:
    nome_base: str
    formato: str
    conteudo: bytes

    @property
    def nome_arquivo(self) -> str:
        return f"{self.nome_base}.{self.formato}"

    @property
    def mimetype(self) -> str:
        return {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pdf": "application/pdf",
        }[self.formato]


def _normalizar_formatos(formatos: Iterable[str] | str | None) -> list[str]:
    if not formatos:
        return list(FORMATOS)
    if isinstance(formatos, str):
        formatos = re.split(r"[,\s]+", formatos)
    pedidos = [f.lower().lstrip(".") for f in formatos if f]
    validos = [f for f in pedidos if f in FORMATOS]
    return validos or list(FORMATOS)


def montar_documento_de(modelo_id: str, valores: dict[str, Any]):
    from .modelos import carregar_modelo

    modelo: Modelo = carregar_modelo(modelo_id)
    return montar_documento(modelo, valores)


def gerar_documentos(
    modelo_id: str,
    valores: dict[str, Any],
    formatos: Iterable[str] | str | None = None,
) -> list[DocumentoGerado]:
    """Valida os dados e devolve os documentos nos formatos pedidos.

    Levanta :class:`DadosInvalidos` com o mapa ``{campo: mensagem}`` quando o
    formulário não passa na validação, e :class:`ModeloNaoEncontrado` quando o
    identificador do modelo não existe em ``modelos/``.
    """
    documento = montar_documento_de(modelo_id, valores)
    gerados = []
    for formato in _normalizar_formatos(formatos):
        render = docx_render.renderizar if formato == "docx" else pdf_render.renderizar
        gerados.append(DocumentoGerado(documento.nome_arquivo, formato, render(documento)))
    return gerados


def gerar_zip(modelo_id: str, valores: dict[str, Any],
              formatos: Iterable[str] | str | None = None) -> tuple[str, bytes]:
    """Gera os arquivos e devolve ``(nome_do_zip, bytes)``."""
    gerados = gerar_documentos(modelo_id, valores, formatos)
    nome_zip = f"{gerados[0].nome_base}.zip" if gerados else "documento.zip"
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as pacote:
        for gerado in gerados:
            pacote.writestr(gerado.nome_arquivo, gerado.conteudo)
    return nome_zip, buffer.getvalue()


def gerar_lote(modelos_e_dados: Iterable[tuple[str, dict[str, Any]]],
               formatos: Iterable[str] | str | None = None,
               destino: str | Path = "saida") -> list[Path]:
    """Gera vários documentos em disco (útil para automação/mala direta).

    Cada item é ``(modelo_id, valores)``. Retorna a lista de arquivos escritos.
    """
    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []
    for modelo_id, valores in modelos_e_dados:
        for gerado in gerar_documentos(modelo_id, valores, formatos):
            caminho = pasta / gerado.nome_arquivo
            contador = 2
            while caminho.exists():
                caminho = pasta / f"{gerado.nome_base}-{contador}.{gerado.formato}"
                contador += 1
            caminho.write_bytes(gerado.conteudo)
            escritos.append(caminho)
    return escritos


def ler_lote_json(caminho: str | Path) -> list[tuple[str, dict[str, Any]]]:
    """Lê um arquivo JSON com ``{"modelo": "...", "registros": [...]}``."""
    bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
    modelo_id = bruto.get("modelo") or bruto.get("modelo_id")
    if not modelo_id:
        raise ValueError("O arquivo de lote precisa informar 'modelo'.")
    return [(modelo_id, registro) for registro in bruto.get("registros", [])]


__all__ = [
    "DocumentoGerado",
    "DadosInvalidos",
    "ModeloNaoEncontrado",
    "FORMATOS",
    "gerar_documentos",
    "gerar_zip",
    "gerar_lote",
    "ler_lote_json",
    "montar_documento_de",
]
