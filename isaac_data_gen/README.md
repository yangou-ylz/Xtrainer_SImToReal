# Isaac Data Generation

This directory contains the Isaac Sim / Isaac Lab / LeIsaac data-generation workflow for X-Trainer.

## Scope

Use this project for:

- X-Trainer PickCube baseline simulation
- retail object task development
- HDF5 recording
- LeRobot conversion
- camera/image validation
- action mapping validation
- sim-to-real randomization experiments

Do not use this directory for ROS2 teleoperation development. ROS2 model reference files are under `../ros2_xtrainer_model/`.

## Environment

Expected baseline:

```text
OS: Ubuntu 22.04
GPU: NVIDIA RTX GPU
Python: conda env xtrainer_VLA, Python 3.11
Isaac Sim: 5.1.0.0
Isaac Lab: v2.3.0
LeIsaac: 0.2.0 from official X-Trainer upstream
```

Set up from the repository root:

```bash
bash scripts/prepare_external_assets.sh
bash scripts/setup_isaac_env.sh
```

The setup writes external repositories and downloaded assets under:

```text
isaac_data_gen/external/
```

This directory is ignored by Git.

## Common Commands

Run a source-tree check:

```bash
cd isaac_data_gen
bash scripts/phys60_action_mapping_tests.sh session_action_mapping
```

Verify LeIsaac registry after setup:

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys22_verify_leisaac_registry.sh session_registry
```

Run a no-camera PickCube smoke test:

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys23_no_camera_smoke.sh session_no_camera
```

Run a three-view demo:

```bash
cd isaac_data_gen
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys25_multiview_demo.sh session_multiview
```

Collect one endpoint-control episode:

```bash
cd isaac_data_gen
bash scripts/collect_episode.sh
```

Export the latest HDF5:

```bash
cd isaac_data_gen
python3 scripts/export_episode.py
```

## Data Contract

The stable action bridge is:

```text
XTrainerCommand14
  -> LeIsaac 16-DoF follower action
  -> HDF5 actions/state
  -> LeRobot dataset
```

See:

- [docs/action_mapping.md](docs/action_mapping.md)
- [docs/data_schema.md](docs/data_schema.md)

Do not hand-write action indices in new scripts. Use `src/phys_data_gen/action_mapping.py`.

## Development Rules

- Keep official upstream code under `external/x-trainer` unchanged when possible.
- Put project code in `src/phys_data_gen`.
- Put runnable entrypoints in `scripts`.
- Put task and dataset parameters in `configs`.
- Every generated dataset should have a quality report.
- Do not commit `external/`, `logs/`, HDF5 files, MP4 files, or LeRobot generated outputs.
