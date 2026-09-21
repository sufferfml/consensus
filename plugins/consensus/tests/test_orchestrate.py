#!/usr/bin/env python3
"""Hermetic integration test using fake Codex and Claude executables."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = PLUGIN_ROOT / "scripts" / "orchestrate.py"


FAKE_CODEX = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with pathlib.Path(os.environ["FAKE_CODEX_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(" ".join(args) + "\n")
out = pathlib.Path(args[args.index("--output-last-message") + 1])
initial = "resume" not in args
payload = {
  "answer": "Codex initial" if initial else "Shared answer",
  "agreements": [] if initial else ["shared"],
  "blocking_disagreements": ["needs peer review"] if initial else [],
  "revisions": [] if initial else ["accepted Claude evidence"],
  "proposed_resolution": "Shared answer",
  "accepted_peer_position": not initial,
  "verdict": "CONTINUE" if initial else "CONSENSUS"
}
out.write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps({"type":"thread.started","thread_id":"11111111-1111-4111-8111-111111111111"}))
'''


FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
log = pathlib.Path(os.environ["FAKE_CLAUDE_LOG"])
log.write_text(" ".join(args), encoding="utf-8")
initial = "--resume" not in args
payload = {
  "answer": "Claude initial" if initial else "Shared answer",
  "agreements": [] if initial else ["shared"],
  "blocking_disagreements": ["needs peer review"] if initial else [],
  "revisions": [] if initial else ["accepted Codex evidence"],
  "proposed_resolution": "Shared answer",
  "accepted_peer_position": not initial,
  "verdict": "CONTINUE" if initial else "CONSENSUS"
}
print(json.dumps({"structured_output": payload, "is_error": bool(os.environ.get("FAKE_CLAUDE_ERROR"))}))
'''


def make_executable(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    path.chmod(0o755)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dual-agent-test-") as raw_temp:
        temp = Path(raw_temp)
        codex = temp / "codex"
        claude = temp / "claude"
        log = temp / "claude-args.log"
        codex_log = temp / "codex-args.log"
        make_executable(codex, FAKE_CODEX)
        make_executable(claude, FAKE_CLAUDE)
        env = os.environ.copy()
        env.update(
            {
                "DUAL_AGENT_CODEX_BIN": str(codex),
                "DUAL_AGENT_CLAUDE_BIN": str(claude),
                "FAKE_CLAUDE_LOG": str(log),
                "FAKE_CODEX_LOG": str(codex_log),
                "DUAL_AGENT_CODEX_MODEL": "test-codex-model",
                "DUAL_AGENT_CLAUDE_MODEL": "test-claude-model",
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(ORCHESTRATOR),
                "--workdir",
                str(temp),
                "--output-root",
                str(temp),
                "--max-rounds",
                "2",
            ],
            input="Decide whether the test passes.",
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr + completed.stdout)
        result = json.loads(completed.stdout)
        assert result["status"] == "CONSENSUS"
        assert result["discussion_rounds"] == 1
        assert result["execution_policy"]["codex"].startswith("read-only")
        assert "safe mode and plan permission mode" in result["execution_policy"]["claude"]
        assert Path(result["transcript_path"]).is_file()
        transcript = Path(result["transcript_path"]).read_text(encoding="utf-8")
        assert "Codex initial" in transcript
        assert "Claude initial" in transcript
        args_log = log.read_text(encoding="utf-8")
        codex_args_log = codex_log.read_text(encoding="utf-8")
        assert "--safe-mode" in args_log
        assert "--setting-sources user" in args_log
        assert "--restricted" not in args_log
        assert "--permission-mode plan" in args_log
        assert "--strict-mcp-config" in args_log
        assert "dangerously" not in args_log
        assert "Read,Glob,Grep,Bash,WebFetch,WebSearch" in args_log
        assert "Edit" not in args_log
        assert "Write" not in args_log
        assert "--model test-claude-model" in args_log
        assert "--model test-codex-model" in codex_args_log
        assert "dangerously" not in transcript
        failed = subprocess.run(
            completed.args, input="Synthetic participant failure.", text=True,
            capture_output=True, env={**env, "FAKE_CLAUDE_ERROR": "1"}, check=False,
        )
        failed_result = json.loads(failed.stdout)
        assert failed.returncode == 1
        assert failed_result["status"] == "ERROR"
        assert "codex" in failed_result["partial"]
        assert "claude" not in failed_result["partial"]
        assert "unsuccessful CLI turn" in failed_result["termination_reason"]
        print("ok: independent start, one consensus round, safe verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
