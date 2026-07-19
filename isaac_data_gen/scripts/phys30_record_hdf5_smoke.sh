#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys30_hdf5_smoke}"
DATASET_FILE="${2:-datasets/raw_hdf5/pickcube_smoke_phys30.hdf5}"
SEED="${3:-30}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys30_record_hdf5_smoke.py" \
  --session-name "$SESSION_NAME" \
  --dataset-file "$DATASET_FILE" \
  --seed "$SEED" \
  --overwrite

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS30_HDF5_SMOKE" ]]; then
  echo "[phys30][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

if [[ ! -s "$ROOT/$DATASET_FILE" ]]; then
  echo "[phys30][ERROR] missing dataset $DATASET_FILE" >&2
  exit 21
fi
