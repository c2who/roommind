#!/usr/bin/env bash
# Build RoomMind and copy the integration into a local Home Assistant config.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_COMPONENT_DIR="/home/christian/docker/homeassistant/homeassistant-config/config/custom_components/roommind"
COMPONENT_DIR="${1:-${LOCAL_COMPONENT_DIR:-$DEFAULT_COMPONENT_DIR}}"

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [destination-component-directory]" >&2
  exit 2
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required for local deployment." >&2
  exit 1
fi

# Vite 8 needs Node 20+. Use the local nvm installation when the shell's
# default Node is older (or npm is unavailable).
NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || true)"
if [[ -z "$NODE_MAJOR" || "$NODE_MAJOR" -lt 20 ]] || ! command -v npm >/dev/null 2>&1; then
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
    echo "Node.js 20+ and npm are required to build the frontend." >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  source "$NVM_DIR/nvm.sh"
  nvm use 20 >/dev/null
fi

echo "==> Building RoomMind frontend"
(cd "$SCRIPT_DIR/frontend" && npm run build --silent)

echo "==> Copying RoomMind to $COMPONENT_DIR"
mkdir -p -- "$COMPONENT_DIR"

# Home Assistant may own its __pycache__ directories. Leave them in place;
# Python invalidates bytecode when the corresponding source changes. Copy only
# integration source, metadata, brand assets and the built frontend bundle.
rsync -a --prune-empty-dirs \
  --exclude='__pycache__/' \
  --include='*/' \
  --include='*.py' \
  --include='*.json' \
  --include='*.js' \
  --include='*.png' \
  --include='*.svg' \
  --exclude='*' \
  "$SCRIPT_DIR/custom_components/roommind/" "$COMPONENT_DIR/"

echo "==> Done. Reload the RoomMind integration for Python changes; hard-refresh your browser for frontend changes."
echo "    Restart Home Assistant for manifest or WebSocket schema changes."
