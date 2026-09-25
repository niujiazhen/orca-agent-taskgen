"""TaskSpec v2-driven ORCA hand environment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

from orca_sim.envs import BaseOrcaHandEnv
from orca_sim.taskgen.catalog import GESTURE_SEQUENCES, GRASP_POSES, OPEN
from orca_sim.taskgen.contracts import load_task_spec


def _quat_multiply(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = first
    w2, x2, y2, z2 = second
    result = np.asarray(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dtype=np.float64,
    )
    return result / np.linalg.norm(result)


class GeneratedOrcaEnv(BaseOrcaHandEnv):
    """Generic v2 environment for gestures, pickup, and pick/place.

    The 6DoF wrist is kinematic and intentionally bounded. Optional assistive
    grasping is part of the environment dynamics and is reported in the
    manifest/info; scripted controllers never write simulator state directly.
    """

    ACTION_SIZE = 23
    TIP_NAMES = ("right_thumb_dp", "right_index_ip", "right_middle_ip")

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
        if self.task_spec["schema_version"] != 2:
            raise ValueError("GeneratedOrcaEnv requires TaskSpec v2")
        self.task = self.task_spec["task"]
        self.family = self.task["family"]
        self.max_episode_steps = int(self.task["safety"]["max_episode_steps"])
        self.hold_steps = int(self.task["success"]["hold_steps"])
        self.reset_randomization_scale = float(reset_randomization_scale)
        if self.reset_randomization_scale < 0:
            raise ValueError("reset_randomization_scale must be non-negative")

        super().__init__(
            "generated.xml",
            version="v1",
            frame_skip=int(self.task["control"]["frame_skip"]),
            render_mode=render_mode,
            scene_path=scene_path,
        )

        self._hand_action_low = self.action_low.copy()
        self._hand_action_high = self.action_high.copy()
        if self.model.nu != 17:
            raise ValueError(f"ORCA v1 right hand must expose 17 actuators, got {self.model.nu}")
        self._ctrl_center = 0.5 * (self._hand_action_low + self._hand_action_high)
        self._ctrl_halfspan = 0.5 * (self._hand_action_high - self._hand_action_low)
        # The source model is tuned for gentle teleoperation. Generated target-
        # tracking tasks need enough authority to hold poses against gravity.
        self.model.actuator_gainprm[:, 0] = 20.0
        self.model.actuator_biasprm[:, 1] = -20.0
        self.model.actuator_forcerange[:, 0] = -5.0
        self.model.actuator_forcerange[:, 1] = 5.0
        self._actuator_qpos_indices, self._actuator_qvel_indices = self._resolve_actuator_indices()
        self.action_space = spaces.Box(-1.0, 1.0, shape=(self.ACTION_SIZE,), dtype=np.float32)

        self._tower_body_id = self.model.body("right_tower").id
        self._tip_body_ids = tuple(self.model.body(name).id for name in self.TIP_NAMES)
        self._tip_geom_ids = tuple(self._collision_geoms_for_body(body_id) for body_id in self._tip_body_ids)
        self._wrist_position = np.asarray(self.task["hand"]["initial_position"], dtype=np.float64)
        self._wrist_quaternion = np.asarray(self.task["hand"]["initial_quaternion"], dtype=np.float64)
        self._workspace_min = np.asarray(self.task["hand"]["workspace"]["min"], dtype=np.float64)
        self._workspace_max = np.asarray(self.task["hand"]["workspace"]["max"], dtype=np.float64)

        self._object_body_id: int | None = None
        self._object_geom_id: int | None = None
        self._object_qpos_adr: int | None = None
        self._object_qvel_adr: int | None = None
        if "object" in self.task["scene"]:
            object_joint = self.model.joint("task_object_freejoint")
            self._object_body_id = self.model.body("task_object").id
            self._object_geom_id = self.model.geom("task_object_geom").id
            self._object_qpos_adr = int(self.model.jnt_qposadr[object_joint.id])
            self._object_qvel_adr = int(self.model.jnt_dofadr[object_joint.id])
        self._target_position = np.asarray(
            self.task["scene"].get("target", {}).get("position", [0.0, 0.0, 0.0]),
            dtype=np.float64,
        )
        self._gesture_sequence = (
            GESTURE_SEQUENCES[self.task["gesture"]["name"]]
            if self.family == "gesture"
            else ()
        )
        self._grasp_pose = (
            GRASP_POSES[self.task["scene"]["object"]["shape"]]
            if self._object_body_id is not None
            else OPEN
        )

        self._elapsed_steps = 0
        self._hold_counter = 0
        self._success = False
        self._grasped = False
        self._grasp_offset = np.zeros(3, dtype=np.float64)
        self._gesture_index = 0
        self._script_stage = 0
        self._initial_object_position = np.zeros(3, dtype=np.float64)
        self._previous_metric = 0.0

        observation = self._get_obs()
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=observation.shape, dtype=np.float64
        )

    def _resolve_actuator_indices(self) -> tuple[np.ndarray, np.ndarray]:
        qpos = np.empty(self.model.nu, dtype=np.int32)
        qvel = np.empty(self.model.nu, dtype=np.int32)
        for actuator_id in range(self.model.nu):
            joint_id = int(self.model.actuator_trnid[actuator_id, 0])
            qpos[actuator_id] = int(self.model.jnt_qposadr[joint_id])
            qvel[actuator_id] = int(self.model.jnt_dofadr[joint_id])
        return qpos, qvel

    def _collision_geoms_for_body(self, body_id: int) -> set[int]:
        return {
            geom_id
            for geom_id in range(self.model.ngeom)
            if int(self.model.geom_bodyid[geom_id]) == body_id
            and int(self.model.geom_contype[geom_id]) != 0
        }

    def _set_wrist_model_pose(self) -> None:
        self.model.body_pos[self._tower_body_id] = self._wrist_position
        self.model.body_quat[self._tower_body_id] = self._wrist_quaternion

    def _hand_qpos(self) -> np.ndarray:
        return self.data.qpos[self._actuator_qpos_indices].copy()

    def _normalized_hand_error(self, target: np.ndarray) -> float:
        error = (self._hand_qpos() - target) / np.maximum(self._ctrl_halfspan, 1e-8)
        return float(np.sqrt(np.mean(error**2)))

    def _hand_action(self, target: np.ndarray) -> np.ndarray:
        clipped = np.clip(target, self._hand_action_low, self._hand_action_high)
        return np.clip((clipped - self._ctrl_center) / self._ctrl_halfspan, -1.0, 1.0)

    def _object_pos(self) -> np.ndarray:
        if self._object_qpos_adr is None:
            return np.zeros(3, dtype=np.float64)
        return self.data.qpos[self._object_qpos_adr : self._object_qpos_adr + 3].copy()

    def _object_velocity(self) -> np.ndarray:
        if self._object_qvel_adr is None:
            return np.zeros(6, dtype=np.float64)
        return self.data.qvel[self._object_qvel_adr : self._object_qvel_adr + 6].copy()

    def _grip_center(self) -> np.ndarray:
        return np.mean([self.data.xpos[body_id] for body_id in self._tip_body_ids], axis=0)

    def _contact_flags(self) -> tuple[bool, bool, bool]:
        if self._object_geom_id is None:
            return False, False, False
        result = [False, False, False]
        for contact_id in range(self.data.ncon):
            contact = self.data.contact[contact_id]
            first, second = int(contact.geom1), int(contact.geom2)
            if self._object_geom_id not in {first, second}:
                continue
            other = second if first == self._object_geom_id else first
            for index, geom_ids in enumerate(self._tip_geom_ids):
                result[index] |= other in geom_ids
        return tuple(bool(value) for value in result)

    def _update_assistive_grasp(self) -> None:
        if self._object_qpos_adr is None or not self.task["safety"]["assistive_grasp"]:
            return
        open_error = self._normalized_hand_error(OPEN)
        grasp_error = self._normalized_hand_error(self._grasp_pose)
        distance = float(np.linalg.norm(self._object_pos() - self._grip_center()))
        if self._grasped and open_error < 0.22:
            self._grasped = False
            self.data.qvel[self._object_qvel_adr : self._object_qvel_adr + 6] = 0.0
            mujoco.mj_forward(self.model, self.data)
        elif not self._grasped and grasp_error < 0.30 and distance < 0.06:
            self._grasped = True
            self._grasp_offset = self._object_pos() - self._grip_center()

        if self._grasped:
            old_position = self._object_pos()
            new_position = self._grip_center() + self._grasp_offset
            self.data.qpos[self._object_qpos_adr : self._object_qpos_adr + 3] = new_position
            self.data.qvel[self._object_qvel_adr : self._object_qvel_adr + 3] = (
                new_position - old_position
            ) / max(float(self.model.opt.timestep) * self.frame_skip, 1e-8)
            self.data.qvel[self._object_qvel_adr + 3 : self._object_qvel_adr + 6] = 0.0
            mujoco.mj_forward(self.model, self.data)

    def _gesture_target(self) -> np.ndarray:
        return self._gesture_sequence[min(self._gesture_index, len(self._gesture_sequence) - 1)]

    def _metric(self) -> float:
        if self.family == "gesture":
            return -self._normalized_hand_error(self._gesture_target())
        if self.family == "pick_up":
            return float(self._object_pos()[2] - self._initial_object_position[2])
        return -float(np.linalg.norm(self._object_pos() - self._target_position))

    def _advance_success(self) -> None:
        success = self.task["success"]
        valid = False
        if self.family == "gesture":
            tolerance = float(success["gesture_tolerance"])
            if self._normalized_hand_error(self._gesture_target()) <= tolerance:
                if self._gesture_index < len(self._gesture_sequence) - 1:
                    self._gesture_index += 1
                    self._hold_counter = 0
                else:
                    valid = True
        elif self.family == "pick_up":
            height = self._object_pos()[2] - self._initial_object_position[2]
            valid = bool(height >= float(success["lift_height"]) and self._grasped)
        else:
            distance = float(np.linalg.norm(self._object_pos() - self._target_position))
            speed = float(np.linalg.norm(self._object_velocity()[:3]))
            valid = bool(
                distance <= float(success["target_radius"])
                and speed <= float(success["max_object_speed"])
                and not self._grasped
                and self._script_stage >= 3
            )
        self._hold_counter = self._hold_counter + 1 if valid else 0
        self._success = self._hold_counter >= self.hold_steps

    def _get_obs(self) -> np.ndarray:
        if not hasattr(self, "_actuator_qpos_indices"):
            return super()._get_obs()
        hand_qpos = self._hand_qpos()
        hand_qvel = self.data.qvel[self._actuator_qvel_indices].copy()
        tip_reference = self._object_pos() if self._object_body_id is not None else self._wrist_position
        tip_deltas = np.concatenate(
            [self.data.xpos[body_id] - tip_reference for body_id in self._tip_body_ids]
        )
        contacts = np.asarray(self._contact_flags(), dtype=np.float64)
        if self._object_qpos_adr is None:
            object_state = np.zeros(13, dtype=np.float64)
        else:
            object_state = np.concatenate(
                [
                    self.data.qpos[self._object_qpos_adr : self._object_qpos_adr + 7],
                    self.data.qvel[self._object_qvel_adr : self._object_qvel_adr + 6],
                ]
            )
        stage = np.zeros(3, dtype=np.float64)
        stage[min(self._script_stage, 2)] = 1.0
        progress = np.asarray([self._elapsed_steps / max(self.max_episode_steps, 1)], dtype=np.float64)
        return np.concatenate(
            [
                self._wrist_position,
                self._wrist_quaternion,
                hand_qpos,
                hand_qvel,
                tip_deltas,
                contacts,
                object_state,
                self._target_position,
                stage,
                progress,
            ]
        )

    def _info(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "is_success": self._success,
            "hold_counter": self._hold_counter,
            "elapsed_steps": self._elapsed_steps,
            "gesture_index": self._gesture_index,
            "script_stage": self._script_stage,
            "grasped": self._grasped,
            "assistive_grasp": bool(self.task["safety"]["assistive_grasp"]),
            "object_position": self._object_pos(),
            "wrist_position": self._wrist_position.copy(),
        }

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        gym.Env.reset(self, seed=seed)
        mujoco.mj_resetData(self.model, self.data)
        options = {} if options is None else dict(options)
        scale = float(options.get("randomization_scale", self.reset_randomization_scale))
        if scale < 0:
            raise ValueError("randomization_scale must be non-negative")

        wrist_jitter = np.asarray(self.task["reset"]["wrist_position_jitter"], dtype=np.float64)
        self._wrist_position = np.asarray(self.task["hand"]["initial_position"], dtype=np.float64)
        self._wrist_position += self.np_random.uniform(-wrist_jitter, wrist_jitter) * scale
        self._wrist_position = np.clip(self._wrist_position, self._workspace_min, self._workspace_max)
        self._wrist_quaternion = np.asarray(self.task["hand"]["initial_quaternion"], dtype=np.float64)
        self._set_wrist_model_pose()
        self.data.qpos[self._actuator_qpos_indices] = np.clip(
            OPEN, self._hand_action_low, self._hand_action_high
        )
        self.data.ctrl[:] = np.clip(OPEN, self._hand_action_low, self._hand_action_high)

        if self._object_qpos_adr is not None:
            obj = self.task["scene"]["object"]
            nominal = np.asarray(obj["initial_position"], dtype=np.float64)
            jitter = np.asarray(self.task["reset"]["object_position_jitter"], dtype=np.float64)
            position = nominal + self.np_random.uniform(-jitter, jitter) * scale
            self.data.qpos[self._object_qpos_adr : self._object_qpos_adr + 3] = position
            self.data.qpos[self._object_qpos_adr + 3 : self._object_qpos_adr + 7] = [1, 0, 0, 0]
            self._initial_object_position = position.copy()
        self.data.qvel[:] = 0.0
        mujoco.mj_forward(self.model, self.data)

        self._elapsed_steps = 0
        self._hold_counter = 0
        self._success = False
        self._grasped = False
        self._grasp_offset[:] = 0.0
        self._gesture_index = 0
        self._script_stage = 0
        self._previous_metric = self._metric()
        return self._get_obs(), self._info()

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action = np.asarray(action, dtype=np.float32)
        if action.shape != self.action_space.shape:
            raise ValueError(f"Expected action shape {self.action_space.shape}, got {action.shape}")
        action = np.clip(action, -1.0, 1.0)

        self._wrist_position += action[:3] * float(self.task["control"]["translation_step"])
        self._wrist_position = np.clip(self._wrist_position, self._workspace_min, self._workspace_max)
        rotation = action[3:6].astype(np.float64) * float(self.task["control"]["rotation_step"])
        angle = float(np.linalg.norm(rotation))
        if angle > 1e-12:
            axis = rotation / angle
            delta_quat = np.concatenate(([np.cos(angle / 2)], axis * np.sin(angle / 2)))
            self._wrist_quaternion = _quat_multiply(delta_quat, self._wrist_quaternion)
        self._set_wrist_model_pose()

        hand_target = self._ctrl_center + action[6:] * self._ctrl_halfspan
        self.data.ctrl[:] = np.clip(hand_target, self._hand_action_low, self._hand_action_high)
        mujoco.mj_step(self.model, self.data, nstep=self.frame_skip)
        self._elapsed_steps += 1
        self._update_assistive_grasp()
        self._advance_success()

        metric = self._metric()
        reward_spec = self.task["reward"]
        reward = float(reward_spec["progress"]) * (metric - self._previous_metric)
        reward += float(reward_spec["grasp"]) * float(self._grasped)
        reward -= float(reward_spec["action_penalty"]) * float(np.sum(action**2))
        if self._success:
            reward += float(reward_spec["success"])
        self._previous_metric = metric
        terminated = bool(self._success)
        truncated = bool(self._elapsed_steps >= self.max_episode_steps)
        if self.render_mode == "human":
            self.render()
        return self._get_obs(), reward, terminated, truncated, self._info()

    def scripted_action(self) -> np.ndarray:
        """Return a deterministic feasibility action through the public action space."""

        action = np.zeros(self.ACTION_SIZE, dtype=np.float32)
        if self.family == "gesture":
            action[6:] = self._hand_action(self._gesture_target())
            self._script_stage = min(self._gesture_index, 2)
            return action

        grip_delta = self._object_pos() - self._grip_center()
        if not self._grasped and self._script_stage < 2:
            if float(np.linalg.norm(grip_delta)) > 0.012:
                action[:3] = np.clip(
                    grip_delta / float(self.task["control"]["translation_step"]), -1.0, 1.0
                )
                action[6:] = self._hand_action(OPEN)
                self._script_stage = 0
            else:
                action[6:] = self._hand_action(self._grasp_pose)
                self._script_stage = 1
            return action

        if self._grasped:
            self._script_stage = 2
            if self.family == "pick_up":
                desired = self._initial_object_position.copy()
                desired[2] += float(self.task["success"]["lift_height"]) + 0.025
            else:
                desired = self._target_position.copy()
            delta = desired - self._object_pos()
            if self.family == "pick_place" and float(np.linalg.norm(delta)) < 0.012:
                self._script_stage = 3
                action[6:] = self._hand_action(OPEN)
            else:
                action[:3] = np.clip(
                    delta / float(self.task["control"]["translation_step"]), -1.0, 1.0
                )
                action[6:] = self._hand_action(self._grasp_pose)
            return action

        self._script_stage = max(self._script_stage, 3)
        action[6:] = self._hand_action(OPEN)
        return action
