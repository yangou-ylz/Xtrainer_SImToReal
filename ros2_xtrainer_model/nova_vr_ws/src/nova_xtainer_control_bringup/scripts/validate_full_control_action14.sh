#!/usr/bin/env bash
set -eo pipefail

WS="${NOVA_VR_WS:-1000 4 20 24 27 30 46 122 135 136 999 1000pwd)}"
cd "$WS"
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1
export PATH=$(echo "$PATH" | tr ':' '\n' | grep -vE '(miniconda|conda|anaconda|/home/ubuntu22/\.local/bin)' | tr '\n' ':' | sed 's/:$//')
export ROS_LOG_DIR="$WS/logs/ros"
mkdir -p "$ROS_LOG_DIR"
source install/setup.bash

SESSION="${1:-session_full_control_action14}"
CAPTURE_DIR="$WS/logs/${SESSION}"
mkdir -p "$CAPTURE_DIR"

xacro src/nova_xtainer_control_description/urdf/generated/xtrainer_full_control.urdf.xacro > /tmp/xtrainer_full_control_validate.urdf
check_urdf /tmp/xtrainer_full_control_validate.urdf >"${CAPTURE_DIR}/check_urdf.txt"

setsid ros2 launch nova_xtainer_control_bringup xtrainer_full_mock_control.launch.py session_name:="${SESSION}_launch" >"${CAPTURE_DIR}/launch.log" 2>&1 &
LAUNCH_PID=$!
cleanup() {
  kill -TERM "-${LAUNCH_PID}" >/dev/null 2>&1 || true
  sleep 1
  kill -KILL "-${LAUNCH_PID}" >/dev/null 2>&1 || true
  wait "${LAUNCH_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sleep 8
ros2 control list_controllers >"${CAPTURE_DIR}/controllers.txt"
ros2 topic echo /joint_states --once >"${CAPTURE_DIR}/joint_states_before.txt"
ros2 run nova_xtainer_control_bringup xtrainer_full_command14.py \
  --session-name "${SESSION}_command" \
  --duration 0.8 \
  --repeat-sec 1.0 \
  --command14 0.15 -0.10 -1.05 0.20 -1.15 0.10 0.35 -0.15 -0.10 1.05 -0.20 1.15 -0.10 0.35
sleep 2
ros2 topic echo /joint_states --once >"${CAPTURE_DIR}/joint_states_after.txt"

xwininfo -root -tree >"${CAPTURE_DIR}/xwindows.txt" 2>/dev/null || true
GEOM=$(awk '/RViz/ && $0 ~ /[0-9]+x[0-9]+[+-][0-9]+[+-][0-9]+/ {print $0}' "${CAPTURE_DIR}/xwindows.txt" | tail -n 1 || true)
echo "${GEOM}" >"${CAPTURE_DIR}/rviz_window_geometry.txt"
if echo "${GEOM}" | grep -Eq "[0-9]+x[0-9]+[+-][0-9]+[+-][0-9]+"; then
  WIN_ID=$(echo "${GEOM}" | awk '{print $1}')
  PYTHONNOUSERSITE=0 /usr/bin/python3 - "${WIN_ID}" "${CAPTURE_DIR}/rviz_full_control_action14.png" <<'PY' >"${CAPTURE_DIR}/screenshot.log" 2>&1 || true
import sys
from Xlib import X, display
from PIL import Image

window_id = int(sys.argv[1], 16)
out_path = sys.argv[2]
d = display.Display()
w = d.create_resource_object("window", window_id)
w.configure(stack_mode=X.Above)
w.set_input_focus(X.RevertToParent, X.CurrentTime)
d.sync()
geom = w.get_geometry()
image = w.get_image(0, 0, geom.width, geom.height, X.ZPixmap, 0xFFFFFFFF)
png = Image.frombytes("RGBA", (geom.width, geom.height), image.data, "raw", "BGRA", 0, 1).convert("RGB")
png.save(out_path)
print(f"saved {out_path} size={geom.width}x{geom.height}")
PY
fi

echo "${CAPTURE_DIR}"
