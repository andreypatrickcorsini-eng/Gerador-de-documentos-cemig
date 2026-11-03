"""Servidor web do Gerador de Documentos CEMIG (Flask)."""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request, send_file
from io import BytesIO

from gerador.gerar import DadosInvalidos, gerar_documentos, gerar_zip
from gerador.modelos import ModeloNaoEncontrado, ferramentas_frontend, listar_modelos

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024


def _campo_em_branco_para_none(valores: dict) -> dict:
    """Converte strings vazias em ``None`` para que os padrões do modelo valham."""
    return {chave: (None if isinstance(valor, str) and not valor.strip() else valor)
            for chave, valor in (valores or {}).items()}


@app.get("/")
def index():
    modelos = [modelo.resumo() for modelo in listar_modelos()]
    return render_template("index.html", modelos=modelos,
                           ferramentas=ferramentas_frontend())


@app.get("/api/modelos")
def api_modelos():
    return jsonify([modelo.resumo() for modelo in listar_modelos()])


@app.get("/api/modelos/<modelo_id>")
def api_modelo(modelo_id: str):
    try:
        from gerador.modelos import carregar_modelo
        return jsonify(carregar_modelo(modelo_id).resumo())
    except ModeloNaoEncontrado:
        return jsonify({"erro": "Modelo não encontrado."}), 404


@app.post("/api/validar")
def api_validar():
    """Valida sem gerar arquivos — usado pelo botão 'Conferir dados'."""
    from gerador.modelos import carregar_modelo, dados_efetivos, validar

    corpo = request.get_json(silent=True) or {}
    try:
        modelo = carregar_modelo(corpo.get("modelo", ""))
    except ModeloNaoEncontrado:
        return jsonify({"erro": "Modelo não encontrado."}), 404

    dados = dados_efetivos(modelo, _campo_em_branco_para_none(corpo.get("dados", {})))
    erros = validar(modelo, dados)
    return jsonify({"ok": not erros, "erros": erros})


@app.post("/api/previa")
def api_previa():
    """Monta a prévia HTML do documento sem exigir validação completa."""
    from gerador import html_preview
    from gerador.modelos import carregar_modelo, montar_documento, pendencias as campos_pendentes

    corpo = request.get_json(silent=True) or {}
    try:
        modelo = carregar_modelo(corpo.get("modelo", ""))
    except ModeloNaoEncontrado:
        return jsonify({"erro": "Modelo não encontrado."}), 404

    dados = _campo_em_branco_para_none(corpo.get("dados", {}))
    documento = montar_documento(modelo, dados, validar_dados=False, marcador_vazio="______")
    return jsonify({
        "html": html_preview.renderizar(documento),
        "pendencias": campos_pendentes(modelo, dados),
    })


@app.post("/api/gerar")
def api_gerar():
    """Gera o documento. Devolve o arquivo direto ou um ZIP com vários formatos."""
    corpo = request.get_json(silent=True) or {}
    modelo_id = corpo.get("modelo", "")
    dados = _campo_em_branco_para_none(corpo.get("dados", {}))
    formato = (corpo.get("formato") or "docx").lower()

    try:
        if formato == "zip":
            nome, conteudo = gerar_zip(modelo_id, dados)
            mimetype = "application/zip"
        else:
            gerados = gerar_documentos(modelo_id, dados, [formato])
            gerado = gerados[0]
            nome, conteudo, mimetype = gerado.nome_arquivo, gerado.conteudo, gerado.mimetype
    except ModeloNaoEncontrado:
        return jsonify({"erro": "Modelo não encontrado."}), 404
    except DadosInvalidos as erro:
        return jsonify({"erro": "Confira os campos destacados.", "erros": erro.erros}), 422

    arquivo = BytesIO(conteudo)
    arquivo.seek(0)
    return send_file(arquivo, mimetype=mimetype, as_attachment=True,
                     download_name=nome, max_age=0)


@app.post("/api/lote")
def api_lote():
    """Gera vários documentos a partir de JSON colado na tela ('modo avançado')."""
    corpo = request.get_json(silent=True) or {}
    registros = corpo.get("registros") or []
    modelo_id = corpo.get("modelo", "")
    if not isinstance(registros, list) or not registros:
        return jsonify({"erro": "Informe uma lista de registros."}), 400

    falhas, sucesso = {}, 0
    from zipfile import ZIP_DEFLATED, ZipFile

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as pacote:
        for indice, registro in enumerate(registros, start=1):
            try:
                for gerado in gerar_documentos(modelo_id, _campo_em_branco_para_none(registro),
                                               ["docx", "pdf"]):
                    pacote.writestr(gerado.nome_arquivo, gerado.conteudo)
                sucesso += 1
            except (DadosInvalidos, ModeloNaoEncontrado) as erro:
                detalhe = getattr(erro, "erros", str(erro))
                falhas[f"registro {indice}"] = detalhe
    if not sucesso:
        return jsonify({"erro": "Nenhum registro pôde ser gerado.", "falhas": falhas}), 422

    buffer.seek(0)
    resposta = send_file(buffer, mimetype="application/zip", as_attachment=True,
                         download_name=f"lote-{modelo_id}.zip", max_age=0)
    if falhas:
        resposta.headers["X-Registros-Com-Falha"] = str(len(falhas))
    return resposta


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "modelos": [m.id for m in listar_modelos()]})


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=porta, debug=os.environ.get("FLASK_DEBUG") == "1")
