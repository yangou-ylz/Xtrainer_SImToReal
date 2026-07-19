#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir create_env)"
LOG_FILE="${LOG_DIR}/create_env.log"

load_conda
sanitize_for_isaac

{
  echo "# Create Fresh Conda Env"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "env_name: ${ENV_NAME}"
  echo "policy: create conda env ${ENV_NAME}; overwrite only when RESET_XTRAINER_ENV=1"
  echo
} | tee "${LOG_FILE}"

if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
  if [[ "${RESET_XTRAINER_ENV:-0}" == "1" ]]; then
    run_logged "${LOG_FILE}" conda env remove -n "${ENV_NAME}" -y
  else
    echo "INFO: conda env ${ENV_NAME} already exists. Set RESET_XTRAINER_ENV=1 to recreate it." | tee -a "${LOG_FILE}"
    run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python --version
    touch "${LOG_DIR}/PASS_CREATE_ENV"
    exit 0
  fi
fi

run_logged "${LOG_FILE}" conda create -n "${ENV_NAME}" python=3.11 -y
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python --version
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip --version
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -c "import sys; print(sys.executable); assert sys.version_info[:2] == (3, 11)"

PASS_FILE="${LOG_DIR}/PASS_CREATE_ENV"
touch "${PASS_FILE}"
echo "PASS: fresh conda env created. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
