#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac

SESSION_NAME="${1:-session_phys100_endpoint_dataset_quality_v1}"
DATASET_FILE="${2:-datasets/raw_hdf5/phys93_endpoint_episode.hdf5}"
EXPORT_SESSION="${3:-session_phys93_endpoint_keyboard_record_v1_export}"

PY_ARGS=(
  --session-name "$SESSION_NAME" \
  --dataset-file "$DATASET_FILE" \
  --export-session "$EXPORT_SESSION"
)
if [[ "${PHYS100_SOFT_FAIL:-0}" == "1" ]]; then
  PY_ARGS+=(--no-raise-on-fail)
fi

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys100_endpoint_dataset_quality.py" "${PY_ARGS[@]}"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS100_ENDPOINT_DATASET_QUALITY" ]]; then
  if [[ -f "$ROOT/logs/$SESSION_NAME/FAIL_PHYS100_ENDPOINT_DATASET_QUALITY" ]]; then
    echo "[phys100] quality FAIL for $SESSION_NAME:" >&2
    sed -n '1,5p' "$ROOT/logs/$SESSION_NAME/FAIL_PHYS100_ENDPOINT_DATASET_QUALITY" >&2
    exit 20
  fi
  echo "[phys100][ERROR] missing quality PASS/FAIL marker for $SESSION_NAME" >&2
  exit 20
fi

for artifact in endpoint_dataset_quality_report.json endpoint_dataset_quality_report.md dataset_validation_report.md; do
  if [[ ! -s "$ROOT/logs/$SESSION_NAME/$artifact" ]]; then
    echo "[phys100][ERROR] missing artifact $artifact for $SESSION_NAME" >&2
    exit 21
  fi
done
