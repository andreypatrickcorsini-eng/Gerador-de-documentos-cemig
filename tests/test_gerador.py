"""Testes do núcleo do gerador.

Execute com::

    .venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gerador import util  # noqa: E402
from gerador.gerar import (  # noqa: E402
    DadosInvalidos,
    gerar_documentos,
    gerar_zip,
    ler_lote_json,
)
from gerador.modelos import (  # noqa: E402
    ModeloNaoEncontrado,
    carregar_modelo,
    listar_modelos,
    montar_documento,
    pendencias,
    validar,
)

TRAVESSIA = {
    "protocolo": "2026.001.12345",
    "data_documento": "2026-11-03",
    "interessado_nome": "João da Silva",
    "interessado_documento": "11144477735",
    "interessado_telefone": "35999887766",
    "interessado_email": "joao@exemplo.com.br",
    "empreendimento": "Fazenda Boa Esperança — Talhão 3",
    "municipio": "Varginha",
    "uf": "MG",
    "tipo_travessia": "Rede de distribuição aérea",
    "tensao_kv": "13,8",
    "extensao_m": "180",
    "vao_m": "60",
    "postes": "4",
    "altura_livre": "6,5",
    "data_inicio": "2026-11-10",
    "data_conclusao": "2026-12-20",
    "responsavel_nome": "Maria Souza",
    "responsavel_registro": "CREA-MG 123456/D",
    "art_numero": "000123456789",
    "observacoes": "Manter sinalização noturna.\nComunicar interrupção programada.",
}

DESEMBARGO = {
    "data_documento": "2026-11-03",
    "interessado_nome": "Agropecuária Santa Rita Ltda.",
    "interessado_documento": "11222333000181",
    "empreendimento": "Fazenda Santa Rita",
    "municipio": "Três Corações",
    "uf": "MG",
    "auto_embargo": "AE 012345/2025",
    "data_embargo": "2025-08-14",
    "area_m2": "125000",
    "motivo_embargo": "Intervenção em Área de Preservação Permanente — APP",
    "responsavel_nome": "Carlos Pereira",
    "responsavel_registro": "CREA-MG 654321/D",
}


class TestUtil(unittest.TestCase):
    def test_cpf_cnpj(self):
        self.assertTrue(util.validar_cpf("111.444.777-35"))
        self.assertFalse(util.validar_cpf("111.444.777-36"))
        self.assertTrue(util.validar_cnpj("11.222.333/0001-81"))
        self.assertFalse(util.validar_cnpj("11.222.333/0001-82"))
        self.assertEqual(util.formatar_cpf("11144477735"), "111.444.777-35")
        self.assertEqual(util.formatar_cnpj("11222333000181"), "11.222.333/0001-81")

    def test_numeros_br(self):
        self.assertEqual(util.para_decimal("1.234,56"), util.para_decimal("1234.56"))
        self.assertEqual(util.formatar_decimal("1234,5"), "1.234,50")
        self.assertEqual(util.formatar_moeda(1234.5), "R$ 1.234,50")
        self.assertEqual(util.numero_por_extenso(2026), "dois mil e vinte e seis")
        self.assertEqual(util.numero_por_extenso(125000), "cento e vinte e cinco mil")

    def test_datas(self):
        self.assertEqual(util.formatar_data("2026-11-03"), "03/11/2026")
        self.assertEqual(util.data_extenso_curta("2026-11-03"), "3 de novembro de 2026")
        self.assertIn("três dias do mês de novembro de dois mil e vinte e seis",
                      util.data_por_extenso("2026-11-03"))

    def test_nome_arquivo(self):
        self.assertEqual(util.nome_arquivo_seguro("Fazenda Boa Esperança — Talhão 3"),
                         "fazenda-boa-esperanca-talhao-3")


class TestModelos(unittest.TestCase):
    def test_lista(self):
        ids = {modelo.id for modelo in listar_modelos()}
        self.assertEqual(ids, {"travessia", "desembargo"})

    def test_modelo_inexistente(self):
        with self.assertRaises(ModeloNaoEncontrado):
            carregar_modelo("nao-existe")

    def test_travessia_completa(self):
        modelo = carregar_modelo("travessia")
        self.assertEqual(validar(modelo, TRAVESSIA), {})
        documento = montar_documento(modelo, TRAVESSIA)
        self.assertEqual(documento.titulo, modelo.titulo_documento)
        self.assertEqual(len(documento.secoes), 6)
        textos = json.dumps([secao.titulo for secao in documento.secoes], ensure_ascii=False)
        self.assertIn("CARACTERÍSTICAS DA TRAVESSIA", textos)

    def test_campos_calculados(self):
        modelo = carregar_modelo("travessia")
        documento = montar_documento(modelo, {**TRAVESSIA, "prazo_dias": ""})
        tabela = next(b for s in documento.secoes for b in s.blocos
                      if b.tipo == "tabela_campos"
                      and any("Prazo" in linha["rotulo"] for linha in b.dados["linhas"]))
        valores = {linha["rotulo"]: linha["valor"] for linha in tabela.dados["linhas"]}
        self.assertEqual(valores["Prazo de execução (dias)"], "40 dias")

        modelo = carregar_modelo("desembargo")
        documento = montar_documento(modelo, DESEMBARGO)
        tabela = next(b for s in documento.secoes for b in s.blocos
                      if b.tipo == "tabela_campos"
                      and any("ha" in linha["rotulo"] for linha in b.dados["linhas"]))
        valores = {linha["rotulo"]: linha["valor"] for linha in tabela.dados["linhas"]}
        self.assertEqual(valores["Área embargada (ha)"], "12,5 ha")
        self.assertEqual(valores["Área embargada (m²)"], "125.000 m²")

    def test_cpf_invalido(self):
        modelo = carregar_modelo("travessia")
        erros = validar(modelo, {**TRAVESSIA, "interessado_documento": "111.111.111-11"})
        self.assertIn("interessado_documento", erros)

    def test_obrigatorios(self):
        modelo = carregar_modelo("desembargo")
        erros = validar(modelo, {})
        self.assertIn("empreendimento", erros)
        self.assertIn("auto_embargo", erros)
        # campos com valor padrão não entram como pendência
        self.assertNotIn("orgao_destinatario", pendencias(modelo, {}))
        self.assertIn("empreendimento", pendencias(modelo, {}))

    def test_datas_incoerentes(self):
        modelo = carregar_modelo("travessia")
        erros = validar(modelo, {**TRAVESSIA,
                                 "data_inicio": "2026-12-20",
                                 "data_conclusao": "2026-11-10"})
        self.assertIn("data_conclusao", erros)

    def test_texto_por_extenso_na_clausula(self):
        modelo = carregar_modelo("desembargo")
        documento = montar_documento(modelo, DESEMBARGO)
        textos = json.dumps(
            [[getattr(b, "dados", {}) for b in secao.blocos] for secao in documento.secoes],
            ensure_ascii=False,
        )
        self.assertIn("(12,5 ha)", textos)
        self.assertIn("em razão de intervenção em Área de Preservação Permanente — APP", textos)
        # campos opcionais vazios não deixam "nº" solto no texto
        self.assertNotIn("ART/RRT nº;", textos)
        self.assertNotIn("PRAD nº ou", textos)
        self.assertNotIn("início previsto em,", textos)

    def test_marcador_de_vazio(self):
        modelo = carregar_modelo("travessia")
        documento = montar_documento(modelo, {"data_documento": "2026-11-03"},
                                     validar_dados=False, marcador_vazio="___")
        bruto = json.dumps([[getattr(b, "dados", {}) for b in s.blocos] for s in documento.secoes],
                           ensure_ascii=False)
        self.assertIn("___", bruto)


class TestGeracao(unittest.TestCase):
    def test_gera_docx_e_pdf(self):
        documentos = gerar_documentos("travessia", TRAVESSIA)
        formatos = {documento.formato for documento in documentos}
        self.assertEqual(formatos, {"docx", "pdf"})
        for documento in documentos:
            self.assertGreater(len(documento.conteudo), 5000)
            if documento.formato == "pdf":
                self.assertTrue(documento.conteudo.startswith(b"%PDF"))
            else:
                self.assertTrue(documento.conteudo.startswith(b"PK"))

    def test_formato_pdf_somente(self):
        documentos = gerar_documentos("desembargo", DESEMBARGO, "pdf")
        self.assertEqual([documento.formato for documento in documentos], ["pdf"])

    def test_zip(self):
        nome, conteudo = gerar_zip("desembargo", DESEMBARGO)
        self.assertTrue(nome.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            nomes = pacote.namelist()
        self.assertEqual(len(nomes), 2)
        self.assertTrue(any(n.endswith(".docx") for n in nomes))
        self.assertTrue(any(n.endswith(".pdf") for n in nomes))

    def test_erro_de_validacao(self):
        with self.assertRaises(DadosInvalidos) as contexto:
            gerar_documentos("desembargo", {"municipio": "Varginha"})
        self.assertIn("empreendimento", contexto.exception.erros)

    def test_lote_json(self):
        caminho = Path("/tmp/lote-teste.json")
        caminho.write_text(json.dumps({
            "modelo": "desembargo",
            "registros": [DESEMBARGO, {**DESEMBARGO, "empreendimento": "Outra Fazenda"}],
        }), encoding="utf-8")
        itens = ler_lote_json(caminho)
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[1][1]["empreendimento"], "Outra Fazenda")


class TestFlask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app.test_client()

    def test_index(self):
        resposta = self.app.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b"Travessia", resposta.data)
        self.assertIn(b"Desembargo", resposta.data)

    def test_api_modelos(self):
        dados = self.app.get("/api/modelos").get_json()
        self.assertEqual({modelo["id"] for modelo in dados}, {"travessia", "desembargo"})
        for modelo in dados:
            self.assertTrue(modelo["campos"])
            self.assertEqual(set(modelo["grupos"]),
                             {campo.get("grupo", "Dados") for campo in modelo["campos"]})

    def test_api_gerar_docx(self):
        resposta = self.app.post("/api/gerar", json={
            "modelo": "travessia", "dados": TRAVESSIA, "formato": "docx"})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("wordprocessingml", resposta.headers["Content-Type"])
        self.assertIn("attachment", resposta.headers["Content-Disposition"])

    def test_api_gerar_zip(self):
        resposta = self.app.post("/api/gerar", json={
            "modelo": "desembargo", "dados": DESEMBARGO, "formato": "zip"})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.headers["Content-Type"], "application/zip")

    def test_api_gerar_invalido(self):
        resposta = self.app.post("/api/gerar", json={
            "modelo": "desembargo", "dados": {}, "formato": "pdf"})
        self.assertEqual(resposta.status_code, 422)
        self.assertIn("empreendimento", resposta.get_json()["erros"])

    def test_api_modelo_inexistente(self):
        resposta = self.app.post("/api/gerar", json={
            "modelo": "../etc/passwd", "dados": {}, "formato": "pdf"})
        self.assertEqual(resposta.status_code, 404)

    def test_api_previa(self):
        resposta = self.app.post("/api/previa", json={
            "modelo": "travessia", "dados": {"interessado_nome": "João"}})
        corpo = resposta.get_json()
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("TERMO DE AUTORIZAÇÃO", corpo["html"])
        self.assertIn("empreendimento", corpo["pendencias"])

    def test_api_validar(self):
        resposta = self.app.post("/api/validar", json={
            "modelo": "desembargo", "dados": DESEMBARGO})
        corpo = resposta.get_json()
        self.assertTrue(corpo["ok"], corpo.get("erros"))

    def test_api_lote(self):
        resposta = self.app.post("/api/lote", json={
            "modelo": "desembargo", "registros": [DESEMBARGO]})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.headers["Content-Type"], "application/zip")


if __name__ == "__main__":
    unittest.main(verbosity=2)
