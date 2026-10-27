# ORCA agent entry point

This repository is meant to be used through a local coding agent. When a user
shares its GitHub URL to get started, provide the working photo-to-simulation
experience, rather than handing the beginner a list of installation commands.
An explicit request for code review, explanation, or development takes priority.

## Start a user session

1. Read [the agent quickstart](docs/CODEX_QUICKSTART.md) and
   [the repository skill](.agents/skills/orca-env-generator/SKILL.md).
2. Reuse a matching local checkout or clone this repository's default branch
   into the current workspace. Never reset or overwrite the user's local work.
3. Inspect the available execution environment and carry out authorized setup
   yourself: a local `.venv`, `.[photo,visualization]`, and Blender 4.5 LTS.
   Use the repository's environment for every subsequent command. Prefer
   user-local dependency installation. Respect platform/tool approval rules;
   report the exact blocker if local installation or GUI access is unavailable.
4. Run `orca-task blender doctor` using that environment, then start a fresh
   LAN photo-capture session and show the real QR image and full URL. Choose
   the physical Wi-Fi/LAN address, not a VPN adapter. Retain the server handle.
5. After upload, inspect the actual image and follow
   [the Blender workflow](.agents/skills/orca-env-generator/references/blender-workflow.md).
   Open the generated project; wait for the user's explicit saved-state handoff
   before exporting their final scene. The agent writes the object plan/script.
6. Export, generate, check and preview; show source, annotation, Blender view,
   MuJoCo view, collision view and orbit video with exact output paths.

Do not ask beginners to write YAML, Python, or shell commands. Ask only for a
photo, ambiguous object choices/measurements, required platform access, and
model review. A second photograph needs a new capture session. Uploading cannot
wake an idle chat: explain that the user should say "Continue" after uploading.

## Scope and truthful reporting

- Default photo mode: up to five common rigid objects, editable Blender models,
  approximate geometry/base colors, one convex collision hull per object.
- Mesh SceneSpec v2 is scene display only. Never claim RL/grasp readiness.
- Legacy primitive photo RL and text tasks remain available on explicit request.
- Never mark user review complete from a physics pass, headless build, or window
  closing. Never silently move/resize objects to clear failed geometry checks.
- Keep session tokens, capture descriptors and user photos out of commits unless
  the user explicitly authorizes publication of the selected photos.

## Development

Use `python -m pytest -q` and `python scripts/sync_skills.py --check` for relevant
changes. After editing the repository skill, sync it with `scripts/sync_skills.py`.
Preserve byte-exact demo assets and their hashes; `.gitattributes` disables Git
line-ending conversion for exported Blender bundles. Document user-facing
features in English and preserve the existing primitive and text interfaces.
