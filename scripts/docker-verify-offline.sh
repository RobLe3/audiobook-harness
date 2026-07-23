#!/usr/bin/env sh
# Run a fully provisioned local project in the verification image with networking disabled.
# The mounted tools directory must contain Linux-compatible Kokoro, Whisper and MFA assets.
set -eu
TOOLS_DIR=${1:?usage: scripts/docker-verify-offline.sh /path/to/linux-tools /path/to/project [command]}
PROJECT_DIR=${2:?usage: scripts/docker-verify-offline.sh /path/to/linux-tools /path/to/project [command]}
COMMAND=${3:-verify}
docker run --rm --network none \
  -v "$TOOLS_DIR:/app/.tools:ro" \
  -v "$PROJECT_DIR:/work/project" \
  audiobook-harness:verify "$COMMAND" /work/project
