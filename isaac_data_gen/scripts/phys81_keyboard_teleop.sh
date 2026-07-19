#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

conda run -n "$ENV_NAME" python "$ROOT/external/x-trainer/scripts/environments/teleoperation/teleop_se3_agent.py" \
  --task=LeIsaac-XTrainer-PickCube-v0 \
  --teleop_device=bi_keyboard \
  --num_envs=1 \
  --device=cuda \
  --enable_cameras \
  --multi_view \
  --step_hz=30 \
  "$@"
