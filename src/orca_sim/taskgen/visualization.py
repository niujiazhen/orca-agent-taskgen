"""Interactive and offscreen visualization for generated bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mujoco

from orca_sim.taskgen import load_environment


def view_bundle(path: str | Path) -> None:
    env = load_environment(path, render_mode="human")
    try:
        env.reset(seed=0, options={"randomization_scale": 0.0})
        while env._viewer is None or env._viewer.is_running():
            _, _, terminated, truncated, _ = env.step(env.scripted_action())
            if terminated or truncated:
                env.reset(seed=0, options={"randomization_scale": 0.0})
    finally:
        env.close()


def preview_bundle(path: str | Path, *, max_steps: int | None = None) -> dict[str, Any]:
    try:
        import imageio.v2 as imageio
    except ImportError as exc:
        raise RuntimeError('Preview generation requires: pip install "orca_sim[visualization]"') from exc

    bundle = Path(path).resolve()
    env = load_environment(bundle)
    visual = env.task["visualization"]
    renderer = mujoco.Renderer(
        env.model, height=int(visual["height"]), width=int(visual["width"])
    )
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(env.model, camera)
    camera.azimuth = 135.0
    camera.elevation = -25.0
    camera.distance = 0.55
    camera.lookat[:] = [0.03, 0.03, 0.18]
    frames = []
    info: dict[str, Any] = {}
    try:
        env.reset(seed=0, options={"randomization_scale": 0.0})
        renderer.update_scene(env.data, camera=camera)
        frames.extend([renderer.render().copy() for _ in range(8)])
        limit = min(env.max_episode_steps, max_steps or env.max_episode_steps)
        for _ in range(limit):
            _, _, terminated, truncated, info = env.step(env.scripted_action())
            renderer.update_scene(env.data, camera=camera)
            frames.append(renderer.render().copy())
            if terminated or truncated:
                break
        frames.extend([frames[-1].copy() for _ in range(12)])
    finally:
        renderer.close()
        env.close()

    png_path = bundle / "preview.png"
    mp4_path = bundle / "preview.mp4"
    imageio.imwrite(png_path, frames[len(frames) // 2])
    imageio.mimsave(mp4_path, frames, fps=int(visual["fps"]), macro_block_size=1)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = sorted(set(manifest["files"]) | {"preview.png", "preview.mp4"})
    manifest["preview"] = {"frames": len(frames), "scripted_success": bool(info.get("is_success"))}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "generated",
        "preview_png": str(png_path),
        "preview_mp4": str(mp4_path),
        "frames": len(frames),
        "scripted_success": bool(info.get("is_success")),
    }
