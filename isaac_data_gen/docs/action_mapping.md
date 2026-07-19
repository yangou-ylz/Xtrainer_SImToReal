# X-Trainer Action Mapping

更新日期：2026-06-14

实现状态：PHYS-6 已完成。实现位于 `src/phys_data_gen/action_mapping.py`，测试位于 `tests/test_action_mapping.py`，回归证据为 `logs/session_phys60_action_mapping_tests_v1/`。

本文件固定 VR/ROS2/真实 SDK/Isaac 之间的动作语义，避免后续按数组下标临时解释。

## 1. 项目内部 14 维语义

`XTrainerCommand14` 顺序：

```text
0  left_joint1       rad
1  left_joint2       rad
2  left_joint3       rad
3  left_joint4       rad
4  left_joint5       rad
5  left_joint6       rad
6  left_gripper      scalar, 0=open, 1=closed
7  right_joint1      rad
8  right_joint2      rad
9  right_joint3      rad
10 right_joint4      rad
11 right_joint5      rad
12 right_joint6      rad
13 right_gripper     scalar, 0=open, 1=closed
```

该语义已经被 ROS2 X-Trainer model、Quest adapter 原型和 SDK dry-run 原型使用。

## 2. LeIsaac / X-Trainer 16 维语义

LeIsaac follower action/state 顺序：

```text
0  J1_1.pos
1  J1_2.pos
2  J1_3.pos
3  J1_4.pos
4  J1_5.pos
5  J1_6.pos
6  J1_7.pos
7  J1_8.pos
8  J2_1.pos
9  J2_2.pos
10 J2_3.pos
11 J2_4.pos
12 J2_5.pos
13 J2_6.pos
14 J2_7.pos
15 J2_8.pos
```

来源：

- `source/leisaac/leisaac/devices/action_process.py`
- `scripts/convert/isaaclab2lerobot_xtrainer.py`
- `source/leisaac/leisaac/assets/robots/xtrainer.py`

## 3. 14 -> 16 映射

```text
J1_1 = left_joint1
J1_2 = left_joint2
J1_3 = left_joint3
J1_4 = left_joint4
J1_5 = left_joint5
J1_6 = left_joint6

left_u = clamp(left_gripper, 0, 1)
J1_8 = left_u * 0.04
J1_7 = -J1_8

J2_1 = right_joint1
J2_2 = right_joint2
J2_3 = right_joint3
J2_4 = right_joint4
J2_5 = right_joint5
J2_6 = right_joint6

right_u = clamp(right_gripper, 0, 1)
J2_8 = right_u * 0.04
J2_7 = -J2_8
```

## 4. 16 -> 14 映射

用于把 LeIsaac action/state 转回项目内部语义：

```text
left_joint1..6 = J1_1..J1_6
left_gripper = clamp(J1_8 / 0.04, 0, 1)

right_joint1..6 = J2_1..J2_6
right_gripper = clamp(J2_8 / 0.04, 0, 1)
```

`J*_7` 应与 `-J*_8` 基本一致；若差异超阈值，validator 应报警。

## 5. 实现要求

- 实现位置：`src/phys_data_gen/action_mapping.py`。
- 单元测试覆盖 open/closed、中间值、越界 clamp、左右臂顺序。
- 所有采集和转换脚本必须调用该模块，不允许散落手写下标。
