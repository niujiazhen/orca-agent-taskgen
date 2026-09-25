from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_repo_and_plugin_skills_are_synchronized() -> None:
    repo_skill = ROOT / ".agents" / "skills" / "orca-env-generator" / "SKILL.md"
    plugin_skill = ROOT / "plugins" / "orca-env-generator" / "skills" / "orca-env-generator" / "SKILL.md"
    assert repo_skill.read_text(encoding="utf-8") == plugin_skill.read_text(encoding="utf-8")


def test_plugin_and_marketplace_identity_match() -> None:
    portable = json.loads(
        (ROOT / "plugins" / "orca-env-generator" / "plugin.json").read_text(encoding="utf-8")
    )
    compatibility = json.loads(
        (ROOT / "plugins" / "orca-env-generator" / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    marketplace = json.loads(
        (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
    )
    entry = marketplace["plugins"][0]
    assert portable["name"] == compatibility["name"] == entry["name"] == "orca-env-generator"
    assert portable["version"] == compatibility["version"] == "0.2.0"
    assert entry["source"]["path"] == "./plugins/orca-env-generator"
    assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}


def test_taskgen_has_no_training_dependencies_or_commands() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert "stable-baselines3" not in pyproject
    assert "tensorboard" not in pyproject
    for removed in ("train.py", "evaluate.py", "ppo_acceptance.py"):
        assert not (ROOT / "src" / "orca_sim" / "taskgen" / removed).exists()
