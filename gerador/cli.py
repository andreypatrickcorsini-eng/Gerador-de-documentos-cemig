"""Linha de comando do gerador.

Exemplos::

    python -m gerador.cli modelos
    python -m gerador.cli gerar travessia --dados exemplos/travessia.json
    python -m gerador.cli lote exemplos/lote.json --saida saida/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gerar import DadosInvalidos, ModeloNaoEncontrado, gerar_lote, ler_lote_json
from .modelos import listar_modelos


def _listar(_args) -> int:
    for modelo in listar_modelos():
        print(f"\n{modelo.icone} {modelo.nome}  ({modelo.id})")
        print(f"   {modelo.descricao}")
        print(f"   campos: {len(modelo.campos)} | seções: {len(modelo.secoes)}")
        for grupo in modelo.grupos():
            campos = [c for c in modelo.campos if c.get("grupo") == grupo]
            obrigatorios = [c for c in campos if c.get("obrigatorio")]
            print(f"   · {grupo}: " + ", ".join(c["chave"] for c in campos))
            if obrigatorios:
                print("     obrigatórios: " + ", ".join(c["chave"] for c in obrigatorios))
    print()
    return 0


def _ler_dados(caminho: str | None, argumentos: list[str]) -> dict:
    dados: dict = {}
    if caminho:
        dados.update(json.loads(Path(caminho).read_text(encoding="utf-8")))
    for par in argumentos:
        chave, _, valor = par.partition("=")
        if not chave or not _:
            print(f"Campo inválido: {par!r} (use chave=valor)", file=sys.stderr)
            raise SystemExit(2)
        dados[chave.strip()] = valor
    return dados


def _gerar(args) -> int:
    dados = _ler_dados(args.dados, args.campo)
    try:
        arquivos = gerar_lote([(args.modelo, dados)], args.formato, args.saida)
    except (DadosInvalidos, ModeloNaoEncontrado) as erro:
        if isinstance(erro, DadosInvalidos):
            print("Dados inválidos:", file=sys.stderr)
            for campo, mensagem in erro.erros.items():
                print(f"  · {campo}: {mensagem}", file=sys.stderr)
        else:
            print(f"Modelo não encontrado: {args.modelo}", file=sys.stderr)
        return 1
    for arquivo in arquivos:
        print(f"✔ {arquivo}")
    return 0


def _lote(args) -> int:
    itens = ler_lote_json(args.arquivo)
    arquivos = gerar_lote(itens, args.formato, args.saida)
    for arquivo in arquivos:
        print(f"✔ {arquivo}")
    print(f"\n{len(arquivos)} arquivo(s) gerado(s) em {Path(args.saida).resolve()}")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gerador", description="Gerador de documentos CEMIG (Travessia e Desembargo).")
    sub = parser.add_subparsers(dest="comando", required=True)

    listar = sub.add_parser("modelos", help="lista os modelos e seus campos")
    listar.set_defaults(funcao=_listar)

    gerar = sub.add_parser("gerar", help="gera um documento a partir de dados")
    gerar.add_argument("modelo", help="travessia ou desembargo")
    gerar.add_argument("--dados", help="arquivo JSON com os dados")
    gerar.add_argument("--campo", action="append", nargs="?", default=[],
                       metavar="CHAVE=VALOR", help="informa um campo (pode repetir)")
    gerar.add_argument("--formato", action="append", choices=["docx", "pdf"],
                       help="formato de saída (padrão: os dois)")
    gerar.add_argument("--saida", default="saida", help="pasta de destino")
    gerar.set_defaults(funcao=_gerar)

    lote = sub.add_parser("lote", help="gera vários documentos de um JSON")
    lote.add_argument("arquivo", help="JSON com {'modelo': ..., 'registros': [...]}")
    lote.add_argument("--formato", action="append", choices=["docx", "pdf"])
    lote.add_argument("--saida", default="saida", help="pasta de destino")
    lote.set_defaults(funcao=_lote)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    return args.funcao(args)


if __name__ == "__main__":
    raise SystemExit(main())
