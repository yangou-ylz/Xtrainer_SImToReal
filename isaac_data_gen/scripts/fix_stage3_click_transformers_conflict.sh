#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_env.sh
source "${SCRIPT_DIR}/common_env.sh"

cd "${PROJECT_ROOT}"
require_project_root
LOG_DIR="$(new_log_dir fix_click_transformers)"
LOG_FILE="${LOG_DIR}/fix_click_transformers.log"

load_conda
sanitize_for_isaac
use_china_pip_mirror
accept_omniverse_eula_for_process

{
  echo "# Stage 3 click/transformers dependency repair"
  echo "timestamp: $(date '+%F %T %Z')"
  echo "env_name: ${ENV_NAME}"
  echo "pip_index_url: ${PIP_INDEX_URL}"
  echo "scope: conda env only"
  echo "reason: Isaac Sim pins click==8.1.7; latest transformers/huggingface-hub/typer pulled click>=8.4"
  echo
} | tee "${LOG_FILE}"

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show click
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show transformers
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show huggingface-hub
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show typer

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip install "transformers==4.50.3" "huggingface-hub==0.36.0" "tokenizers==0.21.4" "typer==0.12.5" "click==8.1.7"

run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show click
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show transformers
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show huggingface-hub
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip show typer
run_logged "${LOG_FILE}" conda run -n "${ENV_NAME}" python -m pip check

touch "${LOG_DIR}/PASS_CLICK_TRANSFORMERS_FIX"
echo "PASS: click/transformers dependency conflict resolved. Log: ${LOG_FILE}" | tee -a "${LOG_FILE}"

