# Phone photo to MuJoCo: user tutorial

For the v0.4 editable Blender modeling and manual review stage, follow the
[Blender workflow tutorial](BLENDER_WORKFLOW.md). This page describes shared
phone capture and the original primitive/RL path, which remains available.

Turn a phone photograph into a tabletop simulation with up to five rigid
objects. The workflow produces a source image, object annotations, a structured
scene specification, a MuJoCo model, a physics report, and a rotating preview.
After reviewing the scene, you can request a separate ORCA hand task.

See the complete [five-object real-photo demo](../examples/photo_generated/scenes/phone_five_objects/README.md).

## 1. Install

You need Codex, Git, Python 3.10 or newer, and a phone and computer on the same
local network. From a terminal, install the plugin:

```powershell
codex plugin marketplace add niujiazhen/orca-agent-taskgen
codex plugin add orca-env-generator@orca-agent-taskgen
```

Restart Codex and open a new chat. The plugin can install its Python dependencies
when needed. For an explicit installation from a checkout on Windows:

```powershell
git clone https://github.com/niujiazhen/orca-agent-taskgen.git
cd orca-agent-taskgen
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[photo,visualization]"
```

For the CLI commands below, activate that environment:

```powershell
.\.venv\Scripts\Activate.ps1
orca-task --help
```

If PowerShell blocks activation, use `.\.venv\Scripts\orca-task.exe` in place
of `orca-task`. Run Python examples with `.\.venv\Scripts\python.exe`.
An additional OpenAI API key is not required by the Python package.

## 2. Arrange the tabletop

- Use a flat tabletop, good lighting, and clearly separated objects.
- Keep each main object fully visible, preferably in a near-overhead photo.
- Choose up to five objects. For a larger scene, tell Codex which five to retain.
- Include a known measurement if available, such as the actual pen length.

Supported categories and their simulation representations:

| Category | Typical object | Rigid model |
|---|---|---|
| `box` | Small box or rectangular block | Box |
| `cylinder` | Soda can or cylindrical block | Cylinder |
| `sphere` | Ball | Sphere |
| `pen` | Pen or pencil | Thin capsule with simple visual details |
| `eraser` | Rectangular eraser | Box |
| `book` | Closed book | Box with simple cover/page details |

For other items, Codex asks before using a supported proxy. For example, an
earbud case can become a white box after you approve that simplification.
Flexible covers can only be represented as static-shape rigid objects; this
does not simulate folding or deformation.

## 3. Start phone upload

Send this message in Codex:

```text
Use $orca-env-generator. Start a phone photo upload session and show me the QR code.
```

Codex starts a local upload server and displays its QR code and full URL.
Keep the computer running, connect the phone to the same Wi-Fi, and scan the
code using the phone camera or QR scanner. Open the link in a browser.

Choose **Take a photo** or **Choose a photo**. If camera selection is unavailable,
take the photograph separately and use the album option. Wait for **Uploaded**.

Accepted formats are JPEG, PNG, WebP, and HEIC/HEIF, with a maximum file size of
20 MB and image size of 40 megapixels. The upload is normalized to PNG with
EXIF orientation applied and original metadata removed.

Each capture session accepts **one photograph**. To upload another, ask Codex
for a **new upload session and QR code**. Refreshing an old page does not create
a new session. Sessions normally expire after one hour.

Alternatively, start capture yourself and keep the terminal open:

```powershell
orca-task capture --lan --output photo_captures
```

The printed JSON contains the URL, QR image path, and session directory.
Use Ctrl+C in that terminal to stop the server when finished.

## 4. Return to Codex and generate the scene

Uploading does not automatically invoke Codex. Return to the chat and send:

```text
Continue with the uploaded photo. Generate a tabletop simulation scene and show it for review.
```

If you have measured an object, include the measurement:

```text
The pen is 14 cm long. Use this measurement to calibrate the scene.
```

Codex inspects the actual image, identifies objects, asks about unsupported
shapes or partial objects, and writes a SceneSpec. The Python CLI prepares
templates and compiles structured specifications; it does not recognize
photographs independently.

Codex then generates the MuJoCo scene, runs physics checks, and creates the
annotated image and previews. If geometry overlaps or is unstable, it reports
the failure and proposes a correction. It asks before moving or resizing an
object to resolve a collision.

## 5. Review the output

The scene directory contains:

```text
generated_scenes/<scene-id>/
  source.png             # Normalized phone photograph
  annotated.png          # Object boxes and IDs on the photograph
  scene_spec.yaml        # Dimensions, poses, proxies, and parameter provenance
  scene.xml              # Loadable MuJoCo model
  manifest.json          # Bundle metadata and specification hash
  scene_report.json      # Physics result and confirmation status
  scene_preview.png      # Rendered simulation scene
  scene_preview.mp4      # Camera orbit around the scene
```

Compare the source, annotations, and simulated scene. Check object count,
relative placement, orientation, and estimated dimensions. A physics pass
establishes stability, not an accurate reconstruction of the photograph.

Say what should change, or explicitly confirm the displayed scene. Only after
that review does Codex mark the current specification as confirmed. Any later
change requires regeneration and fresh review.

To inspect a scene yourself, substitute the exact returned directory:

```powershell
orca-task scene check generated_scenes/<scene-id>
orca-task scene preview generated_scenes/<scene-id>
orca-task scene view generated_scenes/<scene-id>
```

The preview video shows camera motion around the objects. This stage has no
robot hand, actions, rewards, or learned policy.

## 6. Optionally add an ORCA hand task

After reviewing the scene, select one object using its annotation ID:

```text
The displayed scene looks correct. Make the ORCA hand pick up pen_1 and hold it for 20 steps.
Generate the RL environment, run checks, and create a task preview.
```

The task is generated separately under `generated_tasks/`. It uses the same
`load_environment()` API as text-generated tasks. A task preview is a scripted
attempt through the public action space; it is not RL training and may fail.
Large objects such as tablet covers may exceed the hand's grasp span.

## Troubleshooting

| Symptom | What to check |
|---|---|
| QR link does not open | Both devices must use the same LAN, not a guest network with client isolation. Use the full URL, including port and token. |
| Computer has several network adapters | The advertised address must belong to the Wi-Fi/LAN reachable by the phone. VPN addresses may be unreachable. |
| VPN is connected | Where permitted, disconnect it temporarily or enable its local LAN access option. A VPN can route even local subnet traffic into its tunnel. |
| Correct Wi-Fi address is still unreachable | Check the firewall rule for the Python upload server and local port. Do not disable the entire firewall. |
| Wi-Fi says no Internet but websites work | VPN routing or a failed connectivity probe may explain the status. Phone upload depends on local connectivity, not the Windows Internet status label. |
| Wrong address chosen automatically | Start capture with `orca-task capture --lan --advertise-host <computer-wifi-ip>`. This changes the displayed address, not VPN routing or firewall policy. |
| Upload fails on a reused page | A session already holding a photograph rejects a second upload. Request a new session. |
| Upload succeeds but no scene appears | Return to Codex and say "Continue with the uploaded photo." The upload server cannot wake an idle chat. |
| Physics check fails | Review the reported objects. Approve a specific layout or size correction before regeneration. |

## Limits

Colors, dimensions, poses, and layout are approximate. Without a measured
reference, metric scale is assumed; mass and friction are defaults. This is
rigid proxy modeling, not calibrated image-to-mesh reconstruction. Logos,
opening lids, folding, writing, stacking, insertion, external meshes, and
two-hand manipulation are outside this release.

For reproducible evidence, see [photo acceptance and limitations](PHOTO_ACCEPTANCE.md).
