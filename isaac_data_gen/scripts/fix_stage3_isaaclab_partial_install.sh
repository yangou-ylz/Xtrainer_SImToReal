#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir fix_isaaclab_partial)"
LOG_FILE="${LOG_DIR}/fix_isaaclab_partial.log"

load_conda
sanitize_for_isaac
use_china_pip_mirror
accept_omniverse_eula_for_process

{
  echo "# Stage 3 Isaac Lab partial install repair"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "env_name: ${ENV_NAME}"
  echo "pip_index_url: ${PIP_INDEX_URL}"
  echo "scope: conda env only"
  echo "issues:"
  echo "  - setuptools 82 no longer provides pkg_resources, breaking flatdict 4.0.1 isolated build"
  echo "  - ipython 9 pulled psutil>=7, conflicting with isaacsim-kernel psutil==5.9.8"
  echo
} | tee "${LOG_FILE}"

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show setuptools
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show psutil
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show ipython

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "setuptools==80.9.0"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -c "import pkg_resources; print('pkg_resources_ok', pkg_resources.__file__)"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install --no-build-isolation "flatdict==4.0.1"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "ipython<9" "psutil==5.9.8"

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show setuptools
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show flatdict
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show ipython
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show psutil
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip check

touch "${LOG_DIR}/PASS_ISAACLAB_PARTIAL_FIX"
echo "PASS: Isaac Lab partial install repaired. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"

