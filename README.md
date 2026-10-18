# ORCA Text-to-MuJoCo Environment Agent

This Codex plugin turns text or a tabletop photo into a visualizable MuJoCo
scene and a Gymnasium RL environment for one ORCA v1 right hand.

Text input supports gestures, pickup, and placement of boxes, cylinders, and
spheres. Photo input also supports pens, erasers, and books: up to five objects,
one training target. Models approximate the photo's colors, orientation, and
layout. Stacking, insertion, tool use, external meshes, and two-hand tasks are
outside this release.

## 1. Install the Codex plugin

Requirements: Codex, Git, and Python 3.10 or newer.

```powershell
codex plugin marketplace add niujiazhen/orca-agent-taskgen
codex plugin add orca-env-generator@orca-agent-taskgen
```

Restart Codex and start a new task after installation. The plugin follows the
standard [Codex marketplace workflow](https://developers.openai.com/plugins/build/plugins).
No separate OpenAI API key is required by the Python package.
The package pins the validated MuJoCo version for reproducible contact behavior.
Codex installs the Python runtime when first needed. To install it yourself:

```powershell
python -m pip install "orca_sim[photo,visualization] @ git+https://github.com/niujiazhen/orca-agent-taskgen.git@main"
```

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

For a photo, attach it to Codex or provide its local path:

```text
Use $orca-env-generator. 根据这张照片生成桌面场景，先让我确认。
```

For phone capture:

```text
Use $orca-env-generator. 我要用手机拍照生成环境，请打开扫码上传。
```

Codex starts a local upload page and shows a QR code. Keep the phone and
computer on the same Wi-Fi, then take a photo or select one from the album.
Supported formats: JPEG, PNG, WebP, HEIC/HEIF (20 MB / 40 MP maximum).
If Codex has stopped waiting, say “继续处理刚上传的照片”.

Codex shows the photo, numbered object annotations, estimated dimensions, and
the generated scene. Confirm or correct it, then specify the training task:

```text
场景正确。让灵巧手拿起 pen_1，并保持 20 步。
```

Single photos do not determine exact dimensions, mass, or friction. Defaults
are labelled; a known measurement such as “笔长 14cm” can calibrate the scene.

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

Photo scenes first appear in `generated_scenes/<scene>/`: source.png,
annotated.png, scene_spec.yaml, scene.xml, manifest.json, scene_report.json,
scene_preview.png, and scene_preview.mp4. They contain no hand or reward.
After confirmation, the RL task adds TaskSpec v3, a portable hand model and its
assets, source-scene metadata,
validation_report.json, task_preview.png, and task_preview.mp4.

Reports separate scene stability, RL-interface validation, and scripted
feasibility. A failed script is reported separately; it does not imply the
environment cannot be trained. Scene or interface failures mean it is not ready.

## 4. What the preview video means

`preview.mp4` is a non-learning physical-feasibility check. A deterministic
controller operates through the same public 23-dimensional action space that
an RL policy would use. For manipulation tasks, the object remains a free
MuJoCo body and is moved through simulated fingertip contacts.

The preview is **not** PPO training, a trained policy, or evidence that RL has
already converged. It only shows that the generated scene, actions, contacts,
and success condition can complete the task without learning.

Photo mode distinguishes `scene_preview.mp4` (camera orbit, no task) from
`task_preview.mp4` (scripted attempt, labelled success or failure). Failed
attempts are preserved; successful manipulation is not guaranteed for new
photo objects, especially books wider than the hand.

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

Use the actual task directory returned by Codex. Photo tasks use the same
`load_environment()` interface, with 135 observations covering five masked
object slots; existing text/v2 tasks retain 73 observations. To inspect only
the photo scene, use `load_scene("generated_scenes/desk_pen")` and `scene.close()`.

The action contains wrist translation `[3]`, wrist rotation `[3]`, and ORCA
joint targets `[17]`. The observation contains wrist and joint state,
fingertips, contacts, object state, target, and task stage.

To inspect the environment interactively:

```powershell
orca-task view generated_tasks/redcubepickup_v0
```

Photo CLI (Codex performs image interpretation between draft and generation):

```powershell
orca-task capture --lan
orca-task scene generate scene_drafts/desk_pen/scene_spec.yaml --output generated_scenes
orca-task scene check generated_scenes/desk_pen
orca-task scene preview generated_scenes/desk_pen
orca-task scene view generated_scenes/desk_pen
# After the user reviews and confirms the displayed spec hash:
orca-task scene confirm generated_scenes/desk_pen --spec-sha256 <reviewed-hash>
orca-task task create generated_scenes/desk_pen --family pick_up --object pen_1 --output generated_tasks
```

The CLI generates scenes from structured specifications; it does not recognize
photos independently. See [photo acceptance and limitations](docs/PHOTO_ACCEPTANCE.md)
for automated evidence and remaining device checks.
