#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys81_computer_control_v1}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys81_computer_control.py" \
  --session-name "$SESSION_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS81_COMPUTER_CONTROL" ]]; then
  echo "[phys81][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/computer_control_report.json" ]]; then
  echo "[phys81][ERROR] missing computer control report for $SESSION_NAME" >&2
  exit 21
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/after_control_grid.png" ]]; then
  echo "[phys81][ERROR] missing after-control screenshot for $SESSION_NAME" >&2
  exit 22
fi
