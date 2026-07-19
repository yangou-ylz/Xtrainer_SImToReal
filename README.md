# X-Trainer Simulation Handoff

This repository contains the cleaned handoff package for X-Trainer dual-arm simulation and sim-to-real data generation.

It is intentionally smaller than the original working directory. Research notes, papers, historical logs, generated datasets, agent memory, local Git history, and unrelated experiments are not included.

## What Is Included

```text
isaac_data_gen/
  Isaac Sim + Isaac Lab + LeIsaac data-generation workflow
  HDF5 recording, LeRobot conversion, quality gates, randomization profiles

ros2_xtrainer_model/
  ROS2 Humble workspace with the X-Trainer visual and controllable model packages
  RViz/Gazebo launch files, ros2_control mock control, 14-action control utilities

docs/
  Repository inventory, external dependency policy, and development roadmap

scripts/
  Repository-level setup and verification helpers
```

## What Is Not Included

The following content is intentionally excluded:

- research notes, papers, PDFs, and web snapshots
- generated logs and screenshots
- generated HDF5 / LeRobot datasets
- Isaac Lab source checkout
- official X-Trainer-LeIsaac upstream checkout
- local conda environments and ROS2 build/install outputs

Large or official dependencies are restored by scripts. This keeps Git history small and makes later bug fixes easy to synchronize through GitHub.

## Main Workflow

The high-level workflow is:

```text
official X-Trainer-LeIsaac assets
  -> Isaac Sim / Isaac Lab / LeIsaac
  -> PickCube baseline
  -> retail PickSnack task extension
  -> HDF5 recording
  -> LeRobot conversion
  -> VLA / pi0.5 data mixing and real-robot evaluation
```

The ROS2 model is provided as a model and control reference. The primary high-fidelity contact simulation and data-generation path is `isaac_data_gen/`.

## Quick Start

Clone the repository, then prepare external sources and assets:

```bash
cd <repo>
bash scripts/prepare_external_assets.sh
```

Set up the Isaac environment only on a machine with NVIDIA GPU support:

```bash
cd <repo>
bash scripts/setup_isaac_env.sh
```

Verify the source tree:

```bash
cd <repo>
bash scripts/verify_source_tree.sh
```

Initialize and push to a new GitHub repository:

```bash
cd <repo>
REMOTE_URL=git@github.com:<user>/<repo>.git bash scripts/init_and_push_template.sh
```

Then follow:

- [isaac_data_gen/README.md](isaac_data_gen/README.md) for Isaac/LeIsaac data generation
- [ros2_xtrainer_model/README.md](ros2_xtrainer_model/README.md) for ROS2 model visualization and mock control
- [docs/ROADMAP.md](docs/ROADMAP.md) for the next research and engineering direction

## Repository Policy

Use Git for source code, configuration, lightweight model meshes, and documentation.

Do not commit generated datasets, logs, videos, conda environments, Isaac Lab source, or official upstream repositories. If a large asset is required, document how to download it or add it to an external artifact store.
