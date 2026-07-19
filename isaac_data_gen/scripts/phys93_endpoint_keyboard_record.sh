#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys93_endpoint_keyboard_record_v1}"
DATASET_FILE="${2:-datasets/raw_hdf5/phys93_endpoint_episode.hdf5}"
MODE="${3:-interactive}"
HEADLESS_FLAG=()
MAX_STEPS=180
if [[ "$MODE" == "scripted" ]]; then
  HEADLESS_FLAG=(--headless --scripted-success)
else
  # Interactive collection should not auto-exit after the short scripted preflight.
  # Default: 108000 steps / 30Hz ~= 1 hour. Override with PHYS93_INTERACTIVE_MAX_STEPS.
  MAX_STEPS="${PHYS93_INTERACTIVE_MAX_STEPS:-108000}"
fi

mkdir -p "$ROOT/logs/$SESSION_NAME" "$ROOT/logs/${SESSION_NAME}_export"
rm -f \
  "$ROOT/logs/$SESSION_NAME/PASS_PHYS93_ENDPOINT_RECORDING_CORE" \
  "$ROOT/logs/$SESSION_NAME/PASS_PHYS93_ENDPOINT_RECORDING_PREFLIGHT" \
  "$ROOT/logs/$SESSION_NAME/FAIL_PHYS93_ENDPOINT_RECORDING_PREFLIGHT" \
  "$ROOT/logs/${SESSION_NAME}_export/PASS_PHYS90_HDF5_EXPORT_PREVIEW" \
  "$ROOT/logs/${SESSION_NAME}_export/FAIL_PHYS90_HDF5_EXPORT_PREVIEW"

if [[ "$MODE" == "interactive" ]]; then
  echo "[collect] Isaac will open with a live 3-camera preview."
  echo "[collect] Press B to START recording."
  echo "[collect] Press N to SAVE as success, Esc to SAVE as failure, C to CANCEL without saving."
  echo "[collect] max_steps=$MAX_STEPS. Normal end automatically exports videos and trajectories."
fi

set +e
conda run -n "$ENV_NAME" python "$ROOT/scripts/phys9_endpoint_keyboard_control.py" \
  --stage phys93 \
  --session-name "$SESSION_NAME" \
  --mode "$MODE" \
  "${HEADLESS_FLAG[@]}" \
  --seed 93 \
  --max-steps "$MAX_STEPS" \
  --dataset-file "$DATASET_FILE" \
  --overwrite
RUN_RC=$?
set -e

if [[ -f "$ROOT/logs/$SESSION_NAME/CANCEL_PHYS93_ENDPOINT_RECORDING" ]]; then
  echo "[collect] canceled: no dataset was saved and no export was generated."
  exit 0
fi

if [[ "$RUN_RC" -ne 0 ]]; then
  echo "[collect][ERROR] recording command failed, rc=$RUN_RC" >&2
  if [[ -f "$ROOT/logs/$SESSION_NAME/FAIL_PHYS93_ENDPOINT_RECORDING_PREFLIGHT" ]]; then
    echo "[collect][ERROR] reason:" >&2
    sed -n '1,20p' "$ROOT/logs/$SESSION_NAME/FAIL_PHYS93_ENDPOINT_RECORDING_PREFLIGHT" >&2
  fi
  exit "$RUN_RC"
fi

if [[ -f "$ROOT/logs/$SESSION_NAME/FAIL_PHYS93_ENDPOINT_RECORDING_PREFLIGHT" ]]; then
  echo "[collect][ERROR] recording failed:" >&2
  sed -n '1,20p' "$ROOT/logs/$SESSION_NAME/FAIL_PHYS93_ENDPOINT_RECORDING_PREFLIGHT" >&2
  exit 19
fi

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS93_ENDPOINT_RECORDING_CORE" ]]; then
  echo "[phys93][ERROR] missing core PASS marker for $SESSION_NAME" >&2
  exit 20
fi

echo "[collect] recording saved. Exporting videos and trajectories..."
bash "$ROOT/scripts/phys90_hdf5_export_preview.sh" "${SESSION_NAME}_export" "$DATASET_FILE" demo_0

if [[ ! -f "$ROOT/logs/${SESSION_NAME}_export/PASS_PHYS90_HDF5_EXPORT_PREVIEW" ]]; then
  echo "[phys93][ERROR] missing export PASS marker for $SESSION_NAME" >&2
  exit 21
fi

printf "PHYS-9.3 endpoint recording preflight passed\nrecord_session=%s\nexport_session=%s\n" "$SESSION_NAME" "${SESSION_NAME}_export" \
  > "$ROOT/logs/$SESSION_NAME/PASS_PHYS93_ENDPOINT_RECORDING_PREFLIGHT"

echo "[collect] done."
echo "[collect] hdf5: $ROOT/$DATASET_FILE"
echo "[collect] preview video: $ROOT/logs/${SESSION_NAME}_export/multiview.mp4"
echo "[collect] report: $ROOT/logs/$SESSION_NAME/endpoint_keyboard_record_report.md"
