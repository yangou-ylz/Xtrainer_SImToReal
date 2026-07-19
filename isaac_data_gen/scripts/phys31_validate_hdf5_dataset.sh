#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac

SESSION_NAME="${1:-session_phys31_hdf5_validation}"
DATASET_FILE="${2:-datasets/raw_hdf5/pickcube_smoke_phys30.hdf5}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/validate_hdf5_dataset.py" \
  "$DATASET_FILE" \
  --session-name "$SESSION_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS31_HDF5_VALIDATION" ]]; then
  echo "[phys31][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi
