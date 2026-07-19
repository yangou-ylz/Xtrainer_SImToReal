#!/usr/bin/env bash
set -eo pipefail

WS="${NOVA_VR_WS:-1000 4 20 24 27 30 46 122 135 136 999 1000pwd)}"
cd "$WS"
export PYTHONNOUSERSITE=1
export PATH=$(echo "$PATH" | tr ':' '\n' | grep -vE '(miniconda|conda|anaconda|/home/ubuntu22/\.local/bin)' | tr '\n' ':' | sed 's/:$//')
export ROS_LOG_DIR="$WS/logs/ros"
mkdir -p "$ROS_LOG_DIR"
source install/setup.bash

SESSION="${1:-session_dt4_dt7_validate}"
CAPTURE_DIR="$WS/logs/${SESSION}"
mkdir -p "$CAPTURE_DIR"

xacro src/nova_xtainer_control_description/urdf/xtrainer_control.urdf.xacro > /tmp/xtrainer_control_dt4_dt7.urdf
check_urdf /tmp/xtrainer_control_dt4_dt7.urdf >/tmp/xtrainer_control_dt4_dt7_check.log

setsid ros2 launch nova_xtainer_control_bringup xtrainer_dt4_ik_rviz.launch.py session_name:="${SESSION}_launch" >"${CAPTURE_DIR}/launch.log" 2>&1 &
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
ros2 run nova_xtainer_control_bringup send_dt4_right_ik_target.py --session-name "${SESSION}_dt4"
sleep 2
ros2 run nova_xtainer_control_bringup send_dt5_dual_ik_command.py --session-name "${SESSION}_dt5"
sleep 2
ros2 run nova_xtainer_control_bringup send_dt7_command14.py --backend mock_sim --session-name "${SESSION}_dt7_mock"
ros2 run nova_xtainer_control_bringup send_dt7_command14.py --backend xtrainer_dry_run --session-name "${SESSION}_dt7_dry"
ros2 topic echo /joint_states --once >"${CAPTURE_DIR}/joint_states_after_commands.txt"

GEOM=$(xwininfo -root -tree 2>/dev/null | awk '/RViz/ && $0 ~ /[0-9]+x[0-9]+[+-][0-9]+[+-][0-9]+/ {print $0}' | tail -n 1 || true)
echo "${GEOM}" > "${CAPTURE_DIR}/rviz_window_geometry.txt"
if echo "${GEOM}" | grep -Eq "[0-9]+x[0-9]+[+-][0-9]+[+-][0-9]+"; then
  SPEC=$(echo "${GEOM}" | grep -oE "[0-9]+x[0-9]+[+-][0-9]+[+-][0-9]+" | head -n 1)
  SIZE=${SPEC%%+*}
  POS=${SPEC#*+}
  X=${POS%%+*}
  Y=${POS#*+}
  ffmpeg -y -f x11grab -video_size "${SIZE}" -i "${DISPLAY:-:1}+${X},${Y}" -frames:v 1 "${CAPTURE_DIR}/rviz_dt4_dt7.png" >/dev/null 2>&1 || true
fi

echo "${CAPTURE_DIR}"
