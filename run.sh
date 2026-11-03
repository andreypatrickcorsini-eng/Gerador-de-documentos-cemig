#!/usr/bin/env bash
# Sobe o Gerador de Documentos CEMIG criando o ambiente virtual se necessário.
set -euo pipefail

cd "$(dirname "$0")"

PORTA="${PORT:-8000}"

if [ ! -d .venv ]; then
  echo "› criando ambiente virtual (.venv)…"
  python3 -m venv .venv
fi

if ! .venv/bin/python -c "import flask, docx, reportlab" >/dev/null 2>&1; then
  echo "› instalando dependências…"
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

echo "› Gerador de Documentos CEMIG em http://localhost:${PORTA}"
exec .venv/bin/python app.py
