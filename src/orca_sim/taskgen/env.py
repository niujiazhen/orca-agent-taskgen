"""Generic Gymnasium environment backed by a generated pinch TaskSpec."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

from orca_sim.envs import BaseOrcaHandEnv
from orca_sim.taskgen.contracts import load_gesture_reference, load_task_spec

TASKGEN_ROOT = Path(__file__).resolve().parent


class PinchAndHoldEnv(BaseOrcaHandEnv):
    """Two-finger contact-and-hold task generated from a validated TaskSpec."""

    def __init__(
        self,
        *,
        spec_path: str | Path,
        scene_path: str | Path,
        render_mode: str | None = None,
        reset_randomization_scale: float = 1.0,
    ) -> None:
        self.spec_path = Path(spec_path).resolve()
        self.task_spec = load_task_spec(self.spec_path, allowed_root=self.spec_path.parent)
        task = self.task_spec["task"]
        if task["family"] != "pinch_and_hold":
            raise ValueError(f"Unsupported generated task family: {task['family']}")
        if task["hand_version"] != "v1":
            raise ValueError("The PinchAndHold MVP currently supports ORCA v1 only")
        if reset_randomization_scale < 0:
            raise ValueError("reset_randomization_scale must be non-negative")
        self.reset_randomization_scale = float(reset_randomization_scale)
        self.max_episode_steps = int(task["safety"]["max_episode_steps"])
        self.hold_steps = int(task["success"]["hold_steps"])
        self.action_mode = task["control"]["action_mode"]
        self.action_scale = min(
            float(task["control"]["action_scale"]),
            float(task["safety"]["max_action_delta"]),
        )

        super().__init__(
            "generated.xml",
            version="v1",
            frame_skip=5,
            render_mode=render_mode,
            scene_path=scene_path,
        )

        self._object_joint_id = self.model.joint("pinch_object_freejoint").id
        self._object_qpos_adr = int(self.model.jnt_qposadr[self._object_joint_id])
        self._object_qvel_adr = int(self.model.jnt_dofadr[self._object_joint_id])
        self._object_body_id = self.model.body("pinch_object").id
        self._object_geom_id = self.model.geom("pinch_object_geom").id
        self._actuator_qpos_indices = self._resolve_actuator_qpos_indices()

        self._thumb_body_id = self.model.body("right_thumb_dp").id
        self._index_body_id = self.model.body("right_index_ip").id
        self._thumb_geom_ids = self._collision_geoms_for_body(self._thumb_body_id)
        self._index_geom_ids = self._collision_geoms_for_body(self._index_body_id)

        gesture_path = TASKGEN_ROOT / task["reference_gesture"]["path"]
        gesture = load_gesture_reference(gesture_path, allowed_root=TASKGEN_ROOT)
        open_pose = np.asarray(gesture["samples"][0]["qpos"], dtype=np.float64)
        pinch_pose = np.asarray(gesture["samples"][-1]["qpos"], dtype=np.float64)
        self._reset_hand_qpos = (
            open_pose if task["reset"]["hand_pose"] == "open"
            else open_pose
            + float(task["reset"]["hand_closure_fraction"]) * (pinch_pose - open_pose)
        )
        self.scripted_target_qpos = pinch_pose.copy()

        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(self.model.nu,), dtype=np.float32
        )
        self._ctrl_center = 0.5 * (self.action_high + self.action_low)
        self._ctrl_halfspan = 0.5 * (self.action_high - self.action_low)
        self._prev_target = self._reset_hand_qpos.copy()
        self._prev_distance = 0.0
        self._prev_contacts = 0
        self._hold_counter = 0
        self._max_hold_counter = 0
        self._elapsed_steps = 0
        self._success = False

        observation = self._get_obs()
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=observation.shape, dtype=np.float64
        )

    def _resolve_actuator_qpos_indices(self) -> np.ndarray:
        indices = np.empty(self.model.nu, dtype=np.int32)
        for actuator_id in range(self.model.nu):
            joint_id = int(self.model.actuator_trnid[actuator_id, 0])
            indices[actuator_id] = int(self.model.jnt_qposadr[joint_id])
        return indices

    def _collision_geoms_for_body(self, body_id: int) -> set[int]:
        return {
            geom_id
            for geom_id in range(self.model.ngeom)
            if int(self.model.geom_bodyid[geom_id]) == body_id
            and int(self.model.geom_contype[geom_id]) != 0
        }

    def _object_pos(self) -> np.ndarray:
        return self.data.qpos[self._object_qpos_adr : self._object_qpos_adr + 3].copy()

    def _contact_flags(self) -> tuple[bool, bool]:
        thumb = index = False
        for contact_id in range(self.data.ncon):
            contact = self.data.contact[contact_id]
            first, second = int(contact.geom1), int(contact.geom2)
            if self._object_geom_id not in {first, second}:
                continue
            other = second if first == self._object_geom_id else first
            thumb |= other in self._thumb_geom_ids
            index |= other in self._index_geom_ids
        return bool(thumb), bool(index)

    def _tip_distance(self, geom_ids: set[int]) -> float:
        object_pos = self.data.xpos[self._object_body_id]
        return min(
            float(np.linalg.norm(self.data.geom_xpos[geom_id] - object_pos))
            for geom_id in geom_ids
        )

    def _distance_sum(self) -> float:
        return self._tip_distance(self._thumb_geom_ids) + self._tip_distance(self._index_geom_ids)

    def _in_workspace(self) -> bool:
        workspace = self.task_spec["task"]["success"]["workspace"]
        position = self._object_pos()
        return bool(
            np.all(position >= np.asarray(workspace["min"], dtype=np.float64))
            and np.all(position <= np.asarray(workspace["max"], dtype=np.float64))
        )

    def _dropped(self) -> bool:
        return bool(self._object_pos()[2] < self.task_spec["task"]["failure"]["drop_height"])

    def _advance_hold(self, thumb_contact: bool, index_contact: bool) -> bool:
        """Advance the consecutive dual-contact contract by one simulation step."""

        valid = (
            bool(thumb_contact)
            and bool(index_contact)
            and self._in_workspace()
            and not self._dropped()
        )
        self._hold_counter = self._hold_counter + 1 if valid else 0
        self._max_hold_counter = max(self._max_hold_counter, self._hold_counter)
        self._success = self._hold_counter >= self.hold_steps
        return self._success

    def _compose_ctrl_from_qpos(self) -> np.ndarray:
        return np.clip(
            self.data.qpos[self._actuator_qpos_indices], self.action_low, self.action_high
        ).astype(np.float64)

    def action_for_target(self, target_qpos: np.ndarray) -> np.ndarray:
        """Return one normalized action moving toward a physical 17-joint target."""

        target = np.clip(np.asarray(target_qpos, dtype=np.float64), self.action_low, self.action_high)
        if self.action_mode == "absolute":
            action = (target - self._ctrl_center) / np.maximum(self._ctrl_halfspan, 1e-8)
        else:
            denom = self.action_scale * np.maximum(self._ctrl_halfspan, 1e-8)
            action = (target - self._prev_target) / denom
        return np.clip(action, -1.0, 1.0).astype(np.float32)

    def _target_from_action(self, action: np.ndarray) -> np.ndarray:
        clipped = np.clip(np.asarray(action, dtype=np.float64), -1.0, 1.0)
        if self.action_mode == "absolute":
            target = self._ctrl_center + clipped * self._ctrl_halfspan
        else:
            target = self._prev_target + self.action_scale * clipped * self._ctrl_halfspan
        return np.clip(target, self.action_low, self.action_high)

    def _get_obs(self) -> np.ndarray:
        if not hasattr(self, "_object_qpos_adr"):
            return super()._get_obs()
        hand_qpos = self.data.qpos[self._actuator_qpos_indices].copy()
        hand_qvel = self.data.qvel[:17].copy()
        object_qpos = self.data.qpos[self._object_qpos_adr : self._object_qpos_adr + 7].copy()
        object_qvel = self.data.qvel[self._object_qvel_adr : self._object_qvel_adr + 6].copy()
        object_pos = self.data.xpos[self._object_body_id]
        thumb_delta = self.data.xpos[self._thumb_body_id] - object_pos
        index_delta = self.data.xpos[self._index_body_id] - object_pos
        contacts = np.asarray(self._contact_flags(), dtype=np.float64)
        return np.concatenate(
            [hand_qpos, hand_qvel, object_qpos, object_qvel, thumb_delta, index_delta, contacts]
        )

    def _info(self) -> dict[str, Any]:
        thumb, index = self._contact_flags()
        return {
            "thumb_contact": thumb,
            "index_contact": index,
            "dual_contact": thumb and index,
            "in_workspace": self._in_workspace(),
            "dropped": self._dropped(),
            "hold_counter": self._hold_counter,
            "max_hold_counter": self._max_hold_counter,
            "is_success": self._success,
            "object_pos": self._object_pos(),
            "elapsed_steps": self._elapsed_steps,
        }

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        gym.Env.reset(self, seed=seed)
        mujoco.mj_resetData(self.model, self.data)
        task = self.task_spec["task"]
        options = {} if options is None else dict(options)
        scale = float(options.get("randomization_scale", self.reset_randomization_scale))
        if scale < 0:
            raise ValueError("randomization_scale must be non-negative")

        self.data.qpos[self._actuator_qpos_indices] = self._reset_hand_qpos
        nominal = np.asarray(task["reset"]["object_position"], dtype=np.float64)
        jitter = np.asarray(task["reset"]["position_jitter"], dtype=np.float64) * scale
        object_pos = nominal + self.np_random.uniform(-jitter, jitter)
        self.data.qpos[self._object_qpos_adr : self._object_qpos_adr + 3] = object_pos
        self.data.qpos[self._object_qpos_adr + 3 : self._object_qpos_adr + 7] = [1, 0, 0, 0]
        self.data.qvel[:] = 0.0
        self.data.ctrl[:] = np.clip(self._reset_hand_qpos, self.action_low, self.action_high)
        mujoco.mj_forward(self.model, self.data)

        self._prev_target = self._compose_ctrl_from_qpos()
        self._prev_distance = self._distance_sum()
        self._prev_contacts = sum(self._contact_flags())
        self._hold_counter = 0
        self._max_hold_counter = 0
        self._elapsed_steps = 0
        self._success = False
        return self._get_obs(), self._info()

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action = np.asarray(action, dtype=np.float32)
        if action.shape != self.action_space.shape:
            raise ValueError(f"Expected action shape {self.action_space.shape}, got {action.shape}")
        target = self._target_from_action(action)
        rate = (target - self._prev_target) / np.maximum(self._ctrl_halfspan, 1e-8)
        self._prev_target = target
        self.data.ctrl[:] = target
        mujoco.mj_step(self.model, self.data, nstep=self.frame_skip)
        self._elapsed_steps += 1

        task = self.task_spec["task"]
        reward_spec = task["reward"]
        distance = self._distance_sum()
        thumb, index = self._contact_flags()
        contacts = int(thumb) + int(index)
        self._advance_hold(thumb, index)

        reward = reward_spec["distance_progress"] * (self._prev_distance - distance)
        reward += reward_spec["contact_progress"] * (contacts - self._prev_contacts)
        reward -= reward_spec["action_rate_penalty"] * float(np.sum(rate**2))
        if self._success:
            reward += reward_spec["success_bonus"]
        dropped = self._dropped()
        if dropped:
            reward -= reward_spec["drop_penalty"]
        self._prev_distance = distance
        self._prev_contacts = contacts

        terminated = bool(self._success or (dropped and task["failure"]["terminate_on_drop"]))
        truncated = bool(self._elapsed_steps >= self.max_episode_steps)
        info = self._info()
        if self.render_mode == "human":
            self.render()
        return self._get_obs(), float(reward), terminated, truncated, info
