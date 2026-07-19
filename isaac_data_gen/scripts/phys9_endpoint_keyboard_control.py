#!/usr/bin/env python3
"""Endpoint keyboard control and recording for X-Trainer LeIsaac."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import time
import traceback
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from phys_data_gen.dataset_validation import render_markdown_report, validate_hdf5_dataset
from phys_data_gen.image_validation import CAMERAS, mean_abs_diff
from phys_data_gen.logging_utils import log_environment, mark_fail, mark_pass, setup_logging
from phys_data_gen.phys8_tools import capture_multiview, policy_array, save_json, tensor_to_numpy


CONTROL_KEYS = set("wsadequoikjlgr")


def quat_wxyz_from_euler_xyz_deg(roll: float, pitch: float, yaw: float) -> np.ndarray:
    from scipy.spatial.transform import Rotation as R

    xyzw = R.from_euler("XYZ", [roll, pitch, yaw], degrees=True).as_quat()
    return np.asarray([xyzw[3], xyzw[0], xyzw[1], xyzw[2]], dtype=np.float32)


class EndpointTarget:
    """Right-arm endpoint target with deterministic keyboard semantics."""

    def __init__(self, *, workspace_min: tuple[float, float, float], workspace_max: tuple[float, float, float]) -> None:
        self.left_pos = np.asarray([0.345, -0.1175, 0.4157], dtype=np.float32)
        self.left_rpy = np.asarray([180.0, 0.0, 90.0], dtype=np.float32)
        self.home_right_pos = np.asarray([0.715, -0.1175, 0.4157], dtype=np.float32)
        self.home_right_rpy = np.asarray([-180.0, 0.0, -90.0], dtype=np.float32)
        self.workspace_min = np.asarray(workspace_min, dtype=np.float32)
        self.workspace_max = np.asarray(workspace_max, dtype=np.float32)
        self.right_pos = self.home_right_pos.copy()
        self.right_rpy = self.home_right_rpy.copy()
        self.right_gripper = 0.0
        self._last_toggle = False
        self.last_clamp_axes: list[str] = []

    def reset(self) -> None:
        self.right_pos = self.home_right_pos.copy()
        self.right_rpy = self.home_right_rpy.copy()
        self.right_gripper = 0.0
        self._last_toggle = False
        self.last_clamp_axes = []

    def update_from_keys(self, keys: set[str], *, linear_step: float, angular_step_deg: float) -> None:
        if "r" in keys:
            self.reset()
            return

        delta = np.zeros(3, dtype=np.float32)
        if "w" in keys:
            delta[0] += linear_step
        if "s" in keys:
            delta[0] -= linear_step
        if "d" in keys:
            delta[1] += linear_step
        if "a" in keys:
            delta[1] -= linear_step
        if "e" in keys:
            delta[2] += linear_step
        if "q" in keys:
            delta[2] -= linear_step
        requested_pos = self.right_pos + delta
        self.last_clamp_axes = []
        if requested_pos[0] < self.workspace_min[0] or requested_pos[0] > self.workspace_max[0]:
            self.last_clamp_axes.append("x")
        if requested_pos[1] < self.workspace_min[1] or requested_pos[1] > self.workspace_max[1]:
            self.last_clamp_axes.append("y")
        if requested_pos[2] < self.workspace_min[2] or requested_pos[2] > self.workspace_max[2]:
            self.last_clamp_axes.append("z")
        self.right_pos = np.clip(requested_pos, self.workspace_min, self.workspace_max)

        if "u" in keys:
            self.right_rpy[0] += angular_step_deg
        if "o" in keys:
            self.right_rpy[0] -= angular_step_deg
        if "i" in keys:
            self.right_rpy[1] += angular_step_deg
        if "k" in keys:
            self.right_rpy[1] -= angular_step_deg
        if "j" in keys:
            self.right_rpy[2] += angular_step_deg
        if "l" in keys:
            self.right_rpy[2] -= angular_step_deg
        self.right_rpy = ((self.right_rpy + 180.0) % 360.0) - 180.0

        toggle = "g" in keys
        if toggle and not self._last_toggle:
            self.right_gripper = 1.0 - self.right_gripper
        self._last_toggle = toggle

    def action18(self) -> np.ndarray:
        left_quat = quat_wxyz_from_euler_xyz_deg(*self.left_rpy)
        right_quat = quat_wxyz_from_euler_xyz_deg(*self.right_rpy)
        action = np.zeros((18,), dtype=np.float32)
        action[0:3] = self.left_pos
        action[3:7] = left_quat
        action[7] = 0.0
        action[8] = 0.0
        action[9:12] = self.right_pos
        action[12:16] = right_quat
        action[17] = 0.04 * self.right_gripper
        action[16] = -action[17]
        return action

    def target_pose(self) -> np.ndarray:
        right_quat = quat_wxyz_from_euler_xyz_deg(*self.right_rpy)
        return np.concatenate([self.right_pos, right_quat, np.asarray([self.right_gripper], dtype=np.float32)])


class KeyboardState:
    """Global keyboard state via pynput, with a no-key fallback for scripted mode."""

    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.events: list[tuple[str, str, str]] = []
        self.stop_requested = False
        self.success_requested = False
        self.start_requested = False
        self.cancel_requested = False
        self.speed_mode = "normal"
        self._listener = None

    def start(self) -> None:
        try:
            from pynput import keyboard
        except Exception as exc:
            raise RuntimeError(f"pynput is required for interactive endpoint control: {exc}") from exc

        def normalize(key) -> str | None:
            if hasattr(key, "char") and key.char:
                return str(key.char).lower()
            if key == keyboard.Key.esc:
                return "esc"
            return None

        def on_press(key):
            value = normalize(key)
            if value == "esc":
                self.events.append(("press", "esc", "global"))
                self.stop_requested = True
                return False
            if value == "n":
                self.events.append(("press", "n", "global"))
                self.success_requested = True
                self.stop_requested = True
                return False
            if value == "b":
                self.events.append(("press", "b", "global"))
                self.start_requested = True
                return True
            if value == "c":
                self.events.append(("press", "c", "global"))
                self.cancel_requested = True
                self.stop_requested = True
                return False
            if value == "1":
                self.events.append(("press", "1", "global"))
                self.speed_mode = "slow"
                return True
            if value == "2":
                self.events.append(("press", "2", "global"))
                self.speed_mode = "normal"
                return True
            if value:
                if value not in self.keys:
                    self.events.append(("press", value, "global"))
                self.keys.add(value)
            return True

        def on_release(key):
            value = normalize(key)
            if value:
                if value in self.keys:
                    self.events.append(("release", value, "global"))
                self.keys.discard(value)
            return True

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def drain_events(self) -> list[tuple[str, str, str]]:
        events = list(self.events)
        self.events.clear()
        return events


def scripted_keys(step: int) -> set[str]:
    keys: set[str] = set()
    if 8 <= step < 28:
        keys.add("w")
    if 28 <= step < 48:
        keys.add("e")
    if 48 <= step < 68:
        keys.add("j")
    if step == 70:
        keys.add("g")
    if 90 <= step < 108:
        keys.add("s")
    return keys


def first_env(value) -> np.ndarray:
    array = tensor_to_numpy(value)
    if array.ndim >= 2 and array.shape[0] == 1:
        return array[0]
    return array


def right_eef_state(env) -> np.ndarray:
    frame = env.scene["right_ee_frame"]
    pos = first_env(frame.data.target_pos_w)
    quat = first_env(frame.data.target_quat_w)
    return np.concatenate([pos[0], quat[0]]).astype(np.float32)


def make_action_tensor(env, action_np: np.ndarray):
    import torch

    action_shape = env.action_space.shape
    return torch.as_tensor(action_np, dtype=torch.float32, device=env.device).reshape(1, -1).repeat(action_shape[0], 1)


def print_interactive_status(
    *,
    step_idx: int,
    target: EndpointTarget,
    keyboard_state: KeyboardState,
    linear_step: float,
    angular_step_deg: float,
    current_eef: np.ndarray,
) -> None:
    clamp = ",".join(target.last_clamp_axes) if target.last_clamp_axes else "none"
    keys = "".join(sorted(keyboard_state.keys)) or "-"
    pos = target.right_pos.astype(float)
    rpy = target.right_rpy.astype(float)
    eef = current_eef[:3].astype(float)
    print(
        "status "
        f"step={step_idx} mode={keyboard_state.speed_mode} keys={keys} "
        f"target_xyz=({pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f}) "
        f"target_rpy=({rpy[0]:.1f},{rpy[1]:.1f},{rpy[2]:.1f}) "
        f"current_xyz=({eef[0]:.3f},{eef[1]:.3f},{eef[2]:.3f}) "
        f"gripper={target.right_gripper:.2f} step=({linear_step:.4f}m,{angular_step_deg:.2f}deg) "
        f"clamp={clamp}",
        flush=True,
    )


def make_live_preview_frame(images: dict[str, np.ndarray], *, status: str) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default()
    tiles: list[np.ndarray] = []
    for camera in CAMERAS:
        tile = images[camera].copy()
        image = Image.fromarray(tile)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, tile.shape[1], 32), fill=(255, 255, 255))
        draw.text((10, 9), camera, fill=(0, 0, 0), font=font)
        tile = np.asarray(image)
        tiles.append(tile)
    frame = np.concatenate(tiles, axis=1)
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, frame.shape[0] - 34, frame.shape[1], frame.shape[0]), fill=(255, 255, 255))
    draw.text((12, frame.shape[0] - 24), status, fill=(0, 0, 0), font=font)
    return np.asarray(image)


class LivePreview:
    """Realtime multiview preview with OpenCV when available and Tk fallback otherwise."""

    def __init__(self, window_name: str) -> None:
        self.window_name = window_name
        self.backend = "none"
        self._cv2 = None
        self._tk = None
        self._image_tk = None
        self._root = None
        self._label = None
        self._last_key = -1
        self.keys: set[str] = set()
        self.events: list[tuple[str, str, str]] = []
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            import cv2

            gui_line = ""
            for line in cv2.getBuildInformation().splitlines():
                if "GUI:" in line:
                    gui_line = line
                    break
            if "NONE" not in gui_line:
                self._cv2 = cv2
                self.backend = "opencv"
                return
        except Exception:
            pass

        import tkinter as tk
        from PIL import ImageTk

        self._tk = tk
        self._image_tk = ImageTk
        self._root = tk.Tk()
        self._root.title(self.window_name)
        self._label = tk.Label(self._root)
        self._label.pack()
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.bind("<KeyPress>", self._on_key_press)
        self._root.bind("<KeyRelease>", self._on_key_release)
        self.backend = "tk"

    def _on_close(self) -> None:
        self._last_key = ord("c")
        self.events.append(("press", "c", "preview"))

    @staticmethod
    def _event_key(event) -> str:
        value = (event.keysym or "").lower()
        char = (event.char or "").lower()
        if value == "escape":
            return "esc"
        if char:
            return char[0]
        return ""

    def _on_key_press(self, event) -> None:
        key = self._event_key(event)
        if not key:
            return
        self._last_key = 27 if key == "esc" else ord(key)
        if key in CONTROL_KEYS:
            if key not in self.keys:
                self.events.append(("press", key, "preview"))
            self.keys.add(key)
        else:
            self.events.append(("press", key, "preview"))

    def _on_key_release(self, event) -> None:
        key = self._event_key(event)
        if not key:
            return
        if key in self.keys:
            self.events.append(("release", key, "preview"))
        self.keys.discard(key)

    def show(self, *, images: dict[str, np.ndarray], status: str) -> int:
        frame = make_live_preview_frame(images, status=status)
        if self.backend == "opencv":
            assert self._cv2 is not None
            self._cv2.imshow(self.window_name, self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2BGR))
            return int(self._cv2.waitKey(1) & 0xFF)

        if self.backend == "tk":
            assert self._root is not None
            assert self._label is not None
            assert self._image_tk is not None
            from PIL import Image

            image = Image.fromarray(frame)
            photo = self._image_tk.PhotoImage(image=image)
            self._label.configure(image=photo)
            self._label.image = photo
            self._root.update_idletasks()
            self._root.update()
            key = self._last_key
            self._last_key = -1
            return key

        return -1

    def drain_events(self) -> list[tuple[str, str, str]]:
        events = list(self.events)
        self.events.clear()
        return events

    def close(self) -> None:
        if self.backend == "opencv" and self._cv2 is not None:
            self._cv2.destroyWindow(self.window_name)
        elif self.backend == "tk" and self._root is not None:
            try:
                self._root.destroy()
            except Exception:
                pass


def write_endpoint_hdf5(
    dataset_path: Path,
    *,
    observations: list[dict[str, np.ndarray]],
    attrs: dict[str, Any],
    overwrite: bool,
) -> None:
    if dataset_path.exists():
        if overwrite:
            dataset_path.unlink()
        else:
            raise FileExistsError(f"dataset already exists: {dataset_path}")
    dataset_path.parent.mkdir(parents=True, exist_ok=True)

    actions = np.stack([obs["joint_target"] for obs in observations]).astype(np.float32)
    left_state = np.stack([obs["left_joint_pos_rel"] for obs in observations]).astype(np.float32)
    right_state = np.stack([obs["right_joint_pos_rel"] for obs in observations]).astype(np.float32)
    endpoint_action18 = np.stack([obs["endpoint_action18"] for obs in observations]).astype(np.float32)
    target_eef_pose = np.stack([obs["target_eef_pose"] for obs in observations]).astype(np.float32)
    current_eef_pose = np.stack([obs["current_eef_pose"] for obs in observations]).astype(np.float32)
    images = {camera: np.stack([obs[camera] for obs in observations]).astype(np.uint8) for camera in CAMERAS}

    with h5py.File(dataset_path, "w") as h5:
        data = h5.create_group("data")
        demo = data.create_group("demo_0")
        demo.attrs["num_samples"] = actions.shape[0]
        for key, value in attrs.items():
            if isinstance(value, (dict, list, tuple)):
                demo.attrs[key] = json.dumps(value, sort_keys=True)
            else:
                demo.attrs[key] = value
        demo.create_dataset("actions", data=actions, compression="lzf")
        demo.create_dataset("processed_actions", data=actions, compression="lzf")
        obs_group = demo.create_group("obs")
        obs_group.create_dataset("actions", data=actions, compression="lzf")
        obs_group.create_dataset("left_joint_pos_rel", data=left_state, compression="lzf")
        obs_group.create_dataset("right_joint_pos_rel", data=right_state, compression="lzf")
        obs_group.create_dataset("endpoint_action18", data=endpoint_action18, compression="lzf")
        obs_group.create_dataset("target_eef_pose", data=target_eef_pose, compression="lzf")
        obs_group.create_dataset("current_eef_pose", data=current_eef_pose, compression="lzf")
        for camera in CAMERAS:
            obs_group.create_dataset(camera, data=images[camera], compression="lzf")


def render_control_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['stage']} Endpoint Keyboard Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Mode: `{report['mode']}`",
        f"- Frames: `{report['frames']}`",
        f"- Dataset: `{report.get('dataset_file', '')}`",
        f"- Right endpoint displacement: `{report['right_endpoint_displacement_m']:.6f} m`",
        f"- Right joint target delta: `{report['right_joint_target_delta_max_abs']:.6f}`",
        f"- Max image diff: `{report['max_image_diff']:.6f}`",
        "",
        "## Keymap",
        "",
        "W/S x +/-, A/D y +/-, E/Q z +/-, U/O roll +/-, I/K pitch +/-, J/L yaw +/-, G gripper toggle, R reset, N success and stop, Esc stop.",
        "",
        "## Issues",
        "",
    ]
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    else:
        lines.append("- No endpoint keyboard issues.")
    lines.append("")
    return "\n".join(lines)


def print_key_event(
    *,
    action: str,
    value: str,
    source: str,
    recording_active: bool,
    frames: int,
    speed_mode: str,
) -> None:
    print(
        f"[key] {action}={value} source={source} "
        f"recording={'yes' if recording_active else 'no'} frames={frames} speed={speed_mode}",
        flush=True,
    )


def run_control(args: argparse.Namespace) -> int:
    stage = "PHYS-9.2" if args.stage == "phys92" else "PHYS-9.3"
    session = setup_logging(session_name=args.session_name)
    if args.mode == "interactive":
        for handler in list(session.data.handlers):
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                session.data.removeHandler(handler)
    session.run.info("endpoint_keyboard_start stage=%s mode=%s headless=%s", stage, args.mode, args.headless)
    log_environment(session, extra={"stage": stage, "mode": args.mode, "dataset_file": args.dataset_file or ""})

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=args.headless, enable_cameras=True)
    simulation_app = app_launcher.app
    env = None
    keyboard_state = KeyboardState()
    result = 1
    preview_enabled = bool(args.mode == "interactive" and not args.headless and not args.no_camera_preview)
    preview_window_name = "X-Trainer live cameras"
    live_preview: LivePreview | None = None

    try:
        import gymnasium as gym
        from isaaclab_tasks.utils import parse_env_cfg
        import leisaac.tasks  # noqa: F401

        env_cfg = parse_env_cfg(args.task, device=args.device, num_envs=args.num_envs)
        env_cfg.use_teleop_device("xtrainer_vr")
        env_cfg.recorders = None
        env_cfg.seed = args.seed
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None
        if hasattr(env_cfg, "terminations") and hasattr(env_cfg.terminations, "success"):
            env_cfg.terminations.success = None
        for camera_name in ("stereo_left", "stereo_right"):
            if hasattr(env_cfg.scene, camera_name):
                setattr(env_cfg.scene, camera_name, None)
                session.run.info("disabled_scene_camera=%s", camera_name)

        env = gym.make(args.task, cfg=env_cfg).unwrapped
        session.run.info("gym_make_ok action_space=%s observation_space=%s", env.action_space, env.observation_space)
        obs, info = env.reset()
        env.sim.render()
        if len(env.action_space.shape) != 2 or env.action_space.shape[-1] != 18:
            raise RuntimeError(f"unexpected endpoint action space: {env.action_space.shape}")

        target = EndpointTarget(
            workspace_min=(args.workspace_x_min, args.workspace_y_min, args.workspace_z_min),
            workspace_max=(args.workspace_x_max, args.workspace_y_max, args.workspace_z_max),
        )
        if args.mode == "interactive":
            keyboard_state.start()
            if preview_enabled:
                try:
                    live_preview = LivePreview(preview_window_name)
                    session.run.info("live_preview_backend=%s", live_preview.backend)
                except Exception as exc:
                    preview_enabled = False
                    session.run.error("live_preview_disabled error=%r", exc)
                    print(
                        "[preview][ERROR] live 3-camera preview could not open. "
                        "Isaac will stay open, but this run does not satisfy visual collection validation.",
                        flush=True,
                    )
            print("Endpoint keyboard control started.", flush=True)
            print(
                "Keys: B start recording, W/S x, A/D y, E/Q z, U/O roll, I/K pitch, J/L yaw, "
                "G gripper, R reset, 1 slow, 2 normal, N save-success-stop, Esc save-stop, C cancel-no-save.",
                flush=True,
            )
            if preview_enabled and live_preview is not None:
                print(
                    f"Live preview: top + left_wrist + right_wrist ({live_preview.backend}). "
                    "Click the Isaac or preview window before pressing keys.",
                    flush=True,
                )
            if args.dataset_file:
                dataset_path_hint = (ROOT / args.dataset_file).resolve() if not Path(args.dataset_file).is_absolute() else Path(args.dataset_file)
                print(f"Output HDF5 after save: {dataset_path_hint}", flush=True)
            print("Terminal feedback is active: every captured key prints a [key] line.", flush=True)

        initial_images, initial_stats = capture_multiview(env, obs, "preflight_initial", session)
        initial_eef = right_eef_state(env)
        initial_right_target = policy_array(obs, "right_joint_pos_target").copy()
        observations: list[dict[str, np.ndarray]] = []
        start_time = time.monotonic()
        next_tick = start_time
        success = False
        canceled = False
        recording_active = args.mode != "interactive"
        recording_started_at_step = 0 if recording_active else None
        stop_reason = "max_steps"

        for step_idx in range(args.max_steps):
            if args.mode == "interactive":
                active_keys = set(keyboard_state.keys)
                if preview_enabled and live_preview is not None:
                    active_keys.update(live_preview.keys)
                for action, value, source in keyboard_state.drain_events():
                    print_key_event(
                        action=action,
                        value=value,
                        source=source,
                        recording_active=recording_active,
                        frames=len(observations),
                        speed_mode=keyboard_state.speed_mode,
                    )
                if keyboard_state.start_requested and not recording_active:
                    recording_active = True
                    recording_started_at_step = step_idx
                    keyboard_state.start_requested = False
                    print(f"[recording] START step={step_idx}. Frames are now being recorded.", flush=True)
                if keyboard_state.cancel_requested:
                    canceled = True
                    stop_reason = "cancel"
                    print("[recording] CANCEL requested. Current episode will not be saved or exported.", flush=True)
                    break
                if keyboard_state.success_requested:
                    success = True
                if keyboard_state.stop_requested:
                    stop_reason = "success" if success else "stop"
                    if success:
                        print("[recording] N pressed. Saving episode with human_success=true.", flush=True)
                    else:
                        print("[recording] Esc pressed. Saving episode with human_success=false.", flush=True)
                    break
            else:
                active_keys = scripted_keys(step_idx)
                if step_idx == args.max_steps - 1:
                    success = bool(args.scripted_success)

            speed_scale = args.slow_scale if args.mode == "interactive" and keyboard_state.speed_mode == "slow" else 1.0
            linear_step = args.linear_step * speed_scale
            angular_step_deg = args.angular_step_deg * speed_scale
            previous_gripper = target.right_gripper
            target.update_from_keys(active_keys, linear_step=linear_step, angular_step_deg=angular_step_deg)
            if args.mode == "interactive" and target.right_gripper != previous_gripper:
                gripper_state = "closed" if target.right_gripper > 0.5 else "open"
                print(
                    f"[gripper] toggled state={gripper_state} value={target.right_gripper:.2f} "
                    f"frames={len(observations)} recording={'yes' if recording_active else 'no'}",
                    flush=True,
                )
            action18 = target.action18()
            obs, reward, terminated, truncated, info = env.step(make_action_tensor(env, action18))
            env.sim.render()

            left_state = policy_array(obs, "left_joint_pos_rel").astype(np.float32)
            right_state = policy_array(obs, "right_joint_pos_rel").astype(np.float32)
            left_target = policy_array(obs, "left_joint_pos_target").astype(np.float32)
            right_target = policy_array(obs, "right_joint_pos_target").astype(np.float32)
            joint_target = np.concatenate([left_target, right_target]).astype(np.float32)
            sample = {
                "left_joint_pos_rel": left_state,
                "right_joint_pos_rel": right_state,
                "joint_target": joint_target,
                "endpoint_action18": action18.astype(np.float32),
                "target_eef_pose": target.target_pose().astype(np.float32),
                "current_eef_pose": right_eef_state(env).astype(np.float32),
            }
            preview_images: dict[str, np.ndarray] = {}
            for camera in CAMERAS:
                from phys_data_gen.image_validation import extract_obs_image, to_numpy_image

                preview_images[camera] = to_numpy_image(extract_obs_image(obs, camera))
                sample[camera] = preview_images[camera]
            if recording_active:
                observations.append(sample)
            session.data.info(
                "step=%d recording=%s keys=%s right_pos=%s right_rpy=%s gripper=%.3f clamp=%s action_max_abs=%.6f",
                step_idx,
                recording_active,
                "".join(sorted(active_keys)),
                target.right_pos.astype(float).tolist(),
                target.right_rpy.astype(float).tolist(),
                target.right_gripper,
                ",".join(target.last_clamp_axes) if target.last_clamp_axes else "none",
                float(np.max(np.abs(action18))),
            )
            if preview_enabled:
                assert live_preview is not None
                status = (
                    f"{'REC' if recording_active else 'READY'} frames={len(observations)} "
                    f"mode={keyboard_state.speed_mode} gripper={target.right_gripper:.1f} "
                    "B=start N=save-success Esc=save-fail C=cancel"
                )
                key = live_preview.show(images=preview_images, status=status)
                for action, value, source in live_preview.drain_events():
                    print_key_event(
                        action=action,
                        value=value,
                        source=source,
                        recording_active=recording_active,
                        frames=len(observations),
                        speed_mode=keyboard_state.speed_mode,
                    )
                if key in (ord("b"), ord("B")) and not recording_active:
                    keyboard_state.start_requested = True
                elif key in (ord("c"), ord("C")):
                    keyboard_state.cancel_requested = True
                    keyboard_state.stop_requested = True
                elif key in (ord("n"), ord("N")):
                    keyboard_state.success_requested = True
                    keyboard_state.stop_requested = True
                elif key == 27:
                    keyboard_state.stop_requested = True
                elif key == ord("1"):
                    keyboard_state.speed_mode = "slow"
                elif key == ord("2"):
                    keyboard_state.speed_mode = "normal"
            if args.mode == "interactive" and step_idx % max(1, args.interactive_status_interval) == 0:
                print_interactive_status(
                    step_idx=step_idx,
                    target=target,
                    keyboard_state=keyboard_state,
                    linear_step=linear_step,
                    angular_step_deg=angular_step_deg,
                    current_eef=sample["current_eef_pose"],
                )

            if args.mode == "interactive":
                next_tick += 1.0 / args.step_hz
                sleep_time = next_tick - time.monotonic()
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 1.0 / args.step_hz))

        if args.mode == "interactive":
            keyboard_state.stop()
            print(f"[recording] stop_reason={stop_reason} recorded_frames={len(observations)}", flush=True)

        if canceled:
            mark_fail(session, "CANCEL_PHYS93_ENDPOINT_RECORDING", "recording canceled by user; no dataset saved")
            result = 30
            return result

        if args.mode == "interactive" and not recording_active:
            raise RuntimeError("recording never started. Press B to start recording before saving.")

        if len(observations) < args.min_frames:
            raise RuntimeError(f"not enough frames collected: {len(observations)} < {args.min_frames}")

        final_obs = obs
        final_images, final_stats = capture_multiview(env, final_obs, "preflight_final", session)
        final_eef = right_eef_state(env)
        final_right_target = policy_array(final_obs, "right_joint_pos_target").copy()

        image_diffs = {camera: mean_abs_diff(initial_images[camera], final_images[camera]) for camera in CAMERAS}
        endpoint_displacement = float(np.linalg.norm(final_eef[:3] - initial_eef[:3]))
        target_delta = float(np.max(np.abs(final_right_target - initial_right_target)))
        issues: list[str] = []
        if endpoint_displacement < args.min_endpoint_displacement:
            issues.append(f"endpoint displacement too small: {endpoint_displacement:.6f} m")
        if target_delta < args.min_joint_target_delta:
            issues.append(f"right joint target delta too small: {target_delta:.6f}")
        if max(image_diffs.values()) < args.min_image_diff:
            issues.append(f"image diff too small: {image_diffs}")

        dataset_path = None
        validation = None
        if args.dataset_file:
            dataset_path = (ROOT / args.dataset_file).resolve() if not Path(args.dataset_file).is_absolute() else Path(args.dataset_file)
            write_endpoint_hdf5(
                dataset_path,
                observations=observations,
                overwrite=args.overwrite,
                attrs={
                    "stage": stage,
                    "task": args.task,
                    "success": bool(success),
                    "control_mode": "endpoint_keyboard",
                    "source_action": "xtrainer_vr_pose18",
                    "stored_actions": "post_ik_joint_pos_target16",
                    "fps": float(args.step_hz),
                    "num_samples": len(observations),
                    "recording_started_at_step": int(recording_started_at_step or 0),
                    "stop_reason": stop_reason,
                    "workspace_min": target.workspace_min.astype(float).tolist(),
                    "workspace_max": target.workspace_max.astype(float).tolist(),
                },
            )
            if args.mode == "interactive":
                print(f"[recording] SAVED hdf5={dataset_path} frames={len(observations)}", flush=True)
            validation = validate_hdf5_dataset(dataset_path)
            (session.root / "dataset_validation_report.json").write_text(
                json.dumps(validation.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (session.root / "dataset_validation_report.md").write_text(render_markdown_report(validation), encoding="utf-8")
            if not validation.passed:
                issues.append("recorded HDF5 failed validator")

        report = {
            "status": "PASS" if not issues else "FAIL",
            "stage": stage,
            "mode": args.mode,
            "task": args.task,
            "seed": args.seed,
            "frames": len(observations),
            "dataset_file": str(dataset_path) if dataset_path else "",
            "dataset_validation_passed": validation.passed if validation else None,
            "success_marked": bool(success),
            "recording_started_at_step": recording_started_at_step,
            "stop_reason": stop_reason,
            "workspace_min": target.workspace_min.astype(float).tolist(),
            "workspace_max": target.workspace_max.astype(float).tolist(),
            "right_endpoint_displacement_m": endpoint_displacement,
            "right_joint_target_delta_max_abs": target_delta,
            "image_diffs_initial_final": image_diffs,
            "max_image_diff": float(max(image_diffs.values())),
            "initial_eef": initial_eef.astype(float).tolist(),
            "final_eef": final_eef.astype(float).tolist(),
            "initial_stats": initial_stats,
            "final_stats": final_stats,
            "issues": issues,
        }
        report_name = "endpoint_keyboard_preflight_report" if args.stage == "phys92" else "endpoint_keyboard_record_report"
        save_json(session.root / f"{report_name}.json", report)
        (session.root / f"{report_name}.md").write_text(render_control_markdown(report), encoding="utf-8")
        session.data.info("endpoint_keyboard_report=%s", json.dumps(report, sort_keys=True))

        if issues:
            marker = "FAIL_PHYS92_ENDPOINT_KEYBOARD_PREFLIGHT" if args.stage == "phys92" else "FAIL_PHYS93_ENDPOINT_RECORDING_PREFLIGHT"
            mark_fail(session, marker, "; ".join(issues))
            raise RuntimeError("; ".join(issues))
        marker = "PASS_PHYS92_ENDPOINT_KEYBOARD_PREFLIGHT" if args.stage == "phys92" else "PASS_PHYS93_ENDPOINT_RECORDING_CORE"
        mark_pass(session, marker, f"{stage} endpoint keyboard passed")
        if args.mode == "interactive":
            print(f"[recording] CORE PASS marker={session.root / marker}", flush=True)
        result = 0
    except BaseException as exc:
        session.run.error("endpoint_keyboard_failed type=%s error=%r", type(exc).__name__, exc)
        session.run.error("traceback:\n%s", traceback.format_exc())
        marker = "FAIL_PHYS92_ENDPOINT_KEYBOARD_PREFLIGHT" if args.stage == "phys92" else "FAIL_PHYS93_ENDPOINT_RECORDING_PREFLIGHT"
        mark_fail(session, marker, f"{type(exc).__name__}: {exc}")
        result = 10
    finally:
        keyboard_state.stop()
        if env is not None:
            try:
                env.close()
            except Exception as exc:
                session.run.warning("env_close_warning=%r", exc)
        try:
            if live_preview is not None:
                live_preview.close()
        except Exception as exc:
            session.run.warning("preview_close_warning=%r", exc)
        try:
            simulation_app.close(wait_for_replicator=False, skip_cleanup=True)
        except TypeError:
            simulation_app.close()
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["phys92", "phys93"], required=True)
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--mode", choices=["scripted", "interactive"], default="scripted")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--task", default="LeIsaac-XTrainer-PickCube-v0")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=92)
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--min-frames", type=int, default=20)
    parser.add_argument("--step-hz", type=float, default=30.0)
    parser.add_argument("--linear-step", type=float, default=0.004)
    parser.add_argument("--angular-step-deg", type=float, default=1.5)
    parser.add_argument("--slow-scale", type=float, default=0.35)
    parser.add_argument("--interactive-status-interval", type=int, default=15)
    parser.add_argument("--no-camera-preview", action="store_true")
    parser.add_argument("--workspace-x-min", type=float, default=0.42)
    parser.add_argument("--workspace-x-max", type=float, default=1.02)
    parser.add_argument("--workspace-y-min", type=float, default=-0.45)
    parser.add_argument("--workspace-y-max", type=float, default=0.22)
    parser.add_argument("--workspace-z-min", type=float, default=0.16)
    parser.add_argument("--workspace-z-max", type=float, default=0.68)
    parser.add_argument("--min-endpoint-displacement", type=float, default=0.012)
    parser.add_argument("--min-joint-target-delta", type=float, default=0.01)
    parser.add_argument("--min-image-diff", type=float, default=0.2)
    parser.add_argument("--scripted-success", action="store_true")
    parser.add_argument("--dataset-file", default="")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run_control(parse_args()))
