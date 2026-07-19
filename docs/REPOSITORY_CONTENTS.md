# Repository Contents

## Included

### `isaac_data_gen/`

Self-contained project code for X-Trainer simulation data generation:

- `scripts/`: installation, verification, recording, export, and quality-gate entrypoints
- `src/phys_data_gen/`: reusable Python utilities for action mapping, image checks, logging, and dataset validation
- `configs/`: environment, dataset, and randomization profiles
- `docs/action_mapping.md`: fixed action semantics between project 14-DoF commands and LeIsaac 16-DoF actions
- `docs/data_schema.md`: HDF5 and LeRobot schema
- `tests/`: unit tests for the action mapping contract

### `ros2_xtrainer_model/`

ROS2 Humble workspace with the current X-Trainer model packages:

- `nova_xtainer_description`: static full-visual X-Trainer reference model
- `nova_xtainer_control_description`: controllable X-Trainer URDF and local STL meshes
- `nova_xtainer_control_bringup`: RViz/Gazebo launch files, mock controllers, command utilities, validation scripts
- `nova_xtainer_bringup`: static model RViz/Gazebo launch files
- `nova_vr_common`: minimal shared logging helper used by the ROS2 model tools

## Excluded

The original project contained many files that are not needed for this handoff:

- research paper folders
- technical investigation notes
- personal agent memory
- old logs and screenshots
- generated datasets
- third-party repositories that can be downloaded again
- conda environments
- ROS2 build/install/log folders

## External Dependencies

The following dependencies are restored on demand:

- Isaac Sim `5.1.0.0` from NVIDIA pip packages
- Isaac Lab `v2.3.0`
- official `embodied-dobot/x-trainer` commit `5862c3ba4997ae0d4c41f69c73981353af3a8346`
- PickCube assets from `dstx123/xtrainer-leisaac` through the configured Hugging Face mirror

Run:

```bash
bash scripts/prepare_external_assets.sh
```
