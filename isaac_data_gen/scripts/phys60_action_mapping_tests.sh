#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/common_env.sh"

require_project_root
load_conda
sanitize_for_isaac

SESSION_NAME="${1:-session_phys60_action_mapping_tests_v1}"
SESSION_DIR="$ROOT/logs/$SESSION_NAME"
mkdir -p "$SESSION_DIR"

PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" conda run -n "$ENV_NAME" \
  python -m pytest "$ROOT/tests/test_action_mapping.py" -q \
  2>&1 | tee "$SESSION_DIR/pytest.log"

touch "$SESSION_DIR/PASS_PHYS60_ACTION_MAPPING_TESTS"
