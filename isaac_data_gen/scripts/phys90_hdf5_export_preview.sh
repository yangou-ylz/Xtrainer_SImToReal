#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac

SESSION_NAME="${1:-session_phys90_hdf5_export_preview_v1}"
DATASET_FILE="${2:-datasets/raw_hdf5/pickcube_episode_phys84.hdf5}"
DEMO_NAME="${3:-demo_0}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys90_hdf5_export_preview.py" \
  --session-name "$SESSION_NAME" \
  --dataset-file "$DATASET_FILE" \
  --demo-name "$DEMO_NAME"

if [[ ! -f "$ROOT/logs/$SESSION_NAME/PASS_PHYS90_HDF5_EXPORT_PREVIEW" ]]; then
  echo "[phys90][ERROR] missing PASS marker for $SESSION_NAME" >&2
  exit 20
fi

for artifact in top.mp4 left_wrist.mp4 right_wrist.mp4 multiview.mp4 joint_trajectory.csv trajectory.npz export_report.md; do
  if [[ ! -s "$ROOT/logs/$SESSION_NAME/$artifact" ]]; then
    echo "[phys90][ERROR] missing artifact $artifact for $SESSION_NAME" >&2
    exit 21
  fi
done
