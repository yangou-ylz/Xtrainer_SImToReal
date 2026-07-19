#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys100_endpoint_collection_baseline_v1}"
DATASET_FILE="${2:-datasets/raw_hdf5/phys100_endpoint_collection_baseline.hdf5}"
QUALITY_SESSION="${SESSION_NAME}_quality"

bash "$ROOT/scripts/phys93_endpoint_keyboard_record.sh" "$SESSION_NAME" "$DATASET_FILE" scripted
bash "$ROOT/scripts/phys100_endpoint_dataset_quality.sh" "$QUALITY_SESSION" "$DATASET_FILE" "${SESSION_NAME}_export"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS93_ENDPOINT_RECORDING_PREFLIGHT" ]]; then
  echo "[phys100][ERROR] missing PHYS-9.3 baseline PASS marker for $SESSION_NAME" >&2
  exit 30
fi
if [[ ! -f "$ROOT/logs/$QUALITY_SESSION/PASS_PHYS100_ENDPOINT_DATASET_QUALITY" ]]; then
  echo "[phys100][ERROR] missing PHYS-10 quality PASS marker for $QUALITY_SESSION" >&2
  exit 31
fi

printf "PHYS-10.0 endpoint collection baseline passed\nrecord_session=%s\nquality_session=%s\ndataset=%s\n" \
  "$SESSION_NAME" "$QUALITY_SESSION" "$DATASET_FILE" \
  > "$ROOT/logs/$SESSION_NAME/PASS_PHYS100_ENDPOINT_COLLECTION_BASELINE"
