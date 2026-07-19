# X-Trainer Sim-to-Real

X-Trainer 双臂机器人仿真、数据采集和 sim-to-real 开发项目。

项目包含两部分：

```text
isaac_data_gen/
  Isaac Sim + Isaac Lab + LeIsaac 数据生成链路
  用于高保真接触仿真、HDF5 采集、LeRobot 转换、质量检查和随机化增强

ros2_xtrainer_model/
  ROS2 Humble 模型工作区
  用于 X-Trainer 模型显示、可控模型验证、RViz/Gazebo 启动和 14 维动作接口检查
```

## 总体链路

```text
X-Trainer-LeIsaac 资产
  -> Isaac Sim / Isaac Lab / LeIsaac
  -> PickCube 基线任务
  -> 零售 PickSnack / PlaceBasket 任务
  -> HDF5 原始数据
  -> LeRobot 数据集
  -> VLA / pi0.5 训练数据增强
  -> 真机评测
```

`isaac_data_gen/` 是后续高保真仿真和数据生成主线。  
`ros2_xtrainer_model/` 是 ROS2 侧模型和动作语义参考。

## 目录结构

```text
.
├── isaac_data_gen/
│   ├── configs/              # 环境、数据集、随机化配置
│   ├── docs/                 # 动作映射和数据格式
│   ├── scripts/              # 安装、验证、采集、导出、质量检查入口
│   ├── src/phys_data_gen/    # 可复用 Python 工具
│   └── tests/                # 单元测试
├── ros2_xtrainer_model/
│   └── nova_vr_ws/src/       # ROS2 模型包
├── docs/                     # 项目说明和开发路线
└── scripts/                  # 仓库级工具脚本
```

## 快速开始

检查项目结构：

```bash
cd <repo>
bash scripts/verify_source_tree.sh
```

准备 X-Trainer-LeIsaac 上游和 PickCube 资产：

```bash
cd <repo>
bash scripts/prepare_external_assets.sh
```

配置 Isaac 环境：

```bash
cd <repo>
bash scripts/setup_isaac_env.sh
```

环境要求：

- Ubuntu 22.04
- NVIDIA RTX GPU
- conda
- Isaac Sim `5.1.0.0`
- Isaac Lab `v2.3.0`
- LeIsaac `0.2.0`

已有 `xtrainer_VLA` conda 环境时，脚本默认复用该环境。需要完整重建时再执行：

```bash
RESET_XTRAINER_ENV=1 bash scripts/setup_isaac_env.sh
```

## Isaac 数据生成

动作映射测试：

```bash
cd isaac_data_gen
PYTHONPATH=src pytest -q tests/test_action_mapping.py
```

LeIsaac 注册验证：

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys22_verify_leisaac_registry.sh session_registry
```

PickCube 无相机 smoke test：

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys23_no_camera_smoke.sh session_no_camera
```

三视角 demo：

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys25_multiview_demo.sh session_multiview
```

采集一条 episode：

```bash
cd isaac_data_gen
bash scripts/collect_episode.sh
```

导出最新 HDF5：

```bash
cd isaac_data_gen
python3 scripts/export_episode.py
```

## ROS2 模型

构建 ROS2 工作区：

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

查看静态视觉模型：

```bash
ros2 launch nova_xtainer_bringup xtainer_rviz.launch.py
```

运行可控模型：

```bash
ros2 launch nova_xtainer_control_bringup xtrainer_full_mock_control.launch.py
```

另开终端运行 14 维控制滑块：

```bash
cd ros2_xtrainer_model/nova_vr_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run nova_xtainer_control_bringup xtrainer_full_action_slider.py
```

## 文档

- [isaac_data_gen/README.md](isaac_data_gen/README.md)
- [ros2_xtrainer_model/README.md](ros2_xtrainer_model/README.md)
- [docs/REPOSITORY_CONTENTS.md](docs/REPOSITORY_CONTENTS.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)

## 版本管理

建议提交源码、配置、轻量模型和文档。

不要提交运行生成文件：

- `isaac_data_gen/external/`
- `isaac_data_gen/logs/`
- `isaac_data_gen/datasets/`
- `ros2_xtrainer_model/nova_vr_ws/build/`
- `ros2_xtrainer_model/nova_vr_ws/install/`
- `ros2_xtrainer_model/nova_vr_ws/logs/`
- conda 环境、缓存文件、视频文件
