#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
use_china_pip_mirror

STAMP="$(timestamp)"
LOG_DIR="$LOG_ROOT/phys22_${STAMP}_install_leisaac"
LOG_FILE="$LOG_DIR/install_leisaac.log"
mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[phys22] root=$ROOT"
echo "[phys22] env=$ENV_NAME"
echo "[phys22] leisaac_source=$ROOT/external/x-trainer/source/leisaac"

if [[ ! -d "$ROOT/external/x-trainer/source/leisaac" ]]; then
  echo "[phys22][ERROR] missing source/leisaac"
  exit 2
fi

run_logged "$LOG_FILE" conda run -n "$ENV_NAME" python --version
run_logged "$LOG_FILE" conda run -n "$ENV_NAME" python -m pip install -e "$ROOT/external/x-trainer/source/leisaac"
run_logged "$LOG_FILE" conda run -n "$ENV_NAME" python -m pip show leisaac
run_logged "$LOG_FILE" conda run -n "$ENV_NAME" python -m pip check

touch "$LOG_DIR/PASS_PHYS22_LEISAAC_INSTALL"
echo "[phys22] PASS install"
echo "[phys22] log_dir=$LOG_DIR"
