#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys24_single_camera_smoke}"
CAMERA_NAME="${2:-top}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys24_single_camera_smoke.py" \
  --session-name "$SESSION_NAME" \
  --camera "$CAMERA_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS24_SINGLE_CAMERA_SMOKE" ]]; then
  echo "[phys24][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/camera_sample.png" ]]; then
  echo "[phys24][ERROR] missing camera_sample.png for $SESSION_NAME" >&2
  exit 21
fi
