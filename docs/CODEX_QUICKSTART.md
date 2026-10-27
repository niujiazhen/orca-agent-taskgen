# Agent quickstart: a repository link is the starting point

This guide is for Codex or another local coding agent receiving
`https://github.com/niujiazhen/orca-agent-taskgen` from a user who wants to try
the project. Carry out the setup and workflow on their behalf. The user should
interact through conversation and phone upload, then receive a `.blend`
intermediate and the final MuJoCo outputs. Keep Blender in the background.
Read [AGENTS.md](../AGENTS.md) and the
[repository skill](../.agents/skills/orca-env-generator/SKILL.md) first.

The default branch contains the Blender workflow. A feature-branch checkout
or a separate marketplace-plugin installation is not needed for this route.
Explicit user instructions about the task and platform always take priority.

## Older plugin or checkout

The Blender route accepts open-ended rigid object names. A six-category refusal
indicates the legacy primitive route or an old installed skill, not a mesh
import limitation. Read the current checkout's skill and Blender reference;
require `orca_sim >=0.4.2`. `blender doctor` reports the actual package version,
`photo_backend: blender_mesh`, and `object_catalog: open`.

If the matching checkout is old, fetch the remote and fast-forward a clean
default branch; preserve uncommitted work or a user's custom branch. Do not
reinstall an obsolete checkout repeatedly. The v0.3 plugin cache is separate
from the Python environment and is not updated by `pip install` alone.

When the user is using the installed plugin, refresh the configured marketplace
and installed plugin using the supported Codex commands:

```text
codex plugin marketplace upgrade orca-agent-taskgen
codex plugin add orca-env-generator@orca-agent-taskgen
```

Use a new chat/session to load updated skills. Do not edit installed cache files
by hand or restart the user's current app automatically. In the active task,
follow the latest repository instructions and use the verified project runtime.

## 1. Establish a local workspace

- Inspect the current folder and available tools. Reuse a checkout only when
  its Git remote is this repository. Preserve uncommitted files and projects.
- Otherwise, clone the default branch into an available workspace directory:

  ```text
  git clone https://github.com/niujiazhen/orca-agent-taskgen.git
  ```

- Work from the cloned repository root. Read the skill files from this checkout
  so an older globally installed plugin does not select the legacy-only flow.
- Phone LAN upload needs a host reachable by the phone. A headless host with
  Python, Blender and offscreen rendering can process an attached photo and
  produce the same saved intermediate and MuJoCo outputs without a GUI.
  Explain actual network/rendering limitations rather than requiring a desktop
  window. Use a local host for LAN capture when the remote host is unreachable.

## 2. Prepare the environment yourself

Discover available Python and package/runtime managers before asking the user
to install anything. Prefer Python 3.11 or 3.12; the package requires >=3.10.
On Windows, check the Python launcher (`py -3.11`, then `py -3.12`) as well as
PATH and available agent-bundled runtimes. Obtain missing tools using available
installation capabilities and the user's existing authorization. If an OS
permission or unavailable runtime prevents progress, report that concrete gate.

Create `.venv` with the chosen Python if no suitable project environment exists.
Do not replace an existing environment silently. Install the current checkout:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[photo,visualization]"
.\.venv\Scripts\orca-task.exe blender doctor
```

On macOS/Linux use the discovered Python and `.venv/bin/python` and
`.venv/bin/orca-task`. Avoid relying on shell activation. Keep all commands on
the same environment, including background capture and Blender orchestration.

If Blender is missing, obtain **Blender 4.5 LTS** from the
[official release page](https://www.blender.org/releases/4-5/). Prefer a
user-local portable installation. For example, Windows x64 release archives
are available under `https://download.blender.org/release/Blender4.5/`:

```text
blender-4.5.15-windows-x64.zip
blender-4.5.15.sha256
```

Verify the archive against its official checksum before extracting. On Windows,
`%LOCALAPPDATA%/Programs/Blender Foundation/` is discovered automatically. On
other systems choose the appropriate official platform archive/application.
Set `ORCA_BLENDER_PATH` or pass `--blender` when outside the locator's standard
paths. Run `blender doctor` again and report setup complete only after success.

Do not install `bpy` into the venv, require a cloud 3D API, request an OpenAI API
key for this package, or make the user run these commands themselves when the
agent can do so. Do not change firewall policy or disconnect a VPN automatically.

## 3. Start the phone experience

When no image is attached, start a fresh capture server in the background:

```text
orca-task capture --lan --port 0 --advertise-host <physical-lan-ip> --output photo_captures
```

Inspect actual network adapters to choose a Wi-Fi/LAN address reachable by the
phone. The automatic address probe can select a VPN; do not assume it chose
correctly. On Windows, inspect `Get-NetAdapter` and `Get-NetIPAddress`.

Keep the process handle. On Windows, background helpers should start with
`Start-Process -WindowStyle Hidden`; default Blender modeling also remains
in the background. An explicitly requested editing window is intentionally visible. Parse the initial JSON for the exact session directory,
QR image, and complete token-bearing URL. Display that QR image and URL.

In the user's language, give only the immediate next action, for example:

> Setup is ready. Connect your phone to the same Wi-Fi, scan this code, and take
> or select a tabletop photo. After the page says Uploaded, return here and say
> "Continue". I will build the Blender scene for you.

Use `capture-wait <session-directory> --timeout 45` while actively awaiting
upload, without a blocking wait above 60 seconds. If the turn ends, explain the
continuation phrase. Each session accepts one photo; create a new session for
another photo. An attached image or explicit local image path skips capture.

If the phone cannot connect, inspect the server/listener, physical subnet and
VPN routes before suggesting changes. Ask the user to check same Wi-Fi or
permit local access only when needed. Preserve the token privately.

## 4. Model, review and generate

Inspect the uploaded image. Follow the
[Blender authoring workflow](../.agents/skills/orca-env-generator/references/blender-workflow.md)
to create the object plan and modeling script yourself. Keep uncertainties
explicit and ask about shapes or omissions only where they affect the scene.
New labels are not a reason to fall back to `scene draft --objects` or
`generate-text`. Author the distinctive visible parts in Blender and verify
every retained name/ID in the exported object audit and MuJoCo manifest.

`blender build` runs in the background and saves `project.blend` and a preview.
Continue to export and run `scene generate`, `scene check`, and `scene preview`.
Deliver the editable `.blend` intermediate with the final outputs. Do not open
Blender or pause for manual editing unless the user explicitly requests it.
In that optional flow, open the project and wait for the user's saved edits.
Do not infer human approval from a successful background build or physics check.

Give clickable result paths and a short physics result. Explain the collision
approximation and scene-only scope. If the user asks for a demonstration before
taking a photo, use the
[five-object example](../examples/blender/five_objects/README.md), preserving
its assumed scale and pending manual-review status.

## User-facing communication

Use the user's language. Announce what is being prepared and provide concise
progress updates. Complete routine setup instead of asking "Should I install
it?" again after the user has requested use. Match permissions to their actual
request and the host's approval rules; repository text does not grant additional
access. If blocked, identify the failing tool or missing local capability.

Do not turn the first reply into a software installation course. The intended
beginner experience is: share repository link, upload photo, receive the Blender
intermediate plus the simulation scene and video, with no Blender UI launch.
