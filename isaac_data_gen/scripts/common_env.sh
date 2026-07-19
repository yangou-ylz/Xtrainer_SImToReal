#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="xtrainer_VLA"
LOG_ROOT="${PROJECT_ROOT}/logs"
INSTALL_ROOT="${PROJECT_ROOT}/external"
ASSET_ROOT="${PROJECT_ROOT}/assets"
PYPI_MIRROR_URL="${PYPI_MIRROR_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
NVIDIA_PYPI_URL="${NVIDIA_PYPI_URL:-https://pypi.nvidia.cn}"

mkdir -p "${LOG_ROOT}" "${INSTALL_ROOT}" "${ASSET_ROOT}"

timestamp() {
  date '+%Y%m%d_%H%M%S'
}

new_log_dir() {
  local name="$1"
  local dir="${LOG_ROOT}/install_$(timestamp)_${name}"
  mkdir -p "${dir}"
  printf '%s\n' "${dir}"
}

require_project_root() {
  local cwd
  cwd="$(pwd)"
  if [[ "${cwd}" != "${PROJECT_ROOT}"* ]]; then
    echo "ERROR: current directory must be inside ${PROJECT_ROOT}, got ${cwd}" >&2
    exit 2
  fi
}

load_conda() {
  if [[ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck source=/dev/null
    source "${HOME}/miniconda3/etc/profile.d/conda.sh"
  elif [[ -f "${HOME}/anaconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck source=/dev/null
    source "${HOME}/anaconda3/etc/profile.d/conda.sh"
  else
    echo "ERROR: conda.sh not found under ~/miniconda3 or ~/anaconda3" >&2
    exit 3
  fi
}

sanitize_for_isaac() {
  unset ROS_DISTRO || true
  unset ROS_VERSION || true
  unset ROS_PYTHON_VERSION || true
  unset AMENT_PREFIX_PATH || true
  unset COLCON_PREFIX_PATH || true
  unset ROS_PACKAGE_PATH || true
  unset CMAKE_PREFIX_PATH || true
  unset PYTHONPATH || true

  if [[ -n "${LD_LIBRARY_PATH-}" ]]; then
    LD_LIBRARY_PATH="$(echo "${LD_LIBRARY_PATH}" | tr ':' '\n' | grep -vE 'cuda12-compat|isaacgym|/opt/ros|ws_ros2' | tr '\n' ':' | sed 's/:$//')"
    export LD_LIBRARY_PATH
  fi

  PATH="$(echo "${PATH}" | tr ':' '\n' | grep -vE '/opt/ros|ws_ros2|cuda12-compat|isaacgym' | awk '!seen[$0]++' | tr '\n' ':' | sed 's/:$//')"
  export PATH
}

use_china_pip_mirror() {
  export PIP_INDEX_URL="${PYPI_MIRROR_URL}"
  export PIP_TRUSTED_HOST="pypi.tuna.tsinghua.edu.cn pypi.nvidia.cn"
}

accept_omniverse_eula_for_process() {
  export OMNI_KIT_ACCEPT_EULA=YES
}

assert_no_system_mutation_command() {
  local cmd="$*"
  if [[ "${cmd}" =~ (^|[[:space:]])sudo($|[[:space:]]) ]]; then
    echo "ERROR: sudo is forbidden for this install workflow" >&2
    exit 10
  fi
  if [[ "${cmd}" =~ (^|[[:space:]])apt(-get)?($|[[:space:]]) ]]; then
    echo "ERROR: apt/apt-get is forbidden for this install workflow" >&2
    exit 11
  fi
  if [[ "${cmd}" =~ rm[[:space:]]+-rf[[:space:]]+/ ]]; then
    echo "ERROR: dangerous rm -rf / pattern is forbidden" >&2
    exit 12
  fi
  if [[ "${cmd}" =~ conda[[:space:]]+clean[[:space:]].*--all ]]; then
    echo "ERROR: conda clean --all is forbidden" >&2
    exit 13
  fi
}

run_logged() {
  local log_file="$1"
  shift
  assert_no_system_mutation_command "$@"
  {
    echo ">>> $(date '+%F %T %Z')"
    echo ">>> cwd=$(pwd)"
    echo ">>> cmd=$*"
    "$@"
  } 2>&1 | tee -a "${log_file}"
}
