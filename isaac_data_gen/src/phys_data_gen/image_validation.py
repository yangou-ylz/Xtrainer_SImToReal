"""Image extraction and validation helpers for Isaac/LeIsaac camera smoke tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np


CAMERAS = ("top", "left_wrist", "right_wrist")


def to_numpy_image(value) -> np.ndarray:
    """Convert a tensor/array camera output to uint8 HWC RGB."""

    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    else:
        value = np.asarray(value)
    if value.ndim == 4:
        value = value[0]
    if value.ndim != 3:
        raise ValueError(f"expected HWC or NHWC image, got shape={value.shape}")
    if value.shape[-1] > 3:
        value = value[..., :3]
    if value.dtype != np.uint8:
        value = np.clip(value, 0, 255).astype(np.uint8)
    return value


def extract_obs_image(obs: dict, camera_name: str):
    """Return a camera observation from the common Isaac Lab observation layout."""

    if not isinstance(obs, dict):
        return None
    policy = obs.get("policy")
    if isinstance(policy, dict) and camera_name in policy:
        return policy[camera_name]
    if camera_name in obs:
        return obs[camera_name]
    return None


def image_stats(image: np.ndarray) -> dict[str, object]:
    """Return simple nonblank-image diagnostics."""

    grid = image[:: max(1, image.shape[0] // 64), :: max(1, image.shape[1] // 64), :]
    return {
        "shape": list(image.shape),
        "dtype": str(image.dtype),
        "min": int(np.min(image)),
        "max": int(np.max(image)),
        "mean": float(np.mean(image)),
        "std": float(np.std(image)),
        "unique_sample_count": int(len(np.unique(grid.reshape(-1, grid.shape[-1]), axis=0))),
    }


def mean_abs_diff(image_a: np.ndarray, image_b: np.ndarray) -> float:
    """Mean absolute pixel difference between two same-shaped images."""

    if image_a.shape != image_b.shape:
        raise ValueError(f"image shape mismatch: {image_a.shape} vs {image_b.shape}")
    return float(np.mean(np.abs(image_a.astype(np.int16) - image_b.astype(np.int16))))


def save_multiview_grid(images: dict[str, np.ndarray], output_path: Path, title: str | None = None) -> None:
    """Save top/left/right camera images as one labeled horizontal grid."""

    from PIL import Image, ImageDraw

    tiles = []
    label_h = 36 if title else 28
    for name in CAMERAS:
        image = Image.fromarray(images[name])
        canvas = Image.new("RGB", (image.width, image.height + label_h), "white")
        canvas.paste(image, (0, label_h))
        draw = ImageDraw.Draw(canvas)
        label = f"{title} | {name}" if title else name
        draw.text((10, 8), label, fill=(0, 0, 0))
        tiles.append(np.asarray(canvas))
    separator = np.full((tiles[0].shape[0], 8, 3), 255, dtype=np.uint8)
    grid = np.concatenate([tiles[0], separator, tiles[1], separator, tiles[2]], axis=1)
    Image.fromarray(grid).save(output_path)
