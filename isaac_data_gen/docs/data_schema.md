# X-Trainer 仿真数据 Schema

更新日期：2026-06-14

## 1. 原始 HDF5

X-Trainer-LeIsaac 转换脚本预期 HDF5 结构：

```text
data/
  demo_x/
    actions                         shape: [T, 16]
    obs/
      left_joint_pos_rel            shape: [T, 8]
      right_joint_pos_rel           shape: [T, 8]
      top                           shape: [T, 480, 640, 3]
      left_wrist                    shape: [T, 480, 640, 3]
      right_wrist                   shape: [T, 480, 640, 3]
    attrs:
      success                       bool, optional but recommended
```

来源：`scripts/convert/isaaclab2lerobot_xtrainer.py`。

## 2. LeRobot 输出

LeRobot features：

```text
action
  dtype: float32
  shape: (16,)
  names: J1_1.pos ... J1_8.pos, J2_1.pos ... J2_8.pos

observation.state
  dtype: float32
  shape: (16,)
  names: J1_1.pos ... J1_8.pos, J2_1.pos ... J2_8.pos

observation.images.top
  dtype: video
  shape: [480, 640, 3]
  fps: 30.0

observation.images.left_wrist
  dtype: video
  shape: [480, 640, 3]
  fps: 30.0

observation.images.right_wrist
  dtype: video
  shape: [480, 640, 3]
  fps: 30.0
```

默认 task language：

```text
Grab cube and place into plate
```

## 3. 数据质量校验

后续 `src/phys_data_gen/dataset_validation.py` 至少检查：

- 每个 demo 帧数 `T >= 10`。
- action/state/image 帧数一致。
- action/state 没有 NaN/Inf。
- gripper `J*_7 + J*_8` 绝对值在阈值内。
- 图像 shape 为 480x640x3，dtype 可被转换脚本处理。
- success attr 存在时只转换 success episode。
- 记录实际 FPS 或 step_hz，目标 30Hz。

