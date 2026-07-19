#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys23_no_camera_smoke}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys23_no_camera_smoke.py" --session-name "$SESSION_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS23_NO_CAMERA_SMOKE" ]]; then
  echo "[phys23][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi
