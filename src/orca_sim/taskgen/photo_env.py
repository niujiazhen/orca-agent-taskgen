"""Multi-object TaskSpec v3 environment; v2 observations remain unchanged."""
from __future__ import annotations

import mujoco
import numpy as np
from gymnasium import spaces

from orca_sim.taskgen.catalog import OPEN
from orca_sim.taskgen.contracts import ContractError
from orca_sim.taskgen.generic_env import GeneratedOrcaEnv
from orca_sim.taskgen.photo_contracts import object_position
from orca_sim.taskgen.photo_scene import body_name


class PhotoTaskEnv(GeneratedOrcaEnv):
    OBSERVATION_SIZE = 135

    def __init__(self, **kwargs):
        self._records = []
        self._lifted_once = False
        self._physics_fail_steps = 0
        self._physics_invalid = False
        super().__init__(**kwargs)
        self.photo_scene = self.task_spec["scene_spec"]
        self.target_id = self.task_spec["task"]["object_id"]
        self._target_geom_ids = self._collision_geoms_for_body(self._object_body_id)
        for obj in self.photo_scene["objects"]:
            joint = self.model.joint(f"{body_name(obj, self.target_id)}_freejoint").id
            self._records.append((obj, int(self.model.jnt_qposadr[joint]), int(self.model.jnt_dofadr[joint])))
        # The mounting tower is not the hand and must not become an invisible
        # obstacle when the virtual wrist moves around the tabletop.
        tower = np.flatnonzero(self.model.geom_bodyid == self._tower_body_id)
        self.model.geom_contype[tower] = 0
        self.model.geom_conaffinity[tower] = 0
        self._hand_geoms = set()
        for geom in range(self.model.ngeom):
            body = int(self.model.geom_bodyid[geom])
            while body > 0 and body != self._tower_body_id:
                body = int(self.model.body_parentid[body])
            if body == self._tower_body_id and int(self.model.geom_contype[geom]):
                self._hand_geoms.add(geom)
        self._table_geom = self.model.geom("photo_table").id
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=(self.OBSERVATION_SIZE,), dtype=np.float64)

    def _contact_flags(self):
        if not hasattr(self, "_target_geom_ids"):
            return super()._contact_flags()
        result = [False]*3
        for contact in self.data.contact:
            a, b = int(contact.geom1), int(contact.geom2)
            if a not in self._target_geom_ids and b not in self._target_geom_ids:
                continue
            other = b if a in self._target_geom_ids else a
            for i, geoms in enumerate(self._tip_geom_ids):
                result[i] |= other in geoms
        return tuple(result)

    def _get_obs(self):
        base = super()._get_obs()
        if not self._records:
            return base
        slots = np.zeros((5, 15), dtype=np.float64)
        for index, (obj, q, v) in enumerate(self._records):
            slots[index] = np.concatenate([self.data.qpos[q:q+7], self.data.qvel[v:v+6], [1., float(obj["id"] == self.target_id)]])
        # v2: wrist7, joints34, tip offsets9, contacts3, object13, target3,
        # stage3, progress1. Replace the single object with five masked slots.
        result = np.concatenate([base[:53], slots.ravel(), base[66:]])
        result[-4:-1] = [float(not self._grasped and not self._lifted_once),
                          float(self._grasped), float(self._lifted_once and not self._grasped)]
        return result

    def _advance_success(self):
        if not self._records:
            return super()._advance_success()
        config = self.task["success"]
        lifted = self._object_pos()[2]-self._initial_object_position[2] >= config["lift_height"]
        self._lifted_once |= bool(lifted and self._grasped)
        speed = float(np.linalg.norm(self._object_velocity()[:3]))
        if self.family == "pick_up":
            valid = lifted and self._grasped and speed <= config["max_object_speed"]
        else:
            # No dependency on the demonstration's private stage counter.
            any_contact = any(self._contact_flags())
            valid = (self._lifted_once and not any_contact and
                np.linalg.norm(self._object_pos()-self._target_position) <= config["target_radius"] and
                speed <= config["max_object_speed"])
        self._hold_counter = self._hold_counter+1 if valid else 0
        self._success = self._hold_counter >= self.hold_steps

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed, options=options)
        for obj, q, _ in self._records:
            self.data.qpos[q:q+3] = object_position(self.photo_scene, obj)
            self.data.qpos[q+3:q+7] = obj["quaternion"]
        self.data.qvel[:] = 0
        self._initial_object_position = self._object_pos()
        self._lifted_once = False
        self._physics_fail_steps = 0
        self._physics_invalid = False
        mujoco.mj_forward(self.model, self.data)
        if self._table_penetration(self.data) > .002:
            raise ContractError("Initial hand penetrates table")
        # Every visible hand mesh must start above the tabletop as well.
        for geom in self._hand_geoms:
            local = self.model.geom_aabb[geom]
            rot = self.data.geom_xmat[geom].reshape(3, 3)
            low = (self.data.geom_xpos[geom]+rot@local[:3])[2]-(np.abs(rot)@local[3:])[2]
            if low < self.photo_scene["table"]["top_z"]:
                raise ContractError("Initial hand geometry must be above tabletop")
        self._previous_metric = self._metric()
        return self._get_obs(), self._info()

    def _table_penetration(self, data):
        return max((max(0., -float(c.dist)) for c in data.contact
                    if self._table_geom in {int(c.geom1), int(c.geom2)} and
                    bool({int(c.geom1), int(c.geom2)} & self._hand_geoms)), default=0.)

    def step(self, action):
        action = np.asarray(action, dtype=np.float32)
        if action.shape != (23,) or not np.isfinite(action).all():
            raise ValueError("Expected a finite 23-dimensional action")
        # Reject a wrist move that would kinematically put the hand through the
        # table. Finger motion remains governed by collision response.
        from orca_sim.taskgen.generic_env import _quat_multiply
        action = np.clip(action, -1., 1.).copy()
        position, quaternion = self._wrist_position.copy(), self._wrist_quaternion.copy()
        self._wrist_position = np.clip(position+action[:3]*self.task["control"]["translation_step"], self._workspace_min, self._workspace_max)
        rot = action[3:6].astype(float)*self.task["control"]["rotation_step"]
        angle = np.linalg.norm(rot)
        if angle > 1e-12:
            self._wrist_quaternion = _quat_multiply(np.r_[np.cos(angle/2), rot/angle*np.sin(angle/2)], quaternion)
        self._set_wrist_model_pose()
        self._kinematic_data.qpos[:] = self.data.qpos
        mujoco.mj_forward(self.model, self._kinematic_data)
        if self._table_penetration(self._kinematic_data) > .001:
            action[:6] = 0
        self._wrist_position, self._wrist_quaternion = position, quaternion
        self._set_wrist_model_pose()
        observation, reward, terminated, truncated, _ = super().step(action)
        depth = self._table_penetration(self.data)
        self._physics_fail_steps = self._physics_fail_steps+1 if depth > .002 else 0
        self._physics_invalid = self._physics_fail_steps >= 10
        dropped = self._object_pos()[2] < self.photo_scene["table"]["top_z"]-.03
        if self._physics_invalid or dropped:
            self._success = False
            terminated = True
            reward -= 10.
        return observation, reward, terminated, truncated, self._info()

    def _info(self):
        info = super()._info()
        if self._records:
            info.update(target_object_id=self.target_id, lifted_once=self._lifted_once,
                        physics_invalid=self._physics_invalid, hand_table_penetration_m=self._table_penetration(self.data))
        return info
