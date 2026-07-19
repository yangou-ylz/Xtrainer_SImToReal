# ROS2 X-Trainer Model

This directory contains a ROS2 Humble workspace with the current X-Trainer model reference.

## Scope

Use this workspace for:

- viewing the full X-Trainer visual reference in RViz
- running the controllable X-Trainer model with `ros2_control`
- testing the 14-action command interface
- comparing ROS2 model semantics with Isaac/LeIsaac actions

High-fidelity contact simulation and dataset generation should happen in `../isaac_data_gen/`.

## Packages

```text
nova_xtainer_description
  static full-visual X-Trainer reference model

nova_xtainer_control_description
  articulated controllable X-Trainer URDF and local STL meshes

nova_xtainer_control_bringup
  RViz/Gazebo launch files, mock controllers, command utilities

nova_xtainer_bringup
  static reference launch files

nova_vr_common
  minimal logging helper used by model validation tools
```

## Dependencies

Required:

- Ubuntu 22.04
- ROS2 Humble
- `xacro`
- `rviz2`
- `ros2_control`
- `ros2_controllers`
- `gazebo_ros`
- `gazebo_ros2_control`

Install the usual ROS2 dependencies on the target machine. Do not use a conda environment for ROS2.

## Build

```bash
cd ros2_xtrainer_model/nova_vr_ws
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1
export NOVA_VR_WS="$PWD"
export ROS_LOG_DIR="$PWD/logs/ros"
mkdir -p "$ROS_LOG_DIR"
colcon build --symlink-install
source install/setup.bash
```

## Run Static Visual Reference

```bash
ros2 launch nova_xtainer_bringup xtainer_rviz.launch.py
```

Gazebo static visual reference:

```bash
ros2 launch nova_xtainer_bringup xtainer_gazebo.launch.py gui:=true
```

## Run Controllable Model

```bash
ros2 launch nova_xtainer_control_bringup xtrainer_full_mock_control.launch.py
```

In another terminal:

```bash
cd ros2_xtrainer_model/nova_vr_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run nova_xtainer_control_bringup xtrainer_full_action_slider.py
```

## 14-Action Semantics

```text
[left_joint1..6, left_gripper, right_joint1..6, right_gripper]
```

- arm joints are in radians
- gripper value is normalized
- `0.0 = open`
- `1.0 = closed`

The Isaac/LeIsaac conversion is documented in `../isaac_data_gen/docs/action_mapping.md`.

## Notes

The STL meshes in this workspace are included because they are the already-generated model assets required by the ROS2 reference model. ROS2 build outputs and logs are intentionally ignored by Git.
