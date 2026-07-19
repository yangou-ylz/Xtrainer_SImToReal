#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir fix_wheel_packaging)"
LOG_FILE="${LOG_DIR}/fix_wheel_packaging.log"

load_conda
sanitize_for_isaac

{
  echo "# Stage 2 wheel/packaging conflict fix"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "env_name: ${ENV_NAME}"
  echo "reason: Isaac Sim pins packaging==23.0, while conda-provided wheel 0.46.3 requires packaging>=24.0"
  echo "scope: conda env only"
  echo
} | tee "${LOG_FILE}"

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show packaging
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show wheel
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "wheel==0.45.1"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show packaging
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show wheel
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip check

touch "${LOG_DIR}/PASS_WHEEL_PACKAGING_FIX"
echo "PASS: wheel/packaging conflict resolved. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"

