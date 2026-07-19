#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir isaacsim_pip)"
LOG_FILE="${LOG_DIR}/isaacsim_pip.log"

load_conda
sanitize_for_isaac

{
  echo "# Stage 2 Isaac Sim Pip Install"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "env_name: ${ENV_NAME}"
  echo "route: Isaac Sim 5.1 pip + PyTorch cu128 per Isaac Lab docs"
  echo "note: this script installs packages only; it does not set OMNI_KIT_ACCEPT_EULA"
  echo
} | tee "${LOG_FILE}"

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python --version
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install --upgrade pip
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install -U torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show isaacsim
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"

PASS_FILE="${LOG_DIR}/PASS_ISAACSIM_PIP_INSTALL"
touch "${PASS_FILE}"
echo "PASS: Isaac Sim pip packages installed. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"

