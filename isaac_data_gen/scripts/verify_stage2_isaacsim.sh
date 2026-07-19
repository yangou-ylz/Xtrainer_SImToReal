#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir verify_isaacsim)"
LOG_FILE="${LOG_DIR}/verify_isaacsim.log"

load_conda
sanitize_for_isaac

{
  echo "# Stage 2 Isaac Sim Verification"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "env_name: ${ENV_NAME}"
  echo "note: import/package verification only; this does not launch SimulationApp or accept EULA"
  echo
} | tee "${LOG_FILE}"

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python --version
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show isaacsim
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show isaacsim-kernel
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show torch
if [[ "${ACCEPT_NVIDIA_OMNIVERSE_EULA:-NO}" == "YES" ]]; then
  export OMNI_KIT_ACCEPT_EULA=YES
  run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -c "import isaacsim; print('isaacsim_import_ok', isaacsim.__file__)"
  run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -c "from isaacsim import SimulationApp; print('simulation_app_symbol_ok', SimulationApp)"
  touch "${LOG_DIR}/PASS_ISAACSIM_IMPORT"
else
  touch "${LOG_DIR}/NEEDS_EULA_CONFIRMATION"
  echo "SKIP: Isaac Sim import requires NVIDIA Omniverse EULA acceptance." | tee -a "${LOG_FILE}"
  echo "To run import verification after user confirmation: ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/verify_stage2_isaacsim.sh" | tee -a "${LOG_FILE}"
fi
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'); x=torch.ones((4,4), device='cuda'); print('cuda_tensor_sum', float(x.sum().cpu()))"

if conda run -n "${ENV_NAME}" python -m pip check 2>&1 | tee -a "${LOG_FILE}"; then
  touch "${LOG_DIR}/PASS_PIP_CHECK"
else
  touch "${LOG_DIR}/WARN_PIP_CHECK"
  echo "WARN: pip check reported dependency issues; inspect log before Stage 3." | tee -a "${LOG_FILE}"
fi

if [[ -f "${LOG_DIR}/PASS_ISAACSIM_IMPORT" ]]; then
  echo "PASS: Isaac Sim import verification completed. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
else
  echo "PARTIAL: package and torch verification completed; Isaac Sim import is gated on EULA confirmation. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"
fi
