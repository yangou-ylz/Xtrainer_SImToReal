#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac
accept_omniverse_eula_for_process

SESSION_NAME="${1:-session_phys22_leisaac_registry}"

conda run -n "$ENV_NAME" python "$ROOT/scripts/phys22_verify_leisaac_registry.py" --session-name "$SESSION_NAME"
