# X-Trainer Sim-to-Real 交接仓库

这个仓库是从原始工作目录里整理出来的干净版本，主要给后续负责虚拟仿真和 sim-to-real 的同学继续开发。

原始项目里有很多调研、论文、历史日志、数据集和个人配置，这些都没有放进来。这里保留的是能复现模型、跑通仿真数据链路、继续开发零售场景任务所需要的核心内容。

## 仓库里有什么

```text
isaac_data_gen/
  Isaac Sim + Isaac Lab + LeIsaac 数据生成链路
  包含 HDF5 采集、LeRobot 转换、质量检查、随机化配置和采集脚本

ros2_xtrainer_model/
  ROS2 Humble 工作区
  包含 X-Trainer 完整视觉模型、可控模型、RViz/Gazebo 启动和 14 维控制工具

docs/
  仓库内容说明、外部依赖说明、后续开发路线

scripts/
  仓库级准备、检查、初始化和推送脚本
```

## 没有放什么

下面这些内容故意不放进 Git：

- 调研文档、论文、PDF、网页快照
- 历史日志、截图、视频
- 已生成的 HDF5 / LeRobot 数据集
- Isaac Lab 源码副本
- 官方 X-Trainer-LeIsaac 上游副本
- conda 环境、ROS2 build/install/log 输出
- 个人 agent 记忆和本机配置

大文件和官方上游仓库后续用脚本恢复，这样 GitHub 仓库会比较轻，后面改 bug 也容易同步。

## 当前主线

后续开发建议按这个链路走：

```text
官方 X-Trainer-LeIsaac 资产
  -> Isaac Sim / Isaac Lab / LeIsaac
  -> PickCube 基线复现
  -> 零售 PickSnack / PlaceBasket 任务
  -> HDF5 原始数据
  -> LeRobot 数据集
  -> pi0.5 / VLA 训练数据增强
  -> 真机成功率评测
```

`ros2_xtrainer_model/` 主要是模型和控制语义参考。真正做高保真接触、随机化、批量数据生成时，优先在 `isaac_data_gen/` 里开发。

## 第一次拿到仓库后怎么做

先检查源码树：

```bash
cd <repo>
bash scripts/verify_source_tree.sh
```

再拉取官方上游和 PickCube 资产：

```bash
cd <repo>
bash scripts/prepare_external_assets.sh
```

如果要在本机配置 Isaac 环境：

```bash
cd <repo>
bash scripts/setup_isaac_env.sh
```

这个命令需要 NVIDIA GPU、conda、网络和 NVIDIA Omniverse EULA 授权。已有 `xtrainer_VLA` 环境时默认不会删除；只有显式设置 `RESET_XTRAINER_ENV=1` 才会重建。

## 常用入口

仿真数据生成：

```bash
cd isaac_data_gen
bash scripts/collect_episode.sh
```

导出已有 HDF5：

```bash
cd isaac_data_gen
python3 scripts/export_episode.py
```

ROS2 可控模型：

```bash
cd ros2_xtrainer_model/nova_vr_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
ros2 launch nova_xtainer_control_bringup xtrainer_full_mock_control.launch.py
```

更详细的说明看：

- [isaac_data_gen/README.md](isaac_data_gen/README.md)
- [ros2_xtrainer_model/README.md](ros2_xtrainer_model/README.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)
- [docs/REPOSITORY_CONTENTS.md](docs/REPOSITORY_CONTENTS.md)

## 推送到 GitHub

如果这是本地整理目录，准备推到一个新的空 GitHub 仓库，执行：

```bash
cd <repo>
REMOTE_URL=git@github.com:<user>/<repo>.git bash scripts/init_and_push_template.sh
```

HTTPS 也可以：

```bash
cd <repo>
REMOTE_URL=https://github.com/<user>/<repo>.git bash scripts/init_and_push_template.sh
```

脚本只会在当前交接目录里初始化 Git，不会处理原始大项目的 Git 历史。

## 协作规则

- 源码、配置、轻量模型、文档可以进 Git。
- 生成数据、日志、视频、外部仓库、conda 环境不要进 Git。
- 如果某个大资产确实必须使用，优先写下载脚本或说明来源，不要直接塞进仓库。
- 新增任务时，先保证能生成 HDF5、导出 MP4、通过质量检查，再考虑扩大随机化和批量生成。
