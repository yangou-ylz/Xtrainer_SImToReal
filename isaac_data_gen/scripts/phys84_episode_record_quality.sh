#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys84_episode_record_quality_v1}"
DATASET_FILE="${2:-datasets/raw_hdf5/pickcube_episode_phys84.hdf5}"
PRECHECK_REPORT="${3:-logs/session_phys83_grasp_precheck_v1/grasp_precheck_report.json}"
SEED="${4:-84}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys84_episode_record_quality.py" \
  --session-name "$SESSION_NAME" \
  --dataset-file "$DATASET_FILE" \
  --precheck-report "$PRECHECK_REPORT" \
  --seed "$SEED" \
  --overwrite

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS84_EPISODE_RECORD_QUALITY" ]]; then
  echo "[phys84][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

if [[ ! -s "$ROOT/$DATASET_FILE" ]]; then
  echo "[phys84][ERROR] missing dataset $DATASET_FILE" >&2
  exit 21
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/episode_quality_report.json" ]]; then
  echo "[phys84][ERROR] missing episode quality report for $SESSION_NAME" >&2
  exit 22
fi

if [[ ! -s "$ROOT/logs/$SESSION_NAME/demo_0_hdf5_last_grid.png" ]]; then
  echo "[phys84][ERROR] missing HDF5 image evidence for $SESSION_NAME" >&2
  exit 23
fi
