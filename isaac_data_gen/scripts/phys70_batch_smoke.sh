#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

BATCH_NAME="${1:-session_phys70_batch_smoke_v1}"
SEED="${2:-70}"
PROFILE="${3:-minimal_pickcube}"

DATASET_FILE="datasets/raw_hdf5/${BATCH_NAME}.hdf5"
LEROBOT_ROOT="datasets/lerobot/${BATCH_NAME}"
REPO_ID="local/${BATCH_NAME}"
RECORD_SESSION="${BATCH_NAME}_record"
VALIDATE_SESSION="${BATCH_NAME}_validate"
CONVERT_SESSION="${BATCH_NAME}_convert"
QUALITY_SESSION="${BATCH_NAME}"
SESSION_DIR="$ROOT/logs/$BATCH_NAME"
mkdir -p "$SESSION_DIR"

{
  echo "PHYS-7 batch smoke"
  echo "root=$ROOT"
  echo "batch=$BATCH_NAME"
  echo "profile=$PROFILE"
  echo "seed=$SEED"
  echo "dataset=$DATASET_FILE"
  echo "lerobot_root=$LEROBOT_ROOT"
  echo "repo_id=$REPO_ID"
} | tee "$SESSION_DIR/batch_command.log"

bash "$ROOT/scripts/phys30_record_hdf5_smoke.sh" "$RECORD_SESSION" "$DATASET_FILE" "$SEED"
bash "$ROOT/scripts/phys31_validate_hdf5_dataset.sh" "$VALIDATE_SESSION" "$DATASET_FILE"
bash "$ROOT/scripts/phys40_convert_hdf5_to_lerobot.sh" "$CONVERT_SESSION" "$DATASET_FILE" "$LEROBOT_ROOT" "$REPO_ID"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys70_generate_quality_report.py" \
  --session-name "$QUALITY_SESSION" \
  --profile "$PROFILE" \
  --seed "$SEED" \
  --hdf5-file "$DATASET_FILE" \
  --validator-json "logs/$VALIDATE_SESSION/dataset_validation_report.json" \
  --lerobot-report-json "logs/$CONVERT_SESSION/lerobot_conversion_report.json"

if [[ ! -f "$ROOT/logs/$QUALITY_SESSION/PASS_PHYS70_BATCH_QUALITY_REPORT" ]]; then
  echo "[phys70][ERROR] missing PASS marker for $QUALITY_SESSION" >&2
  exit 20
fi
