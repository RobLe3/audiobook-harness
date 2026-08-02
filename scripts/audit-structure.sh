#!/usr/bin/env bash
set -euo pipefail

# Read-only architectural audit.  CodeGraph requires a supported Node
# runtime; prefer the pinned local Node 20/22 installations over whatever the
# user's shell happens to expose.  Indexes and Sentrux baselines are local
# engineering artifacts, never production or publication evidence.
ROOT=$(cd "$(dirname "$0")/.." && pwd)
NODE_BIN=""
for candidate in "$HOME"/.nvm/versions/node/v22.*/bin "$HOME"/.nvm/versions/node/v20.20.2/bin; do
  if [[ -x "$candidate/node" ]]; then
    NODE_BIN="$candidate"
    break
  fi
done
if [[ -n "$NODE_BIN" ]]; then
  export PATH="$NODE_BIN:$PATH"
fi

if ! command -v codegraph >/dev/null 2>&1; then
  echo "codegraph is not installed; install it locally before running this audit." >&2
  exit 2
fi
if ! command -v sentrux >/dev/null 2>&1; then
  echo "sentrux is not installed; install it locally before running this audit." >&2
  exit 2
fi

if [[ ! -d "$ROOT/.codegraph" ]]; then
  echo "CodeGraph is not initialized. Run: codegraph init '$ROOT'" >&2
  exit 2
fi

echo "== CodeGraph status =="
codegraph status "$ROOT"
echo
echo "== Sentrux architectural rules =="
sentrux check "$ROOT"
echo
if [[ "${1:-}" == "--save-baseline" ]]; then
  echo "== Saving Sentrux baseline =="
  sentrux gate --save "$ROOT"
else
  echo "== Sentrux regression gate =="
  sentrux gate "$ROOT"
fi
