#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir preflight)"
LOG_FILE="${LOG_DIR}/preflight.log"

{
  echo "# Preflight Check"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "project_root: ${PROJECT_ROOT}"
  echo "env_name: ${ENV_NAME}"
  echo
} | tee "${LOG_FILE}"

run_logged "${LOG_FILE}" nvidia-smi
run_logged "${LOG_FILE}" nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
run_logged "${LOG_FILE}" bash -lc "lsb_release -a 2>/dev/null || true"
run_logged "${LOG_FILE}" uname -a
run_logged "${LOG_FILE}" free -h
run_logged "${LOG_FILE}" df -h "${PROJECT_ROOT}" "${HOME}"
run_logged "${LOG_FILE}" bash -lc "ldd --version | head -1"
run_logged "${LOG_FILE}" bash -lc "which nvcc || true; nvcc --version 2>/dev/null || true"

load_conda
run_logged "${LOG_FILE}" conda env list
run_logged "${LOG_FILE}" conda info

{
  echo
  echo "## Shell isolation variables"
  echo "CONDA_PREFIX=${CONDA_PREFIX-}"
  echo "ROS_DISTRO=${ROS_DISTRO-}"
  echo "LD_LIBRARY_PATH=${LD_LIBRARY_PATH-}"
  echo "PYTHONPATH=${PYTHONPATH-}"
  echo "PATH entries:"
  echo "${PATH}" | tr ':' '\n'
} | tee -a "${LOG_FILE}"

PASS_FILE="${LOG_DIR}/PASS_PRECHECK"
touch "${PASS_FILE}"
echo "PASS: preflight completed. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
