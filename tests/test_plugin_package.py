from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "dev-task-router"


def test_plugin_manifest_and_marketplace_are_valid() -> None:
    manifest_path = PLUGIN / ".codex-plugin" / "plugin.json"
    marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "dev-task-router"
    assert manifest["version"] == "0.9.0"
    assert manifest["skills"] == "./skills/"
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    assert manifest["interface"]["displayName"] == "项目拆解器"
    assert "recovery" in manifest["description"].lower() or "recover" in manifest["description"].lower()
    assert "evidence" in manifest["description"].lower()

    plugins = marketplace["plugins"]
    assert len(plugins) == 1
    assert plugins[0]["name"] == "dev-task-router"
    assert plugins[0]["source"]["path"] == "./plugins/dev-task-router"


def test_required_skills_have_frontmatter_and_correct_routing_policy() -> None:
    required = {
        "index",
        "inspect-repository",
        "decompose-project",
        "classify-task",
        "route-model",
        "build-context-pack",
        "switch-local-mode",
        "prepare-local-execution",
        "recover-execution",
        "create-handoff",
    }

    for skill_name in required:
        path = PLUGIN / "skills" / skill_name / "SKILL.md"
        assert path.exists(), f"missing {path}"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\nname:"), f"missing frontmatter in {path}"
        assert "description:" in text.split("---", 2)[1]

    index_text = (PLUGIN / "skills" / "index" / "SKILL.md").read_text(encoding="utf-8")
    assert "LOW failure    → MEDIUM" in index_text
    assert "MEDIUM failure → HIGH" in index_text
    assert "weak-first" in index_text
    assert "commit-anchored" in index_text
    assert "repository dump" in index_text.lower()
    assert "same canonical conversation" in index_text.lower()

    inspect_text = (PLUGIN / "skills" / "inspect-repository" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "commit SHA" in inspect_text
    assert "at most 12" in inspect_text
    assert "Do not fabricate" in inspect_text
    assert "changed_files" in inspect_text and "test_files" in inspect_text

    decompose_text = (PLUGIN / "skills" / "decompose-project" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Project → Stage → Step → Task" in decompose_text
    assert "escalate_after: 1" in decompose_text
    assert "Surface" in decompose_text
    assert "Repository" in decompose_text

    classify_text = (PLUGIN / "skills" / "classify-task" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "blast radius" in classify_text
    assert "Confidence" in classify_text
    assert "Traits" in classify_text
    assert "commit-anchored" in classify_text

    route_text = (PLUGIN / "skills" / "route-model" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Chat" in route_text
    assert "Codex / Work" in route_text
    assert "do not invent" in route_text.lower()

    context_text = (PLUGIN / "skills" / "build-context-pack" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Task decomposition must not become conversation decomposition" in context_text
    assert "rolling project context" in context_text.lower()
    assert "stale_context" in context_text
    assert "full conversation history" in context_text

    switch_text = (PLUGIN / "skills" / "switch-local-mode" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "same conversation" in switch_text.lower()
    assert "verified: true" in switch_text
    assert "no fixed screen coordinates" in switch_text.lower()
    assert "MODE_SWITCH" in switch_text

    execution_text = (PLUGIN / "skills" / "prepare-local-execution" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "STALE_CONTEXT" in execution_text
    assert "PROFILE_MISMATCH" in execution_text
    assert "must not increment the Task attempt counter" in execution_text
    assert "must not claim the coding Task has run" in execution_text
    assert "autodev-local gate --switch" in execution_text

    recovery_text = (PLUGIN / "skills" / "recover-execution" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "SAFE_RETRY" in recovery_text
    assert "AMBIGUOUS" in recovery_text
    assert "execution-evidence.jsonl" in recovery_text
    assert "autodev-local audit --json" in recovery_text
    assert "autodev-local sync-repository --json" in recovery_text
    assert "same canonical ChatGPT conversation must not be described as an independent reviewer" in recovery_text
    assert "implemented but not live-verified" in recovery_text

    handoff_text = (PLUGIN / "skills" / "create-handoff" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Commit:" in handoff_text
    assert "CI:" in handoff_text
    assert "12 relevant" in handoff_text
