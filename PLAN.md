# ORCA Text-to-MuJoCo Agent v2

The v2 product boundary is natural-language generation of an untrained,
visualizable MuJoCo/Gymnasium environment. Training and PPO validation are not
part of the Agent.

## Phase gates

1. **Contracts and catalog** — TaskSpec v2 strictly validates one ORCA v1 right
   hand, three task families, three primitive shapes, and three gesture groups.
2. **Generic runtime** — every v2 bundle exposes a 23-value action, stable
   observation contract, seeded reset, bounded 6DoF wrist, rewards, and success.
3. **Feasibility and visualization** — random stress is finite; scripted actions
   reach success without training or direct state writes by the controller;
   zero/random actions do not falsely succeed; PNG/MP4 previews render.
4. **Codex UX** — repository Skill and installable Plugin accept Chinese or
   English text, reject unsupported tasks, invoke deterministic generation, and
   report the exact output bundle.
5. **Release** — tests, wheel contents, docs, examples, Skill, and Plugin pass
   clean-environment checks.

Legacy TaskSpec v1 PinchAndHold loading is retained as a compatibility path.
