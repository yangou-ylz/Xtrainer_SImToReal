#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required=(
  "README.md"
  "isaac_data_gen/scripts/common_env.sh"
  "isaac_data_gen/scripts/phys20_prepare_xtrainer_upstream.sh"
  "isaac_data_gen/scripts/phys21_sync_pickcube_assets.sh"
  "isaac_data_gen/src/phys_data_gen/action_mapping.py"
  "isaac_data_gen/docs/action_mapping.md"
  "isaac_data_gen/docs/data_schema.md"
  "ros2_xtrainer_model/nova_vr_ws/src/nova_xtainer_description/package.xml"
  "ros2_xtrainer_model/nova_vr_ws/src/nova_xtainer_description/urdf/generated/xtrainer_full_visual.urdf.xacro"
  "ros2_xtrainer_model/nova_vr_ws/src/nova_xtainer_control_description/package.xml"
  "ros2_xtrainer_model/nova_vr_ws/src/nova_xtainer_control_description/urdf/generated/xtrainer_full_control.urdf.xacro"
  "ros2_xtrainer_model/nova_vr_ws/src/nova_xtainer_control_bringup/package.xml"
)

for rel in "${required[@]}"; do
  if [[ ! -e "$ROOT/$rel" ]]; then
    echo "missing: $rel" >&2
    exit 2
  fi
done

PRIVATE_PATTERN='(re''search_|agent_''memory|\.pdf$)'
if find "$ROOT" -path "$ROOT/.git" -prune -o -type f -print | grep -E "$PRIVATE_PATTERN" >/dev/null; then
  echo "unexpected research/private files found" >&2
  exit 3
fi

echo "source tree OK"
