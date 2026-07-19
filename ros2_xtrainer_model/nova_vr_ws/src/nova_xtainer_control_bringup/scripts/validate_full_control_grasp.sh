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

SESSION="${1:-session_full_control_grasp}"
GUI="${2:-false}"
CAPTURE_DIR="$WS/logs/${SESSION}"
mkdir -p "$CAPTURE_DIR"
PORT=$((12000 + ($$ % 20000)))
GAZEBO_MASTER_URI="http://127.0.0.1:${PORT}"
echo "${GAZEBO_MASTER_URI}" >"${CAPTURE_DIR}/gazebo_master_uri.txt"

xacro src/nova_xtainer_control_description/urdf/generated/xtrainer_full_control.urdf.xacro hardware_plugin:=gazebo_ros2_control/GazeboSystem > /tmp/xtrainer_full_control_grasp_validate.urdf
check_urdf /tmp/xtrainer_full_control_grasp_validate.urdf >"${CAPTURE_DIR}/check_urdf.txt"

setsid ros2 launch nova_xtainer_control_bringup xtrainer_full_control_gazebo.launch.py gui:="${GUI}" rviz:=false gazebo_master_uri:="${GAZEBO_MASTER_URI}" >"${CAPTURE_DIR}/launch.log" 2>&1 &
LAUNCH_PID=$!
cleanup() {
  kill -TERM "-${LAUNCH_PID}" >/dev/null 2>&1 || true
  sleep 1
  kill -KILL "-${LAUNCH_PID}" >/dev/null 2>&1 || true
  wait "${LAUNCH_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sleep 28
ros2 control list_controllers >"${CAPTURE_DIR}/controllers.txt"
ros2 service list >"${CAPTURE_DIR}/services.txt"
ros2 run nova_xtainer_control_bringup xtrainer_full_grasp_smoke.py \
  --session-name "${SESSION}" \
  --object-name xtrainer_grasp_block \
  >"${CAPTURE_DIR}/grasp_smoke.log" 2>&1
ros2 topic echo /joint_states --once >"${CAPTURE_DIR}/joint_states_after.txt"

echo "${CAPTURE_DIR}"
