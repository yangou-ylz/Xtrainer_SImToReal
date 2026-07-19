#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

STAMP="$(date '+%Y%m%d_%H%M%S')"
SESSION_NAME="${1:-session_user_collect_${STAMP}}"
DATASET_FILE="${2:-datasets/raw_hdf5/user_episode_${STAMP}.hdf5}"
QUALITY_SESSION="${SESSION_NAME}_quality"

echo "============================================================"
echo "X-Trainer episode collection"
echo "============================================================"
echo "Session : $SESSION_NAME"
echo "Dataset : $ROOT/$DATASET_FILE"
echo ""
echo "Controls:"
echo "  B      start recording"
echo "  N      save as success and finish"
echo "  Esc    save as failure and finish"
echo "  C      cancel without saving"
echo "  1 / 2  slow / normal speed"
echo ""

bash "$ROOT/scripts/phys93_endpoint_keyboard_record.sh" "$SESSION_NAME" "$DATASET_FILE" interactive

if [[ -f "$ROOT/logs/$SESSION_NAME/CANCEL_PHYS93_ENDPOINT_RECORDING" ]]; then
  echo "Collection canceled. Nothing was exported."
  exit 0
fi

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS93_ENDPOINT_RECORDING_PREFLIGHT" ]]; then
  echo "[collect][ERROR] recording did not finish cleanly. See: $ROOT/logs/$SESSION_NAME/error.log" >&2
  exit 20
fi

echo ""
echo "Running quality gate..."
set +e
PHYS100_SOFT_FAIL=1 bash "$ROOT/scripts/phys100_endpoint_dataset_quality.sh" "$QUALITY_SESSION" "$DATASET_FILE" "${SESSION_NAME}_export"
QUALITY_RC=$?
set -e

echo ""
echo "Recording   : PASS"
echo "Export      : PASS"
if [[ "$QUALITY_RC" -eq 0 ]]; then
  echo "Quality     : PASS"
else
  echo "Quality     : FAIL"
  if [[ -f "$ROOT/logs/$QUALITY_SESSION/FAIL_PHYS100_ENDPOINT_DATASET_QUALITY" ]]; then
    QUALITY_ISSUE="$(sed -n '1p' "$ROOT/logs/$QUALITY_SESSION/FAIL_PHYS100_ENDPOINT_DATASET_QUALITY")"
    echo "Quality issue : $QUALITY_ISSUE"
    if [[ "$QUALITY_ISSUE" == *"right gripper range too small"* ]]; then
      echo "Hint          : 数据已经保存，但没有检测到右夹爪开合。下次采集请按 G，并确认终端出现 [gripper] toggled。"
    fi
  fi
fi
echo "Saved data is still available even when Quality is FAIL."
echo "HDF5        : $ROOT/$DATASET_FILE"
echo "Multi-view  : $ROOT/logs/${SESSION_NAME}_export/multiview.mp4"
echo "Quality     : $ROOT/logs/$QUALITY_SESSION/endpoint_dataset_quality_report.md"
echo "Trajectory  : $ROOT/logs/${SESSION_NAME}_export/trajectory.npz"
echo "Run log     : $ROOT/logs/$SESSION_NAME/run.log"
echo "Data log    : $ROOT/logs/$SESSION_NAME/data.log"

exit 0
