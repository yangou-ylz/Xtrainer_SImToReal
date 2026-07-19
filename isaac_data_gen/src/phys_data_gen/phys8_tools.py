"""Shared helpers for PHYS-8 interactive and grasp-precheck stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from phys_data_gen.action_mapping import command14_to_leisaac16
from phys_data_gen.image_validation import CAMERAS, extract_obs_image, image_stats, save_multiview_grid, to_numpy_image


def tensor_to_numpy(value):
    """Convert torch tensor or array-like value to numpy."""

    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def first_env_array(value):
    """Return the first env row for batched Isaac Lab observations."""

    array = tensor_to_numpy(value)
    if array.ndim >= 2 and array.shape[0] == 1:
        return array[0]
    return array


def policy_array(obs: dict[str, Any], key: str) -> np.ndarray:
    policy = obs.get("policy", {}) if isinstance(obs, dict) else {}
    if key not in policy:
        raise KeyError(f"missing policy observation key: {key}")
    return first_env_array(policy[key])


def bool_from_obs(obs: dict[str, Any], group_name: str, key: str) -> bool | None:
    group = obs.get(group_name, {}) if isinstance(obs, dict) else {}
    if key not in group:
        return None
    array = first_env_array(group[key])
    return bool(np.asarray(array).item())


def capture_multiview(env, obs: dict[str, Any], output_prefix: str, session) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Save and validate top/left/right camera images for one observation."""

    import imageio.v3 as iio

    images: dict[str, np.ndarray] = {}
    stats: dict[str, Any] = {}
    for camera_name in CAMERAS:
        obs_image = extract_obs_image(obs, camera_name)
        if obs_image is not None:
            image = to_numpy_image(obs_image)
            source = f"observation.policy.{camera_name}"
        else:
            sensor = env.scene.sensors[camera_name]
            image = to_numpy_image(sensor.data.output["rgb"])
            source = f"scene.sensors.{camera_name}.data.output.rgb"

        camera_stats = image_stats(image)
        camera_stats["source"] = source
        camera_stats["camera"] = camera_name
        validate_camera_stats(camera_name, camera_stats)
        images[camera_name] = image
        stats[camera_name] = camera_stats
        iio.imwrite(session.root / f"{output_prefix}_{camera_name}.png", image)
        session.data.info("capture=%s camera=%s stats=%s", output_prefix, camera_name, json.dumps(camera_stats, sort_keys=True))

    grid_path = session.root / f"{output_prefix}_grid.png"
    save_multiview_grid(images, grid_path, title=output_prefix)
    return images, stats


def validate_camera_stats(camera_name: str, stats: dict[str, Any]) -> None:
    if stats["shape"] != [480, 640, 3]:
        raise RuntimeError(f"{camera_name}: unexpected image shape: {stats['shape']}")
    if float(stats["std"]) < 2.0:
        raise RuntimeError(f"{camera_name}: image appears blank: std={stats['std']}")
    if int(stats["unique_sample_count"]) < 10:
        raise RuntimeError(f"{camera_name}: too few sampled colors: {stats['unique_sample_count']}")


def make_command14(stage_name: str) -> np.ndarray:
    """Deterministic PHYS-8 command sequence in project 14-D semantic format."""

    command = np.zeros((14,), dtype=np.float32)
    if stage_name == "home_open":
        command[6] = 0.0
        command[13] = 0.0
    elif stage_name == "move_ready":
        command[0] = 0.16
        command[1] = -0.12
        command[3] = 0.08
        command[5] = 0.08
        command[6] = 0.10
        command[7] = -0.16
        command[8] = -0.12
        command[10] = 0.08
        command[12] = -0.08
        command[13] = 0.10
    elif stage_name == "close_grippers":
        command = make_command14("move_ready")
        command[6] = 1.0
        command[13] = 1.0
    elif stage_name == "lift_after_close":
        command = make_command14("close_grippers")
        command[1] = -0.18
        command[8] = -0.18
        command[3] = 0.12
        command[10] = 0.12
    elif stage_name == "return_home_open":
        command = make_command14("home_open")
    else:
        raise ValueError(f"unknown command stage: {stage_name}")
    return command


def phys8_stage_sequence() -> list[tuple[str, int]]:
    return [
        ("home_open", 8),
        ("move_ready", 24),
        ("close_grippers", 18),
        ("lift_after_close", 12),
    ]


def phys8_record_sequence() -> list[tuple[str, int]]:
    return [
        ("home_open", 8),
        ("move_ready", 24),
        ("close_grippers", 18),
        ("lift_after_close", 12),
        ("return_home_open", 8),
    ]


def make_leisaac_action(stage_name: str, env, action_shape):
    """Create a torch action tensor for one PHYS-8 stage."""

    import torch

    action16 = command14_to_leisaac16(make_command14(stage_name))
    action = torch.as_tensor(action16, dtype=torch.float32, device=env.device).reshape(1, -1).repeat(action_shape[0], 1)
    return action, action16


def scene_metrics(env, obs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect official PickCube-related geometric and boolean diagnostics."""

    import torch
    from isaaclab.managers import SceneEntityCfg
    from isaaclab.utils.math import quat_apply
    from leisaac.tasks.pick_cube import mdp as pick_cube_mdp

    robot = env.scene["robot"]
    cube = env.scene["cube"]
    plate = env.scene["Plate"]
    right_ee_frame = env.scene["right_ee_frame"]

    object_pos = cube.data.root_pos_w
    plate_pos = plate.data.root_pos_w
    ee_pos_w = right_ee_frame.data.target_pos_w[:, 1, :]
    ee_quat_w = right_ee_frame.data.target_quat_w[:, 1, :]
    offset_local = torch.tensor([0.0, 0.0, 0.16], device=env.device).repeat(env.num_envs, 1)
    grasp_center_pos = ee_pos_w + quat_apply(ee_quat_w, offset_local)
    pos_diff = torch.linalg.vector_norm(object_pos - grasp_center_pos, dim=1)

    j2_8_ids, _ = robot.find_joints("J2_8")
    j2_7_ids, _ = robot.find_joints("J2_7")
    j2_8 = robot.data.joint_pos[:, j2_8_ids[0]]
    j2_7 = robot.data.joint_pos[:, j2_7_ids[0]]

    object_grasped = pick_cube_mdp.object_grasped(
        env,
        object_cfg=SceneEntityCfg("cube"),
        ee_frame_cfg=SceneEntityCfg("right_ee_frame"),
    )
    put_cube_to_plate = pick_cube_mdp.put_cube_to_plate(
        env,
        object_cfg=SceneEntityCfg("cube"),
        plate_cfg=SceneEntityCfg("Plate"),
        ee_frame_cfg=SceneEntityCfg("right_ee_frame"),
    )
    task_done = pick_cube_mdp.task_done(
        env,
        objects_cfg=[SceneEntityCfg("cube")],
        plate_cfg=SceneEntityCfg("Plate"),
    )

    result = {
        "cube_pos_w": tensor_to_numpy(object_pos[0]).astype(float).tolist(),
        "plate_pos_w": tensor_to_numpy(plate_pos[0]).astype(float).tolist(),
        "right_grasp_center_pos_w": tensor_to_numpy(grasp_center_pos[0]).astype(float).tolist(),
        "right_grasp_center_to_cube_m": float(pos_diff[0].detach().cpu().item()),
        "right_j2_8_m": float(j2_8[0].detach().cpu().item()),
        "right_j2_7_plus_j2_8_m": float((j2_7[0] + j2_8[0]).detach().cpu().item()),
        "object_grasped_official": bool(object_grasped[0].detach().cpu().item()),
        "put_cube_to_plate_official": bool(put_cube_to_plate[0].detach().cpu().item()),
        "task_done_official": bool(task_done[0].detach().cpu().item()),
    }
    if obs is not None:
        result["obs_pick_cube"] = bool_from_obs(obs, "subtask_terms", "pick_cube")
        result["obs_put_cube_to_plate"] = bool_from_obs(obs, "subtask_terms", "put_cube_to_plate")
    return result


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
