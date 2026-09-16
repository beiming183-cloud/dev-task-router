from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v09_package_and_plugin_versions_are_synchronized() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_init = (ROOT / "src" / "dev_task_router" / "__init__.py").read_text(
        encoding="utf-8"
    )
    manifest = json.loads(
        (ROOT / "plugins" / "dev-task-router" / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert 'version = "0.9.0"' in pyproject
    assert '__version__ = "0.9.0"' in package_init
    assert manifest["version"] == "0.9.0"
