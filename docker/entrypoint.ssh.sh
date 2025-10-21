#!/usr/bin/env bash
set -euo pipefail

# Ensure expected directories (can be bind-mounted by SSH trainer)
mkdir -p /workspace/qcraft/configs
mkdir -p /workspace/qcraft/outputs

# If user passed an explicit Python invocation, honor it. Otherwise run the QCraft training entrypoint.
if [[ "${1:-}" == "python" || "${1:-}" == "python3" ]]; then
  exec "$@"
else
  exec python3 -m cloud.training_entrypoint "$@"
fi
