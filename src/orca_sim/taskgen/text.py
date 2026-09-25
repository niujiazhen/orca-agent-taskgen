"""Bounded natural-language request parser used by the Codex skill and CLI."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any


class UnsupportedTaskError(ValueError):
    """Raised when a request is outside the v2 capability catalog."""


COLORS = {
    "red": [0.85, 0.15, 0.12, 1.0],
    "红": [0.85, 0.15, 0.12, 1.0],
    "blue": [0.12, 0.35, 0.85, 1.0],
    "蓝": [0.12, 0.35, 0.85, 1.0],
    "green": [0.15, 0.75, 0.25, 1.0],
    "绿": [0.15, 0.75, 0.25, 1.0],
    "yellow": [0.9, 0.75, 0.1, 1.0],
    "黄": [0.9, 0.75, 0.1, 1.0],
}

UNSUPPORTED = {
    "screw": "tool use and screw assembly",
    "螺丝": "工具使用和螺丝装配",
    "stack": "stacking",
    "堆叠": "堆叠",
    "insert": "insertion",
    "插入": "插入",
    "mesh": "external meshes",
    "stl": "external STL meshes",
    "obj": "external OBJ meshes",
    "双手": "双手任务",
    "two hands": "two-hand tasks",
}


def _slug_words(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(word.title() for word in words[:4]) or f"Task{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}"


def _rgba(text: str, default: list[float], *, last: bool = False) -> list[float]:
    lowered = text.lower()
    matches = [(lowered.rfind(token) if last else lowered.find(token), rgba) for token, rgba in COLORS.items()]
    matches = [(position, rgba) for position, rgba in matches if position >= 0]
    if matches:
        position, rgba = (max(matches) if last else min(matches))
        del position
        return list(rgba)
    return list(default)


def _base_task(text: str, family: str, env_id: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "task": {
            "env_id": env_id,
            "name": text.strip()[:120],
            "family": family,
            "source_text": text.strip(),
            "hand": {
                "version": "v1",
                "side": "right",
                "base_control": "kinematic_6dof",
                "initial_position": [0.04, 0.0, 0.04575],
                "initial_quaternion": [1.0, 0.0, 0.0, 0.0],
                "workspace": {"min": [-0.12, -0.18, -0.02], "max": [0.20, 0.18, 0.24]},
            },
            "scene": {
                "table": {
                    "position": [0.04, 0.04, 0.10],
                    "half_size": [0.24, 0.24, 0.10],
                    "rgba": [0.20, 0.30, 0.40, 1.0],
                    "friction": [1.2, 0.01, 0.001],
                }
            },
            "reset": {
                "object_position_jitter": [0.005, 0.005, 0.0],
                "wrist_position_jitter": [0.002, 0.002, 0.002],
            },
            "control": {"frame_skip": 5, "translation_step": 0.004, "rotation_step": 0.04},
            "reward": {"progress": 10.0, "grasp": 2.0, "success": 100.0, "action_penalty": 0.001},
            "success": {
                "hold_steps": 20,
                "gesture_tolerance": 0.05,
                "lift_height": 0.05,
                "target_radius": 0.03,
                "max_object_speed": 0.05,
            },
            "safety": {"max_episode_steps": 500, "drop_height": 0.17, "assistive_grasp": True},
            "visualization": {"width": 640, "height": 480, "fps": 30, "camera": "free"},
        },
    }


def task_spec_from_text(text: str, *, env_id: str | None = None) -> dict[str, Any]:
    """Convert a bounded Chinese/English request into a deterministic v2 TaskSpec."""

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Task request must not be empty")
    lowered = cleaned.lower()
    for token, capability in UNSUPPORTED.items():
        if token in lowered:
            raise UnsupportedTaskError(
                f"Unsupported v2 request ({capability}). Supported tasks are gesture, "
                "pick up, and pick/place with a box, cylinder, or sphere."
            )

    is_place = any(token in lowered for token in ("放到", "放置", "place", "move to"))
    is_pick = is_place or any(token in lowered for token in ("拿起", "抓起", "捏起", "pick up", "lift"))
    family = "pick_place" if is_place else "pick_up" if is_pick else "gesture"
    generated_id = env_id or f"{_slug_words(cleaned)}-v0"
    spec = _base_task(cleaned, family, generated_id)
    task = spec["task"]

    if family == "gesture":
        # A free-space hand gesture does not require a support surface.
        task["scene"].pop("table", None)
        if any(token in lowered for token in ("三指", "three-finger", "three finger")):
            gesture = "three_finger_grasp_release"
        elif any(token in lowered for token in ("捏", "pinch", "拇指", "thumb")):
            gesture = "thumb_index_pinch_release"
        elif any(token in lowered for token in ("握拳", "拳", "fist", "half-close", "half close")):
            gesture = "open_half_close_fist_open"
        else:
            raise UnsupportedTaskError(
                "Unknown gesture. Use open/half-close/fist, thumb-index pinch/release, "
                "or three-finger grasp/release."
            )
        task["gesture"] = {"name": gesture}
        return spec

    # Tabletop manipulation uses a palm-down diagonal approach. This keeps the
    # wrist and palm above the support plane while the fingertips reach the
    # object. Gesture tasks retain the upright display pose from _base_task.
    task["hand"].update(
        {
            "initial_position": [0.013, 0.093, 0.486],
            "initial_quaternion": [0.0, 1.0, 0.0, 0.0],
            "workspace": {"min": [-0.20, -0.30, 0.30], "max": [0.30, 0.30, 0.70]},
        }
    )

    shape_tokens = ("方块", "立方体", "box", "cube", "圆柱", "cylinder", "球", "sphere", "ball")
    if not any(token in lowered for token in shape_tokens):
        raise UnsupportedTaskError(
            "Object shape is missing or unsupported. Specify a box/cube, cylinder, or sphere."
        )
    if any(token in lowered for token in ("圆柱", "cylinder")):
        shape, size = "cylinder", [0.014, 0.022, 0.014]
    elif any(token in lowered for token in ("球", "sphere", "ball")):
        shape, size = "sphere", [0.017, 0.017, 0.017]
    else:
        shape, size = "box", [0.016, 0.016, 0.016]
    half_height = size[1] if shape == "cylinder" else size[0] if shape == "sphere" else size[2]
    task["scene"]["object"] = {
        "name": "task_object",
        "shape": shape,
        "size": size,
        "mass": 0.04,
        "rgba": _rgba(lowered, [0.85, 0.25, 0.12, 1.0]),
        "friction": [1.2, 0.01, 0.001],
        "initial_position": [0.02, 0.065, 0.20 + half_height + 0.002],
    }
    if family == "pick_place":
        y = -0.075 if any(token in lowered for token in ("右", "right")) else 0.12
        target_position = [0.02, y, 0.20 + half_height + 0.002]
        task["scene"]["target"] = {
            "position": target_position,
            "radius": 0.03,
            "rgba": _rgba(lowered, [0.15, 0.75, 0.25, 0.35], last=True)[:3] + [0.35],
        }
    return deepcopy(spec)
