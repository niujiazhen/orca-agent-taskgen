# BlueCylinderPlace-v0

Generated from: 把蓝色圆柱拿起来并放到桌面右侧的绿色区域

- Family: `pick_place`
- Hand: ORCA v1 right hand with a bounded kinematic 6DoF wrist
- Validation: see `validation_report.json`

```python
from orca_sim.taskgen import load_environment

env = load_environment(r".", render_mode="human")
observation, info = env.reset(seed=0)
```

This bundle contains an untrained RL environment. Any preview is produced by a
non-learning scripted feasibility controller, not PPO or a trained policy.
