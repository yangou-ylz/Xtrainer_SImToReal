# 开发路线

## 目标

构建 X-Trainer 双臂机器人在零售抓取场景下的仿真数据生成链路。

核心目标：

- 在 Isaac/LeIsaac 中复现 X-Trainer 双臂任务。
- 生成可训练、可回放、可检查的数据。
- 将仿真数据转换为 LeRobot 格式。
- 为 VLA / pi0.5 训练提供 sim-to-real 数据增强。
- 用真机评测验证仿真数据是否提升泛化能力。

## 阶段 1：复现 PickCube 基线

先跑通官方 PickCube 任务。

验收输出：

- HDF5 episode。
- 三视角 `multiview.mp4`。
- 轨迹导出文件。
- 数据质量报告。
- LeRobot 转换结果。

推荐命令：

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys25_multiview_demo.sh session_multiview
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys30_record_hdf5_smoke.sh session_hdf5
bash scripts/phys40_convert_hdf5_to_lerobot.sh session_lerobot
```

## 阶段 2：建立零售物体任务

将 PickCube 扩展为零售抓取任务。

建议任务：

- `PickSnackBox`：抓取盒装零食并放入目标区域。
- `PickBottle`：抓取瓶装或罐装商品。
- `PickSnackBag`：抓取简化袋装零食。
- `PlaceBasket`：将商品放入篮子或收纳框。

初始版本优先使用刚体近似，不直接做软体包装。

## 阶段 3：加入随机化

随机化按顺序逐步加入：

1. 物体位置和朝向。
2. 目标容器位置。
3. 干扰物数量和位置。
4. 光照、曝光和背景贴图。
5. 物体质量、摩擦、夹爪驱动参数。

每新增一种随机化，都需要保留：

- 配置文件。
- 运行日志。
- 视频预览。
- 质量报告。

## 阶段 4：对齐真实数据

使用真实机器人采集数据校准仿真分布。

需要重点对齐：

- 相机视角。
- 桌面高度。
- 物体尺寸。
- workspace 边界。
- 夹爪开合范围。
- 初始机械臂姿态。
- 任务语言。

仿真场景不需要追求所有细节完全一致，优先保证视觉分布、动作空间和任务成功条件一致。

## 阶段 5：数据混合训练

推荐做三组训练对比：

- 真实数据训练。
- 真实数据 + 仿真数据混合训练。
- 仿真数据预训练 + 真实数据微调。

评测场景：

- 同物体新位置。
- 新物体同布局。
- 多物体杂乱布局。
- 语言指定目标物体。
- 遮挡或干扰物场景。

评测指标：

- 抓取成功率。
- 放置成功率。
- 抓错物体比例。
- 碰撞次数。
- 平均完成时间。

## 阶段 6：双臂协作任务

单臂零售抓取稳定后，再加入双臂协作。

推荐任务：

- 一只手稳定篮子，另一只手放入商品。
- 一只手拨开遮挡，另一只手抓取目标。
- 一只手固定容器，另一只手执行放置。
- 一只手调整商品姿态，另一只手抓取。

## 开发原则

- 先跑通最小闭环，再扩大任务复杂度。
- 每次只改一个主要变量。
- 所有 episode 都要能导出视频。
- 所有数据都要经过质量检查。
- 动作下标统一走 `action_mapping.py`。
- Gazebo Classic 只用于 ROS2 模型和控制验证，不作为高保真接触物理结论。
