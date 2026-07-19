#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys92_endpoint_keyboard_preflight_v1}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys9_endpoint_keyboard_control.py" \
  --stage phys92 \
  --session-name "$SESSION_NAME" \
  --mode scripted \
  --headless \
  --seed 92 \
  --max-steps 120 \
  --scripted-success

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS92_ENDPOINT_KEYBOARD_PREFLIGHT" ]]; then
  echo "[phys92][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

for artifact in endpoint_keyboard_preflight_report.md endpoint_keyboard_preflight_report.json preflight_initial_grid.png preflight_final_grid.png; do
  if [[ ! -s "$ROOT/logs/$SESSION_NAME/$artifact" ]]; then
    echo "[phys92][ERROR] missing artifact $artifact for $SESSION_NAME" >&2
    exit 21
  fi
done
