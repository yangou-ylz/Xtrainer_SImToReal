# Development Roadmap

## Goal

Build a useful simulation data factory for X-Trainer dual-arm retail manipulation.

The purpose is not to prove that simulation is perfectly realistic. The purpose is to generate controlled scene variation, failure coverage, and evaluation data that improves real-robot VLA behavior.

## Current Baseline

The handoff package already contains:

- X-Trainer model assets and ROS2 controllable reference model
- Isaac/LeIsaac PickCube baseline scripts
- three-camera RGB recording
- HDF5 dataset recording
- LeRobot conversion
- action mapping between 14-DoF project commands and 16-DoF LeIsaac actions
- endpoint keyboard collection
- dataset quality checks

## Recommended Next Steps

### Stage 1: Stabilize PickCube

Reproduce the included PickCube workflow on the target machine.

Required outputs:

- one HDF5 episode
- one multiview MP4
- one quality report
- one LeRobot conversion

### Stage 2: Build PickSnack

Replace the cube with retail-like objects:

- snack box
- bottle or can
- bag-like simplified package
- basket or plate target

Start with rigid approximations. Do not begin with deformable packaging.

### Stage 3: Add Controlled Randomization

Add variation in this order:

1. object position and yaw
2. distractor objects
3. camera exposure and lighting
4. background/table texture
5. object mass and friction

Every randomization profile must have a quality gate.

### Stage 4: Align With Real Data

Use a small set of successful real-robot snack-grasp episodes to align:

- camera viewpoints
- workspace bounds
- object scale
- gripper open/close range
- initial arm poses
- task language

### Stage 5: Train and Compare

Run three data-mixing experiments:

- real only
- real + simulation
- simulation pretrain + real fine-tune

Evaluate on real hidden trials:

- same snack, new pose
- new snack, same layout
- cluttered retail layout
- language-targeted object selection

### Stage 6: Dual-Arm Retail Tasks

Add dual-arm value only when single-arm PickSnack is stable.

Good dual-arm tasks:

- one arm stabilizes a basket while the other places an object
- one arm clears an occluder while the other grasps the target
- one arm holds a bag or container while the other inserts an item

## Research Focus

A concise research question:

> How can a small amount of real X-Trainer retail manipulation data be combined with high-fidelity Isaac/LeIsaac simulation data to improve VLA generalization to new snacks, layouts, and occlusions?

Keep all progress measurable through real-robot success rate, not only simulator success.
