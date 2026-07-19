#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys82_gui_keyboard_preflight_v1}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys82_gui_keyboard_preflight.py" \
  --session-name "$SESSION_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS82_GUI_KEYBOARD_PREFLIGHT" ]]; then
  echo "[phys82][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/gui_preflight_cameras_grid.png" ]]; then
  echo "[phys82][ERROR] missing camera grid for $SESSION_NAME" >&2
  exit 21
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/gui_keyboard_preflight_report.json" ]]; then
  echo "[phys82][ERROR] missing report for $SESSION_NAME" >&2
  exit 22
fi
