#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XTRAINER="$ROOT/external/x-trainer"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$ROOT/logs/phys20_${STAMP}_audit_xtrainer"
LOG="$LOG_DIR/audit.log"

mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG") 2>&1

echo "[phys20] root=$ROOT"
echo "[phys20] xtrainer=$XTRAINER"

if [[ ! -d "$XTRAINER" ]]; then
  echo "[phys20][ERROR] missing $XTRAINER"
  exit 2
fi

required_files=(
  README.md
  README.zh.md
  LICENSE
  source/leisaac/pyproject.toml
  source/leisaac/leisaac/__init__.py
  source/leisaac/leisaac/tasks/__init__.py
  source/leisaac/leisaac/tasks/pick_cube/__init__.py
  source/leisaac/leisaac/tasks/pick_cube/xtrainer_pick_cube_env_cfg.py
  source/leisaac/leisaac/assets/robots/xtrainer.py
  source/leisaac/leisaac/devices/action_process.py
  source/leisaac/leisaac/devices/keyboard/bi_keyboard.py
  scripts/environments/list_envs.py
  scripts/environments/teleoperation/teleop_se3_agent.py
  scripts/convert/isaaclab2lerobot_xtrainer.py
  assets/robots/x_trainer.usd
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$XTRAINER/$file" ]]; then
    echo "[phys20][ERROR] missing required file: $file"
    exit 3
  fi
  echo "[phys20] found $file"
done

{
  echo "# PHYS-2.0 X-Trainer Upstream Audit"
  echo
  echo "date: $(date -Iseconds)"
  echo "path: $XTRAINER"
  echo
  echo "## Key files"
  for file in "${required_files[@]}"; do
    size="$(du -h "$XTRAINER/$file" | awk '{print $1}')"
    echo "- $file ($size)"
  done
  echo
  echo "## Version facts"
  grep -E "Isaac Sim|Isaac Lab|Python|version =|isaaclab" "$XTRAINER/README.md" "$XTRAINER/source/leisaac/pyproject.toml" || true
  echo
  echo "## Registered XTrainer tasks"
  grep -R "LeIsaac-XTrainer" "$XTRAINER/source/leisaac/leisaac/tasks" "$XTRAINER/scripts" || true
  echo
  echo "## Action and data schema hooks"
  grep -R "J1_7\\|J1_8\\|left_joint_pos_rel\\|right_joint_pos_rel\\|obs/top\\|obs/left_wrist\\|obs/right_wrist" \
    "$XTRAINER/source/leisaac/leisaac" "$XTRAINER/scripts/convert/isaaclab2lerobot_xtrainer.py" || true
} > "$LOG_DIR/upstream_audit.md"

find "$XTRAINER" -maxdepth 4 -type f | sed "s#^$XTRAINER/##" | sort > "$LOG_DIR/file_manifest_depth4.txt"

touch "$LOG_DIR/PASS_PHYS20_XTRAINER_UPSTREAM"
echo "[phys20] PASS audit"
echo "[phys20] log_dir=$LOG_DIR"
