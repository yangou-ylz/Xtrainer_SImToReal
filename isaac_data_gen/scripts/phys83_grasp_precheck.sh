#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys83_grasp_precheck_v1}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys83_grasp_precheck.py" \
  --session-name "$SESSION_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS83_GRASP_PRECHECK" ]]; then
  echo "[phys83][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/grasp_precheck_report.json" ]]; then
  echo "[phys83][ERROR] missing report for $SESSION_NAME" >&2
  exit 21
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/final_lift_grid.png" ]]; then
  echo "[phys83][ERROR] missing final screenshot for $SESSION_NAME" >&2
  exit 22
fi
