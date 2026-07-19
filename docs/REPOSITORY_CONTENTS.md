# 项目内容

## `isaac_data_gen/`

Isaac/LeIsaac 数据生成主目录。

```text
configs/
  环境、数据集和随机化配置

docs/
  动作映射和数据格式说明

scripts/
  安装、验证、采集、导出、质量检查脚本

src/phys_data_gen/
  可复用 Python 工具

tests/
  单元测试

external/
  外部上游和下载资产，本地生成

datasets/
  HDF5 和 LeRobot 输出，本地生成

logs/
  运行日志、视频导出、质量报告，本地生成
```

核心文档：

- `docs/action_mapping.md`
- `docs/data_schema.md`

核心模块：

- `src/phys_data_gen/action_mapping.py`
- `src/phys_data_gen/dataset_validation.py`
- `src/phys_data_gen/image_validation.py`
- `src/phys_data_gen/logging_utils.py`

## `ros2_xtrainer_model/`

ROS2 Humble 模型工作区。

```text
nova_vr_ws/src/nova_xtainer_description/
  完整 X-Trainer 静态视觉模型

nova_vr_ws/src/nova_xtainer_control_description/
  可控 X-Trainer URDF 和 STL mesh

nova_vr_ws/src/nova_xtainer_control_bringup/
  RViz/Gazebo launch、mock controller、14 维命令工具

nova_vr_ws/src/nova_xtainer_bringup/
  静态模型 RViz/Gazebo launch

nova_vr_ws/src/nova_vr_common/
  ROS2 侧日志工具
```

## 外部依赖

外部依赖通过脚本准备：

```bash
bash scripts/prepare_external_assets.sh
```

包含：

- Isaac Lab `v2.3.0`
- `embodied-dobot/x-trainer` 固定版本
- X-Trainer 机器人 USD 资产
- PickCube 场景资产

Isaac 环境通过脚本安装和验证：

```bash
bash scripts/setup_isaac_env.sh
```

## 生成目录

下面这些目录用于本地运行输出，不建议纳入版本管理：

```text
isaac_data_gen/external/
isaac_data_gen/logs/
isaac_data_gen/datasets/
ros2_xtrainer_model/nova_vr_ws/build/
ros2_xtrainer_model/nova_vr_ws/install/
ros2_xtrainer_model/nova_vr_ws/logs/
```
