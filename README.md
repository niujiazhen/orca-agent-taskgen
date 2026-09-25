# ORCA Text-to-MuJoCo Environment Agent

This Codex plugin turns a Chinese or English task description into a validated,
visualizable MuJoCo/Gymnasium reinforcement-learning environment for one ORCA
v1 right hand.

It supports hand gestures, picking up a box/cylinder/sphere, and placing one of
those objects in a target region. It does not support stacking, insertion,
tools, screws, external meshes, robot arms, or two-hand tasks.

## 1. Install the Codex plugin

Requirements: Codex, Git, and Python 3.10 or newer.

```powershell
codex plugin marketplace add niujiazhen/orca-agent-taskgen
codex plugin add orca-env-generator@orca-agent-taskgen
```

Restart Codex and start a new task after installation. The plugin follows the
standard [Codex marketplace workflow](https://developers.openai.com/plugins/build/plugins).
No separate OpenAI API key is required by the Python package.

## 2. Describe the environment

Enter one sentence describing the hand action, object, and target when needed.
You do not need to write YAML, MJCF, or reward code.

```text
Use $orca-env-generator:
让灵巧手拿起桌上的红色方块。生成环境，完成检查并创建 preview。
```

Other examples:

```text
把蓝色圆柱拿起来，放到桌面右侧的绿色目标区域。
Make the ORCA hand close into a fist and open again.
Pick up the green sphere from the table.
```

Codex fills safe defaults for omitted size, mass, friction, reward, reset
randomization, and success thresholds. It asks a question only when an
ambiguity changes the task itself.

## 3. Agent output

The Agent converts the request into a TaskSpec, generates the MuJoCo scene and
Gymnasium environment, runs validation, and creates a preview. The final reply
reports the task directory, environment ID, validation result, and preview
paths.

Each generated task bundle contains:

```text
generated_tasks/<task>/
├── request.txt
├── task_spec.yaml
├── scene.xml
├── manifest.json
├── validation_report.json
├── preview.png
├── preview.mp4
└── README.md
```

## 4. What the preview video means

`preview.mp4` is a non-learning physical-feasibility check. A deterministic
controller operates through the same public 23-dimensional action space that
an RL policy would use. For manipulation tasks, the object remains a free
MuJoCo body and is moved through simulated fingertip contacts.

The preview is **not** PPO training, a trained policy, or evidence that RL has
already converged. It only shows that the generated scene, actions, contacts,
and success condition can complete the task without learning.

[Gesture preview](examples/generated/handfist_v0/preview.mp4) ·
[Pickup preview](examples/generated/redcubepickup_v0/preview.mp4) ·
[Pick-and-place preview](examples/generated/bluecylinderplace_v0/preview.mp4)

## 5. Use the generated RL environment

Load a bundle directly:

```python
from orca_sim.taskgen import load_environment

env = load_environment(
    "generated_tasks/redcubepickup_v0",
    render_mode="human",  # or "rgb_array"
)

observation, info = env.reset(seed=0)

for _ in range(1000):
    action = env.action_space.sample()  # replace with your RL policy
    observation, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        observation, info = env.reset()

env.close()
```

The action contains wrist translation `[3]`, wrist rotation `[3]`, and ORCA
joint targets `[17]`. The observation contains wrist and joint state,
fingertips, contacts, object state, target, and task stage.

To inspect the environment interactively:

```powershell
orca-task view generated_tasks/redcubepickup_v0
```
