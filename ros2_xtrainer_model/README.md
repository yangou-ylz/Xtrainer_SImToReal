# ROS2 X-Trainer 模型

这个目录是 ROS2 Humble 工作区，主要用于查看和验证 X-Trainer 模型。

它不是高保真接触物理主线。真正做 Isaac/LeIsaac 数据生成时，优先看 `../isaac_data_gen/`。这里更多是模型参考、动作语义参考和控制链路参考。

## 包含哪些 ROS2 包

```text
nova_xtainer_description
  完整 X-Trainer 静态视觉参考模型

nova_xtainer_control_description
  可控 X-Trainer URDF 和本地 STL mesh

nova_xtainer_control_bringup
  RViz/Gazebo 启动、mock controller、14 维命令工具

nova_xtainer_bringup
  静态参考模型启动

nova_vr_common
  最小日志工具
```

## 依赖

需要：

- Ubuntu 22.04
- ROS2 Humble
- `xacro`
- `rviz2`
- `ros2_control`
- `ros2_controllers`
- `gazebo_ros`
- `gazebo_ros2_control`

ROS2 不要放在 conda 里跑。使用系统 ROS2/overlay 环境。

## 构建

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

## 查看完整静态视觉模型

RViz：

```bash
ros2 launch nova_xtainer_bringup xtainer_rviz.launch.py
```

Gazebo：

```bash
ros2 launch nova_xtainer_bringup xtainer_gazebo.launch.py gui:=true
```

静态视觉模型只用来看完整 X-Trainer 外观，不用于关节控制。

## 运行可控模型

启动可控模型和 mock controller：

```bash
ros2 launch nova_xtainer_control_bringup xtrainer_full_mock_control.launch.py
```

另开一个终端运行滑块控制：

```bash
cd ros2_xtrainer_model/nova_vr_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run nova_xtainer_control_bringup xtrainer_full_action_slider.py
```

Gazebo position-control：

```bash
ros2 launch nova_xtainer_control_bringup xtrainer_full_control_gazebo.launch.py gui:=true rviz:=false
```

## 14 维动作语义

项目内部动作顺序固定为：

```text
[left_joint1..6, left_gripper, right_joint1..6, right_gripper]
```

说明：

- 机械臂关节单位是 rad。
- 夹爪是归一化值。
- `0.0 = open`。
- `1.0 = closed`。

Isaac/LeIsaac 侧的 16 维映射见：

```text
../isaac_data_gen/docs/action_mapping.md
```

## 注意事项

- 这里包含的 STL mesh 是 ROS2 参考模型运行必需的轻量资产，可以进 Git。
- `build/`、`install/`、`log/`、`logs/` 不进 Git。
- Gazebo Classic 只用于模型显示、controller smoke test 和有限控制验证，不作为真实抓取接触物理结论。
- 如果后续修改动作语义，必须同步更新 Isaac 侧 `action_mapping.md` 和测试。
