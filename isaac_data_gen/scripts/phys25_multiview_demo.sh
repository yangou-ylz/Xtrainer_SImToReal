#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys25_multiview_demo}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys25_multiview_demo.py" \
  --session-name "$SESSION_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS25_MULTIVIEW_DEMO" ]]; then
  echo "[phys25][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/multiview_grid.png" ]]; then
  echo "[phys25][ERROR] missing multiview_grid.png for $SESSION_NAME" >&2
  exit 21
fi
