#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir verify_isaaclab)"
LOG_FILE="${LOG_DIR}/verify_isaaclab.log"
ISAACLAB_DIR="${INSTALL_ROOT}/IsaacLab"

load_conda
sanitize_for_isaac

{
  echo "# Stage 3 Isaac Lab Verification"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "env_name: ${ENV_NAME}"
  echo "isaaclab_dir: ${ISAACLAB_DIR}"
  echo
} | tee "${LOG_FILE}"

if [[ ! -d "${ISAACLAB_DIR}/.git" ]]; then
  echo "ERROR: IsaacLab repository not found at ${ISAACLAB_DIR}" | tee -a "${LOG_FILE}"
  exit 30
fi

if [[ "${ACCEPT_NVIDIA_OMNIVERSE_EULA:-NO}" != "YES" ]]; then
  touch "${LOG_DIR}/NEEDS_EULA_CONFIRMATION"
  echo "ERROR: Isaac Lab verification can launch/import Isaac Sim components and requires NVIDIA Omniverse EULA confirmation." | tee -a "${LOG_FILE}"
  echo "Run after user confirmation: ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/verify_stage3_isaaclab.sh" | tee -a "${LOG_FILE}"
  exit 31
fi

accept_omniverse_eula_for_process

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python --version
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show isaacsim
run_logged "${LOG_FILE}" bash -lc "cd '${ISAACLAB_DIR}' && timeout 300s conda run -n '${ENV_NAME}' ./isaaclab.sh -p '${PROJECT_ROOT}/scripts/verify_stage3_isaaclab_smoke.py'"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip check

touch "${LOG_DIR}/PASS_ISAACLAB_VERIFY"
echo "PASS: Isaac Lab verification completed. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
