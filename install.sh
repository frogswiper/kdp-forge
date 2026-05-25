#!/usr/bin/env bash
# kdp-forge one-shot installer.
#
#   curl -fsSL https://raw.githubusercontent.com/frogswiper/kdp-forge/main/install.sh | bash
#
# Or, with a target directory:
#
#   curl -fsSL https://raw.githubusercontent.com/frogswiper/kdp-forge/main/install.sh \
#     | KDP_FORGE_DIR=$HOME/apps/kdp-forge bash
#
# Requires: git, docker, docker compose. Ollama running locally is optional (AI
# features need it, everything else works without).

set -euo pipefail

REPO="https://github.com/frogswiper/kdp-forge.git"
DIR="${KDP_FORGE_DIR:-$HOME/kdp-forge}"
PORT="${SITE_PORT:-2005}"
HOST="${SITE_HOST:-localhost}"

step() { printf "\n\033[1;36m▶\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; exit 1; }

command -v git >/dev/null || die "git is required"
command -v docker >/dev/null || die "docker is required"
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"

step "Cloning into $DIR"
if [[ -d "$DIR/.git" ]]; then
  warn "$DIR already exists — pulling latest"
  git -C "$DIR" pull --ff-only
else
  git clone "$REPO" "$DIR"
fi

cd "$DIR"

step "Writing .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  sed -i.bak "s|^SITE_HOST=.*|SITE_HOST=$HOST|" .env && rm .env.bak
  sed -i.bak "s|^SITE_PORT=.*|SITE_PORT=$PORT|" .env && rm .env.bak
  echo "  → wrote .env (SITE_HOST=$HOST SITE_PORT=$PORT)"
else
  echo "  → .env already exists, leaving as-is"
fi

step "Building & starting containers"
docker compose up -d --build

step "Waiting for service…"
for i in $(seq 1 30); do
  if curl -sk -o /dev/null -w '%{http_code}' "https://${HOST}:${PORT}/health" | grep -q 200; then
    break
  fi
  sleep 1
done

step "Done"
cat <<EOF

  kdp-forge is running.

  → Web:    https://${HOST}:${PORT}
  → Health: https://${HOST}:${PORT}/health
  → Source: $DIR

  Self-signed TLS — accept the certificate warning in your browser.

  Next steps:
    1. Make sure Ollama is reachable from the container (\`OLLAMA_HOST=0.0.0.0\`
       in your Ollama service env if you're on Linux).
    2. Visit the URL above, upload a manuscript, and follow ONBOARDING.md.

EOF
