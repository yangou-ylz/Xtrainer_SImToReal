#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys80_realtime_view_v1}"
STEPS="${2:-60}"
STEP_HZ="${3:-15}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys80_realtime_view.py" \
  --session-name "$SESSION_NAME" \
  --steps "$STEPS" \
  --step-hz "$STEP_HZ"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS80_REALTIME_VIEW" ]]; then
  echo "[phys80][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/multiview_realtime_final.png" ]]; then
  echo "[phys80][ERROR] missing final screenshot for $SESSION_NAME" >&2
  exit 21
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/realtime_view_report.json" ]]; then
  echo "[phys80][ERROR] missing realtime report for $SESSION_NAME" >&2
  exit 22
fi
