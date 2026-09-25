# RedCubePickup-v0

Generated from: 让灵巧手拿起桌上的红色方块

- Family: `pick_up`
- Hand: ORCA v1 right hand with a bounded kinematic 6DoF wrist
- Validation: see `validation_report.json`

```python
from orca_sim.taskgen import load_environment

env = load_environment(r".", render_mode="human")
observation, info = env.reset(seed=0)
```

This bundle contains an untrained RL environment. Any preview is produced by a
non-learning contact-feasibility controller through the public action space,
not PPO or a trained policy. The object remains a free MuJoCo body.
