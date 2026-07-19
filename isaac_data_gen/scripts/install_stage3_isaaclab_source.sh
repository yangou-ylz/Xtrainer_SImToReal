#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir isaaclab_source)"
LOG_FILE="${LOG_DIR}/isaaclab_source.log"
ISAACLAB_DIR="${INSTALL_ROOT}/IsaacLab"
ISAACLAB_TAG="v2.3.0"

load_conda
sanitize_for_isaac
use_china_pip_mirror
accept_omniverse_eula_for_process

{
  echo "# Stage 3 Isaac Lab Source Install"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "env_name: ${ENV_NAME}"
  echo "isaaclab_tag: ${ISAACLAB_TAG}"
  echo "route: Isaac Lab source install on top of Isaac Sim 5.1 pip"
  echo "scope: project external directory + conda env only"
  echo "pip_index_url: ${PIP_INDEX_URL}"
  echo "eula: OMNI_KIT_ACCEPT_EULA=YES, authorized by user in chat"
  echo
} | tee "${LOG_FILE}"

if ! find "${LOG_ROOT}" -maxdepth 2 -name PASS_ISAACSIM_IMPORT | grep -q .; then
  echo "ERROR: Stage 3 requires Stage 2 Isaac Sim import verification first." | tee -a "${LOG_FILE}"
  echo "Run after user EULA confirmation: ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/verify_stage2_isaacsim.sh" | tee -a "${LOG_FILE}"
  touch "${LOG_DIR}/NEEDS_STAGE2_EULA_IMPORT"
  exit 20
fi

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python --version
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show isaacsim
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "setuptools==80.9.0"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -c "import pkg_resources; print('pkg_resources_ok', pkg_resources.__file__)"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install --no-build-isolation "flatdict==4.0.1"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "ipython<9" "psutil==5.9.8"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip check

if [[ -d "${ISAACLAB_DIR}/.git" ]]; then
  echo "INFO: IsaacLab repository already exists: ${ISAACLAB_DIR}" | tee -a "${LOG_FILE}"
  run_logged "${LOG_FILE}" git -C "${ISAACLAB_DIR}" status --short
  run_logged "${LOG_FILE}" git -C "${ISAACLAB_DIR}" rev-parse --short HEAD
  run_logged "${LOG_FILE}" git -C "${ISAACLAB_DIR}" describe --tags --always
else
  if [[ -e "${ISAACLAB_DIR}" ]]; then
    echo "ERROR: ${ISAACLAB_DIR} exists but is not a git repository. Refusing to overwrite." | tee -a "${LOG_FILE}"
    exit 21
  fi
  run_logged "${LOG_FILE}" git clone --depth 1 --branch "${ISAACLAB_TAG}" https://github.com/isaac-sim/IsaacLab.git "${ISAACLAB_DIR}"
fi

run_logged "${LOG_FILE}" git -C "${ISAACLAB_DIR}" rev-parse --short HEAD
run_logged "${LOG_FILE}" git -C "${ISAACLAB_DIR}" describe --tags --always
run_logged "${LOG_FILE}" bash -lc "cd '${ISAACLAB_DIR}' && conda run -n '${ENV_NAME}' ./isaaclab.sh --help"

# Install Isaac Lab extensions first, without optional RL/IL learning frameworks.
# This avoids robomimic/build-tool extras until the core Isaac Lab import path is verified.
run_logged "${LOG_FILE}" bash -lc "cd '${ISAACLAB_DIR}' && conda run -n '${ENV_NAME}' ./isaaclab.sh --install none"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "transformers==4.50.3" "huggingface-hub==0.36.0" "tokenizers==0.21.4" "typer==0.12.5" "click==8.1.7"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "psutil==5.9.8" "setuptools==80.9.0" "ipython<9"
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip check

touch "${LOG_DIR}/PASS_ISAACLAB_SOURCE_INSTALL"
echo "PASS: Isaac Lab source install completed. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
