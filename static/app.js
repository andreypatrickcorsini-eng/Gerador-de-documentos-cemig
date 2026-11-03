/* Gerador de Documentos CEMIG — lógica da interface */
(function () {
  "use strict";

  const MODELOS = window.MODELOS || [];
  const FERRAMENTAS = window.FERRAMENTAS || {};

  const $ = (seletor) => document.querySelector(seletor);
  const seletorTipo = document.querySelectorAll(".opcao-tipo");
  const container = $("#campos-container");
  const formulario = $("#formulario");
  const aviso = $("#aviso");
  const previaArea = $("#previa-area");
  const statusPrevia = $("#status-previa");

  let modeloAtual = null;
  let valores = {};          // valores digitados por modelo
  let errosAtuais = {};
  let zoom = 0;
  let temporizador = null;
  let requisicaoPrevia = null;

  const ZOONS = [
    { classe: "", rotulo: "100%" },
    { classe: "zoom-125", rotulo: "125%" },
    { classe: "zoom-150", rotulo: "150%" },
  ];

  // ---------------------------------------------------------------- util --
  function ehData(valor) {
    return /^\d{4}-\d{2}-\d{2}$/.test(valor || "");
  }

  function dataParaBR(valor) {
    if (!ehData(valor)) return valor || "";
    const [ano, mes, dia] = valor.split("-");
    return `${dia}/${mes}/${ano}`;
  }

  function brParaData(valor) {
    const achado = String(valor || "").match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return achado ? `${achado[3]}-${achado[2]}-${achado[1]}` : valor;
  }

  function paraNumero(valor) {
    if (valor === null || valor === undefined || valor === "") return null;
    const limpo = String(valor).replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
    const numero = Number(limpo);
    return Number.isFinite(numero) ? numero : null;
  }

  function formatarNumero(numero, casas) {
    if (numero === null) return "";
    return numero.toLocaleString("pt-BR", {
      minimumFractionDigits: casas,
      maximumFractionDigits: casas,
    });
  }

  function casasDecimais(campo) {
    if (campo.casas_decimais !== undefined) return campo.casas_decimais;
    const valor = valores[campo.chave];
    const texto = String(valor === undefined || valor === null ? "" : valor).replace(",", ".");
    if (texto === "") return 0;
    return Number.isInteger(Number(texto)) ? 0 : 2;
  }

  function limparAviso() {
    aviso.className = "aviso";
    aviso.innerHTML = "";
  }

  function mostrarAviso(tipo, html) {
    aviso.className = "aviso visivel " + tipo;
    aviso.innerHTML = html;
  }

  function escapar(texto) {
    return String(texto === undefined || texto === null ? "" : texto)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ------------------------------------------------------- recálculos -----
  function recalcular() {
    if (!modeloAtual) return;
    modeloAtual.campos.forEach((campo) => {
      if (!campo.calculado) return;
      if (valores[campo.chave]) return; // valor informado à mão prevalece

      if (campo.calculado === "dias_entre") {
        const inicio = valores.data_inicio;
        const fim = valores.data_conclusao;
        if (ehData(inicio) && ehData(fim)) {
          const dias = Math.round(
            (new Date(fim + "T12:00:00") - new Date(inicio + "T12:00:00")) / 86400000
          );
          valores[campo.chave] = dias >= 0 ? String(dias) : "";
        }
      } else if (campo.calculado === "m2_para_ha") {
        const area = paraNumero(valores.area_m2);
        if (area !== null) {
          valores[campo.chave] = (area / 10000).toLocaleString("pt-BR",
            { minimumFractionDigits: 4, maximumFractionDigits: 4 });
        }
      }
    });
  }

  // ----------------------------------------------------------- máscaras ---
  function mascararDocumento(bruto) {
    const d = String(bruto || "").replace(/\D/g, "").slice(0, 14);
    if (d.length <= 11) {
      return d
        .replace(/^(\d{3})(\d)/, "$1.$2")
        .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
        .replace(/\.(\d{3})(\d{1,2})$/, ".$1-$2");
    }
    return d
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1/$2")
      .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
  }

  function mascararTelefone(bruto) {
    const d = String(bruto || "").replace(/\D/g, "").slice(0, 11);
    if (d.length <= 10) {
      return d.replace(/^(\d{2})(\d)/, "($1) $2")
              .replace(/(\d{4})(\d{1,4})$/, "$1-$2");
    }
    return d.replace(/^(\d{2})(\d)/, "($1) $2")
            .replace(/(\d{5})(\d{1,4})$/, "$1-$2");
  }

  // ------------------------------------------------------ formulário ------
  function campoHTML(campo) {
    const chave = campo.chave;
    const valor = valores[chave] === undefined ? "" : valores[chave];
    const id = "campo-" + chave;
    const obrig = campo.obrigatorio ? '<span class="obrig">*</span>' : "";
    const largo = campo.largo ? " largo" : "";
    const classes = ["campo", largo.trim(), campo.calculado ? "calculado" : ""].join(" ");
    let controle = "";

    if (campo.tipo === "selecao") {
      const opcoes = campo.opcoes || [];
      const itens = ['<option value=""></option>'].concat(
        opcoes.map((o) => `<option value="${escapar(o)}"${o === valor ? " selected" : ""}>${escapar(o)}</option>`)
      );
      controle = `<select id="${id}" name="${chave}" data-chave="${chave}">${itens.join("")}</select>`;
    } else if (campo.tipo === "area") {
      controle = `<textarea id="${id}" name="${chave}" data-chave="${chave}"
        placeholder="${escapar(campo.placeholder || "")}">${escapar(valor)}</textarea>`;
    } else {
      const tipo = campo.tipo === "data" ? "date"
        : campo.tipo === "email" ? "email"
        : campo.tipo === "numero" ? "text"
        : campo.tipo === "telefone" ? "tel" : "text";
      const inputmode = campo.tipo === "numero" ? ' inputmode="decimal"'
        : campo.tipo === "documento" || campo.tipo === "telefone" ? ' inputmode="numeric"' : "";
      const exibido = campo.tipo === "data" ? brParaData(valor) : valor;
      controle = `<input id="${id}" name="${chave}" data-chave="${chave}" type="${tipo}"${inputmode}
        value="${escapar(exibido)}" placeholder="${escapar(campo.placeholder || "")}"
        ${campo.calculado ? "" : "autocomplete=\"off\""}>`;
    }

    const dica = campo.dica ? `<span class="dica">${escapar(campo.dica)}</span>` : "";
    const erro = `<span class="erro-campo" data-erro="${chave}"></span>`;

    return `<div class="${classes}" data-wrapper="${chave}">
      <label for="${id}">${escapar(campo.rotulo)}${obrig}</label>
      ${controle}
      ${dica}${erro}
    </div>`;
  }

  function renderizarFormulario(modelo) {
    const grupos = {};
    (modelo.grupos || []).forEach((g) => { grupos[g] = []; });
    modelo.campos.forEach((campo) => {
      const grupo = campo.grupo || "Dados";
      (grupos[grupo] = grupos[grupo] || []).push(campo);
    });

    container.innerHTML = Object.keys(grupos).map((nome) => {
      const campos = grupos[nome].map(campoHTML).join("");
      return `<fieldset class="grupo" style="border:0;padding:0;margin:0 0 18px;">
        <legend>${escapar(nome)}</legend>
        <div class="grade">${campos}</div>
      </fieldset>`;
    }).join("");

    // Sincroniza campos recalculados
    modelo.campos.forEach((campo) => {
      const elemento = document.querySelector(`[data-chave="${campo.chave}"]`);
      if (elemento && valores[campo.chave] !== undefined && campo.calculado) {
        elemento.value = valores[campo.chave];
      }
    });

    aplicarErros();
  }

  function aplicarErros() {
    document.querySelectorAll("[data-wrapper]").forEach((wrapper) => {
      const chave = wrapper.dataset.wrapper;
      const mensagem = errosAtuais[chave];
      wrapper.classList.toggle("invalido", Boolean(mensagem));
      const alvo = wrapper.querySelector("[data-erro]");
      if (alvo) alvo.textContent = mensagem || "";
    });
  }

  // ------------------------------------------------------ prévia ------
  function agendarPrevia() {
    clearTimeout(temporizador);
    temporizador = setTimeout(atualizarPrevia, 320);
  }

  async function atualizarPrevia() {
    if (!modeloAtual) return;
    if (requisicaoPrevia) requisicaoPrevia.abort();
    requisicaoPrevia = new AbortController();

    statusPrevia.textContent = "atualizando…";
    statusPrevia.className = "pill";

    try {
      const resposta = await fetch("/api/previa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modelo: modeloAtual.id, dados: valores }),
        signal: requisicaoPrevia.signal,
      });
      const dados = await resposta.json();
      if (!resposta.ok) throw new Error(dados.erro || "Falha na prévia");

      previaArea.innerHTML = dados.html;
      const faltando = dados.pendencias || [];
      if (faltando.length) {
        statusPrevia.textContent = `${faltando.length} campo(s) pendente(s)`;
        statusPrevia.className = "pill alerta";
      } else {
        statusPrevia.textContent = "pronto para gerar";
        statusPrevia.className = "pill ok";
      }
      const folha = previaArea.querySelector(".folha");
      if (folha) folha.classList.add(...ZOONS[zoom].classe.split(" ").filter(Boolean));
    } catch (erro) {
      if (erro.name === "AbortError") return;
      statusPrevia.textContent = "prévia indisponível";
      statusPrevia.className = "pill alerta";
    }
  }

  // ------------------------------------------------------ eventos ------
  function selecionarModelo(id) {
    const modelo = MODELOS.find((m) => m.id === id);
    if (!modelo) return;
    modeloAtual = modelo;
    valores = valoresPorModelo[id] || {};
    errosAtuais = {};

    seletorTipo.forEach((botao) => {
      botao.setAttribute("aria-checked", String(botao.dataset.modelo === id));
    });

    // Preenche padrões na primeira utilização
    if (!valoresPorModelo[id]) {
      modelo.campos.forEach((campo) => {
        if (campo.padrao !== undefined && campo.padrao !== null && !campo.calculado) {
          valores[campo.chave] = campo.padrao;
        }
      });
      if (modelo.campos.some((c) => c.chave === "data_documento") && !valores.data_documento) {
        valores.data_documento = new Date().toISOString().slice(0, 10);
      }
    }

    limparAviso();
    recalcular();
    renderizarFormulario(modelo);
    document.querySelectorAll(".acoes .botao").forEach((botao) => { botao.disabled = false; });
    atualizarPrevia();
  }

  const valoresPorModelo = {};

  seletorTipo.forEach((botao) => {
    botao.addEventListener("click", () => selecionarModelo(botao.dataset.modelo));
  });

  container.addEventListener("input", (evento) => {
    const alvo = evento.target;
    const chave = alvo.dataset.chave;
    if (!chave || !modeloAtual) return;
    const campo = modeloAtual.campos.find((c) => c.chave === chave) || {};

    let valor = alvo.value;
    if (campo.tipo === "documento" && valor) {
      valor = mascararDocumento(valor);
      alvo.value = valor;
    } else if (campo.tipo === "telefone" && valor) {
      valor = mascararTelefone(valor);
      alvo.value = valor;
    }

    valores[chave] = valor;
    valoresPorModelo[modeloAtual.id] = valores;

    // Recalcula dependentes e atualiza seus inputs
    modeloAtual.campos.forEach((dependente) => {
      if (dependente.calculado && campo.origem && dependente.origem.includes(chave)) {
        valores[dependente.chave] = "";
      }
    });
    recalcular();
    modeloAtual.campos.forEach((c) => {
      if (!c.calculado) return;
      const elemento = document.querySelector(`[data-chave="${c.chave}"]`);
      if (elemento && document.activeElement !== elemento) {
        elemento.value = valores[c.chave] === undefined ? "" : valores[c.chave];
      }
    });

    if (errosAtuais[chave]) {
      delete errosAtuais[chave];
      aplicarErros();
    }
    agendarPrevia();
  });

  container.addEventListener("change", () => agendarPrevia());

  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    gerar("docx");
  });

  $("#btn-pdf").addEventListener("click", () => gerar("pdf"));
  $("#btn-zip").addEventListener("click", () => gerar("zip"));

  $("#btn-zoom").addEventListener("click", () => {
    zoom = (zoom + 1) % ZOONS.length;
    $("#btn-zoom").textContent = "🔍 " + ZOONS[zoom].rotulo;
    const folha = previaArea.querySelector(".folha");
    if (folha) {
      folha.classList.remove("zoom-125", "zoom-150");
      if (ZOONS[zoom].classe) folha.classList.add(ZOONS[zoom].classe);
    }
  });

  $("#btn-conferir").addEventListener("click", async () => {
    if (!modeloAtual) return mostrarAviso("info", "Escolha primeiro o tipo de documento.");
    try {
      const resposta = await fetch("/api/validar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modelo: modeloAtual.id, dados: valores }),
      });
      const dados = await resposta.json();
      errosAtuais = dados.erros || {};
      aplicarErros();
      if (dados.ok) {
        const pendencias = modeloAtual.campos.filter(
          (c) => !c.obrigatorio && !String(valores[c.chave] || "").trim()
        ).length;
        mostrarAviso("ok", "Todos os campos obrigatórios estão corretos." +
          (pendencias ? ` ${pendencias} campo(s) opcional(is) em branco serão omitidos do documento.` : ""));
      } else {
        const itens = Object.entries(errosAtuais)
          .map(([chave, msg]) => {
            const campo = modeloAtual.campos.find((c) => c.chave === chave);
            return `<li><strong>${escapar(campo ? campo.rotulo : chave)}</strong>: ${escapar(msg)}</li>`;
          }).join("");
        mostrarAviso("erro", `Corrija ${Object.keys(errosAtuais).length} campo(s):<ul>${itens}</ul>`);
      }
    } catch (erro) {
      mostrarAviso("erro", "Não foi possível conferir os dados agora. Tente novamente.");
    }
  });

  $("#btn-limpar").addEventListener("click", () => {
    if (!modeloAtual) return;
    if (!confirm("Limpar todos os campos deste documento?")) return;
    delete valoresPorModelo[modeloAtual.id];
    valores = {};
    errosAtuais = {};
    selecionarModelo(modeloAtual.id);
    limparAviso();
  });

  // ------------------------------------------------------ geração -----
  async function baixar(resposta, nomePadrao) {
    const tipo = resposta.headers.get("Content-Type") || "";
    if (tipo.includes("application/json")) {
      const dados = await resposta.json();
      errosAtuais = dados.erros || {};
      aplicarErros();
      if (errosAtuais && Object.keys(errosAtuais).length) {
        const itens = Object.entries(errosAtuais).map(([chave, msg]) => {
          const campo = modeloAtual.campos.find((c) => c.chave === chave);
          return `<li><strong>${escapar(campo ? campo.rotulo : chave)}</strong>: ${escapar(msg)}</li>`;
        }).join("");
        mostrarAviso("erro", `Antes de gerar, corrija:<ul>${itens}</ul>`);
      } else {
        mostrarAviso("erro", escapar(dados.erro || "Não foi possível gerar o documento."));
      }
      return;
    }

    const disposicao = resposta.headers.get("Content-Disposition") || "";
    const achado = disposicao.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
    const nome = achado ? decodeURIComponent(achado[1].replace(/"/g, "")) : nomePadrao;

    const blob = await resposta.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = nome;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    mostrarAviso("ok", `Documento gerado: <strong>${escapar(nome)}</strong>`);
  }

  async function gerar(formato) {
    if (!modeloAtual) {
      mostrarAviso("info", "Escolha primeiro <strong>Travessia</strong> ou <strong>Desembargo</strong>.");
      return;
    }
    const botao = formato === "docx" ? $("#btn-word") : formato === "pdf" ? $("#btn-pdf") : $("#btn-zip");
    const conteudoOriginal = botao.innerHTML;
    botao.disabled = true;
    botao.innerHTML = '<span class="spinner"></span> gerando…';
    limparAviso();

    try {
      const resposta = await fetch("/api/gerar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modelo: modeloAtual.id, dados: valores, formato }),
      });
      if (resposta.status === 422 || !resposta.ok) {
        await baixar(resposta, "documento");
      } else {
        await baixar(resposta, `documento.${formato}`);
      }
    } catch (erro) {
      mostrarAviso("erro", "Falha de comunicação com o servidor. Verifique se ele está em execução.");
    } finally {
      botao.disabled = false;
      botao.innerHTML = conteudoOriginal;
    }
  }

  // ------------------------------------------------------ lote -----
  $("#btn-lote").addEventListener("click", async () => {
    if (!modeloAtual) return mostrarAviso("info", "Escolha primeiro o tipo de documento.");
    let registros;
    try {
      registros = JSON.parse($("#lote-json").value || "[]");
    } catch (erro) {
      return mostrarAviso("erro", "O JSON do lote está inválido: " + escapar(erro.message));
    }
    if (!Array.isArray(registros) || !registros.length) {
      return mostrarAviso("info", "Cole uma lista JSON com pelo menos um registro.");
    }
    const botao = $("#btn-lote");
    botao.disabled = true;
    botao.innerHTML = '<span class="spinner"></span> gerando…';
    try {
      const resposta = await fetch("/api/lote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modelo: modeloAtual.id, registros }),
      });
      await baixar(resposta, `lote-${modeloAtual.id}.zip`);
    } finally {
      botao.disabled = false;
      botao.innerHTML = "📦 Gerar lote (.zip)";
    }
  });

  // ------------------------------------------------------ inicial -----
  // Só seleciona automaticamente quando o tipo vem na URL (?tipo=travessia).
  const inicial = new URLSearchParams(location.search).get("tipo");
  if (inicial && MODELOS.some((m) => m.id === inicial)) {
    selecionarModelo(inicial);
  } else {
    // Nenhum modelo escolhido: mantém o estado vazio com a instrução.
    previaArea.innerHTML = `<div class="vazio">
      <span class="emoji">📄</span>
      Escolha <strong>Travessia</strong> ou <strong>Desembargo</strong> ao lado para ver o documento.
    </div>`;
    statusPrevia.textContent = "nenhum modelo selecionado";
    document.querySelectorAll(".acoes .botao").forEach((botao) => {
      if (botao.id !== "btn-conferir") botao.disabled = true;
    });
  }
})();
