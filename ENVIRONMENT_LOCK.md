# Reproducible Environment Lock

Updated: 2026-09-24 (America/Los_Angeles)

## Source

- Repository: `https://github.com/LynnUoE/orca_sim.git`
- Baseline commit: `02571cf7fbec1e57de615e61949d504440e2646a`
- Working branch: `codex/agent-task-generation`
- MVP embodiment: ORCA v1 right hand

## Runtime

- OS: Windows 10 build 26200, 64-bit
- Python: 3.11.9
- gymnasium: 1.3.0
- mujoco: 3.13.0
- numpy: 2.4.6
- PyYAML: 6.0.3
- jsonschema: 4.26.0
- imageio: visualization extra only

## Bootstrap

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[visualization,dev]" build
```

The text-to-environment Agent does not require PPO, PyTorch, Stable-Baselines3,
or TensorBoard. The editable install is for development only; release checks
also install the wheel in a separate clean virtual environment.

## External reference provenance

- Repository: `https://github.com/back2-thebasic/orcahand-retarget-experiments`
- Reference commit: `032b5fd424cb67d9e6203388d9de0edc7453eff6`
- Configuration: `configs/last.yaml`
- Embodiment: ORCA v1 right hand
- Use in this goal: pose/retargeting design reference only

The reference repository currently provides YAML configurations and videos,
not verified object-contact trajectories. Any locally generated controller or
trajectory is labeled synthetic until real `timestamp`, `qpos[17]`, and
`ctrl[17]` data is supplied and validated.
