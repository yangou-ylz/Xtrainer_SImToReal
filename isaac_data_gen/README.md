# Isaac 数据生成

这个目录是 X-Trainer 虚拟仿真和数据生成的主工作区。

它的目标不是单纯“跑一个仿真”，而是把仿真变成一个能持续产出训练数据、评测数据和 sim-to-real 对照实验的数据工厂。

## 这个目录负责什么

适合在这里做：

- X-Trainer PickCube 基线复现。
- 零售物体任务开发，例如 PickSnack、PlaceBasket。
- Isaac/LeIsaac 三视角 RGB 数据采集。
- HDF5 原始数据记录。
- LeRobot 数据集转换。
- 图像、轨迹和 episode 质量检查。
- 场景随机化和 sim-to-real 数据增强。

不建议在这里做 ROS2/Quest 遥操作开发。ROS2 模型参考在 `../ros2_xtrainer_model/`。

## 环境要求

推荐基线：

```text
系统：Ubuntu 22.04
GPU：NVIDIA RTX 系列
Python：conda 环境 xtrainer_VLA，Python 3.11
Isaac Sim：5.1.0.0
Isaac Lab：v2.3.0
LeIsaac：0.2.0，来自官方 X-Trainer 上游
```

从仓库根目录执行：

```bash
bash scripts/prepare_external_assets.sh
bash scripts/setup_isaac_env.sh
```

外部上游和下载资产会放到：

```text
isaac_data_gen/external/
```

这个目录不会进 Git。

## 常用命令

动作映射单元测试：

```bash
cd isaac_data_gen
PYTHONPATH=src pytest -q tests/test_action_mapping.py
```

LeIsaac registry 验证：

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys22_verify_leisaac_registry.sh session_registry
```

无相机 PickCube smoke test：

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys23_no_camera_smoke.sh session_no_camera
```

三视角 demo：

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys25_multiview_demo.sh session_multiview
```

采集一条末端控制 episode：

```bash
cd isaac_data_gen
bash scripts/collect_episode.sh
```

导出最新 HDF5：

```bash
cd isaac_data_gen
python3 scripts/export_episode.py
```

## 数据格式

当前稳定的数据链路是：

```text
XTrainerCommand14
  -> LeIsaac 16 维 follower action
  -> HDF5 actions / observations
  -> LeRobot dataset
```

动作语义和数据格式看：

- [docs/action_mapping.md](docs/action_mapping.md)
- [docs/data_schema.md](docs/data_schema.md)

新脚本不要手写动作下标，统一调用：

```text
src/phys_data_gen/action_mapping.py
```

## 目录结构

```text
configs/
  环境、数据集、随机化配置

docs/
  动作映射和数据格式说明

scripts/
  安装、验证、采集、导出、质量检查脚本

src/phys_data_gen/
  可复用 Python 工具

tests/
  单元测试

external/
  官方上游和下载资产，本地生成，不进 Git

datasets/
  HDF5 和 LeRobot 输出，本地生成，不进 Git

logs/
  每次运行的日志和报告，本地生成，不进 Git
```

## 开发建议

- 官方上游代码尽量保持干净，不要直接在 `external/x-trainer` 里堆业务修改。
- 自己写的通用逻辑放 `src/phys_data_gen/`。
- 可执行入口放 `scripts/`。
- 参数放 `configs/`，不要散落硬编码。
- 每次生成数据都要保存配置、日志、视频和质量报告。
- 新随机化必须能通过质量门，否则不要扩大批量生成。
