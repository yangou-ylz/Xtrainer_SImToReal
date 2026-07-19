#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac

SESSION_NAME="${1:-session_phys40_lerobot_conversion_v1}"
INPUT_HDF5="${2:-datasets/raw_hdf5/pickcube_smoke_phys30.hdf5}"
OUTPUT_ROOT="${3:-datasets/lerobot/phys40_xtrainer_pickcube_smoke}"
REPO_ID="${4:-local/xtrainer_pickcube_smoke}"

PYTHONNOUSERSITE=1 conda run -n lerobot_xtrainer python "$ROOT/scripts/phys40_convert_hdf5_to_lerobot.py" \
  --session-name "$SESSION_NAME" \
  --input-hdf5 "$INPUT_HDF5" \
  --output-root "$OUTPUT_ROOT" \
  --repo-id "$REPO_ID" \
  --allow-smoke-unsuccessful \
  --overwrite

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS40_LEROBOT_CONVERSION" ]]; then
  echo "[phys40][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi
