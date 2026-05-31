#!/usr/bin/env bash
# agents installer — checks prereqs, installs Python deps, pulls minimum models.
# Usage:  ./install.sh        (full: deps + models)
#         ./install.sh --deps-only
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS_ONLY=0
[ "${1:-}" = "--deps-only" ] && DEPS_ONLY=1

info()  { printf '\033[36m==>\033[0m %s\n' "$1"; }
warn()  { printf '\033[33m!  \033[0m %s\n' "$1"; }
ok()    { printf '\033[32m✓  \033[0m %s\n' "$1"; }

# 1. Python
if ! command -v python3 >/dev/null 2>&1; then
  warn "python3 not found — install Python 3.10+ first: https://www.python.org"
  exit 1
fi
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
ok "Python ${PYV}"

# 2. Dependencies
info "Installing Python dependencies"
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -r "${REPO_DIR}/requirements.txt"
ok "Dependencies installed"

# 3. Ollama
if ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama not found — install from https://ollama.com then re-run for models"
else
  ok "Ollama present"
  if [ "${DEPS_ONLY}" -eq 0 ]; then
    if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
      warn "Ollama not running — start it with: ollama serve"
    else
      info "Pulling minimum models (fast + coder)"
      ollama pull qwen2.5:7b
      ollama pull qwen2.5-coder:32b
      ok "Models pulled"
    fi
  fi
fi

# 4. .env scaffold
if [ ! -f "${REPO_DIR}/.env" ] && [ -f "${REPO_DIR}/.env.example" ]; then
  cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
  ok "Created .env (add ANTHROPIC_API_KEY if you want the CLAUDE agent)"
fi

echo
ok "Done. Try:  ./run \"explain how a hash map works\""
info "Diagnose anytime with:  ./run --doctor"
