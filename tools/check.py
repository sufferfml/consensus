#!/usr/bin/env python3
"""Run dependency-free packaging and offline behavior checks from any directory."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/consensus"


def main() -> int:
    manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert manifest["name"] == "consensus"
    assert manifest["license"] == "MIT"
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", manifest["version"])
    assert marketplace["name"] == "consensus"
    entries = marketplace["plugins"]
    assert len(entries) == 1 and entries[0]["name"] == "consensus"
    assert (ROOT / entries[0]["source"]["path"]).resolve() == PLUGIN.resolve()
    assert (PLUGIN / manifest["skills"]).is_dir()
    assert (ROOT / "LICENSE").read_bytes() == (PLUGIN / "LICENSE").read_bytes()
    for path in sorted(PLUGIN.rglob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print("ok: marketplace, plugin metadata, license and Python syntax", flush=True)

    # Remove participant/model overrides so a contributor's shell cannot alter
    # the fake-CLI test contract. No model/GitHub commands are used by the tests.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("DUAL_AGENT_", "GITHUB_CONSENSUS_", "FAKE_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for name in ("test_orchestrate.py", "test_github_discussion.py",
                 "test_github_cli_flow.py", "test_integrity.py"):
        subprocess.run([sys.executable, "-B", str(PLUGIN / "tests" / name)],
                       cwd=ROOT, env=env, check=True, timeout=90)
    print("All offline checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
