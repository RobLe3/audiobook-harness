#!/usr/bin/env sh
# Local repository verification. Never pulls images, packages, or models.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "Missing .venv; run: python scripts/setup.py --interactive" >&2
  exit 2
fi
"$PYTHON" -m pytest -q
"$PYTHON" -m ruff check src tests
if docker image inspect audiobook-harness:verify >/dev/null 2>&1; then
  EXPECTED_VERSION=$(PYTHONPATH="$ROOT/src" "$PYTHON" -m audiobook_harness.cli --version)
  IMAGE_REPORT=$(docker run --rm --network none audiobook-harness:verify doctor)
  IMAGE_VERSION=$(printf '%s' "$IMAGE_REPORT" | "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("version", ""))')
  if [ "$IMAGE_VERSION" = "$EXPECTED_VERSION" ]; then
    printf '%s\n' "$IMAGE_REPORT"
  else
    echo "Docker smoke skipped: local image is stale ($IMAGE_VERSION; checkout is $EXPECTED_VERSION)."
  fi
else
  echo "Docker smoke skipped: local audiobook-harness:verify image is not present."
fi
