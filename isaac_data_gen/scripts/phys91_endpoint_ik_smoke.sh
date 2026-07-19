#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys91_endpoint_ik_smoke_v1}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys91_endpoint_ik_smoke.py" \
  --session-name "$SESSION_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS91_ENDPOINT_IK_SMOKE" ]]; then
  echo "[phys91][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

for artifact in endpoint_ik_report.md endpoint_ik_report.json initial_grid.png final_grid.png; do
  if [[ ! -s "$ROOT/logs/$SESSION_NAME/$artifact" ]]; then
    echo "[phys91][ERROR] missing artifact $artifact for $SESSION_NAME" >&2
    exit 21
  fi
done
