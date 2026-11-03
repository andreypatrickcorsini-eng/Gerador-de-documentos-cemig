"""Núcleo do gerador de documentos CEMIG.

O pacote é organizado em três camadas:

* ``util``     → formatação, validação e conversões (CPF, datas, valores, extenso).
* ``modelos``  → leitura dos modelos JSON, validação dos dados e montagem dos
                 blocos de documento (representação intermediária).
* ``docx_render`` / ``pdf_render`` → desenham os blocos em Word e PDF.

Tudo é dirigido pelos arquivos em ``modelos/*.json``: para trocar o texto oficial
de Travessia ou Desembargo basta editar o JSON, sem mexer em código.
"""

from .gerar import gerar_documentos, ModeloNaoEncontrado  # noqa: F401

__all__ = ["gerar_documentos", "ModeloNaoEncontrado"]
