# 仓库内容说明

这份文档说明当前交接仓库里放了什么、没放什么，以及外部依赖应该怎么恢复。

## 已包含内容

### `isaac_data_gen/`

这是后续仿真数据生成的主目录，包含：

- `scripts/`：安装、验证、采集、导出和质量检查入口。
- `src/phys_data_gen/`：可复用 Python 工具，包括动作映射、图像检查、日志和数据集校验。
- `configs/`：环境、数据集和随机化配置。
- `docs/action_mapping.md`：固定 14 维项目动作和 LeIsaac 16 维动作之间的映射。
- `docs/data_schema.md`：HDF5 和 LeRobot 数据格式。
- `tests/`：动作映射单元测试。

这个目录的定位是：继续做 Isaac/LeIsaac 高保真仿真、虚拟数据采集和 sim-to-real 数据增强。

### `ros2_xtrainer_model/`

这是 ROS2 Humble 模型参考工作区，包含：

- `nova_xtainer_description`：完整 X-Trainer 静态视觉参考模型。
- `nova_xtainer_control_description`：可控 X-Trainer URDF 和本地 STL mesh。
- `nova_xtainer_control_bringup`：RViz/Gazebo 启动、mock controller、14 维命令工具和验证脚本。
- `nova_xtainer_bringup`：静态模型 RViz/Gazebo 启动。
- `nova_vr_common`：ROS2 侧最小日志工具。

这个目录主要用于看模型、验证控制语义、对齐 ROS2 和 Isaac 两边的动作定义。它不是最终高保真接触物理主线。

### `docs/`

仓库级文档：

- `REPOSITORY_CONTENTS.md`：当前文件，说明仓库内容和排除项。
- `ROADMAP.md`：后续从 PickCube 到零售 PickSnack、sim-to-real 和 VLA 训练的路线。

### `scripts/`

仓库级工具：

- `verify_source_tree.sh`：检查交接仓库是否缺关键文件、是否混入不该放的资料。
- `prepare_external_assets.sh`：恢复官方 X-Trainer-LeIsaac 上游和 PickCube 资产。
- `setup_isaac_env.sh`：创建并验证 Isaac/LeIsaac 环境。
- `init_and_push_template.sh`：把当前交接目录初始化为新 Git 仓库并推到 GitHub。

## 故意排除的内容

原始项目里有很多不适合交给仿真开发仓库的内容，已经排除：

- 调研、论文、PDF、网页快照。
- 历史日志、截图、视频。
- 生成过的 HDF5 和 LeRobot 数据集。
- Isaac Lab 源码副本。
- 官方 X-Trainer-LeIsaac 源码副本。
- conda 环境。
- ROS2 build/install/log 输出。
- 个人 agent 记忆、本机配置和无关实验。

这样做的原因很简单：这些东西要么太大，要么跟交付目标无关，要么包含个人研究过程，不适合放到共享仓库。

## 外部依赖

下面这些依赖不进 Git，用脚本恢复：

- Isaac Sim `5.1.0.0`
- Isaac Lab `v2.3.0`
- 官方 `embodied-dobot/x-trainer`，固定 commit：`5862c3ba4997ae0d4c41f69c73981353af3a8346`
- PickCube 资产，来自 `dstx123/xtrainer-leisaac`，默认走 Hugging Face 镜像

恢复命令：

```bash
cd <repo>
bash scripts/prepare_external_assets.sh
```

安装 Isaac 环境：

```bash
cd <repo>
bash scripts/setup_isaac_env.sh
```

## Git 使用建议

建议提交：

- 源码
- 配置
- 小型 mesh
- README 和开发文档
- 测试脚本

不要提交：

- `isaac_data_gen/external/`
- `isaac_data_gen/logs/`
- `isaac_data_gen/datasets/`
- `ros2_xtrainer_model/nova_vr_ws/build/`
- `ros2_xtrainer_model/nova_vr_ws/install/`
- `ros2_xtrainer_model/nova_vr_ws/logs/`
- `.venv/`、conda 环境、缓存文件
