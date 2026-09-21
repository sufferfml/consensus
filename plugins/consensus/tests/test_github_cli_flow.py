#!/usr/bin/env python3
"""End-to-end CLI test using a stateful fake gh executable."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "github_discussion.py"


FAKE_GH = r'''#!/usr/bin/env python3
import json, os, pathlib, sys

args = sys.argv[1:]
db_path = pathlib.Path(os.environ["FAKE_GH_DB"])
log_path = pathlib.Path(os.environ["FAKE_GH_LOG"])
login = os.environ.get("FAKE_GH_LOGIN", "alice")
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"args": args, "login": login}) + "\n")

if args == ["--version"]:
    print("gh version fake")
    raise SystemExit(0)
if args[:2] == ["auth", "status"]:
    print("logged in")
    raise SystemExit(0)
if args[:2] == ["api", "user"]:
    print(login)
    raise SystemExit(0)
if args[:2] == ["repo", "view"]:
    print("acme/project")
    raise SystemExit(0)

if args[:2] == ["issue", "create"]:
    title = args[args.index("--title") + 1]
    body = sys.stdin.read()
    db = {
        "number": 7,
        "url": "https://github.com/acme/project/issues/7",
        "title": title,
        "state": "OPEN",
        "body": body,
        "author": {"login": login},
        "comments": [],
    }
    db_path.write_text(json.dumps(db), encoding="utf-8")
    print(db["url"])
    raise SystemExit(0)

if args[:2] == ["issue", "view"]:
    db = json.loads(db_path.read_text(encoding="utf-8"))
    fields = args[args.index("--json") + 1].split(",")
    print(json.dumps({field: db[field] for field in fields}))
    raise SystemExit(0)

if args[:2] == ["issue", "comment"]:
    db = json.loads(db_path.read_text(encoding="utf-8"))
    index = len(db["comments"]) + 1
    db["comments"].append({
        "body": sys.stdin.read(),
        "author": {"login": login},
        "createdAt": f"2026-09-04T00:{index:02d}:00+00:00",
        "url": f"https://github.com/acme/project/issues/7#issuecomment-{index}",
    })
    db_path.write_text(json.dumps(db), encoding="utf-8")
    print(db["comments"][-1]["url"])
    raise SystemExit(0)

print("unsupported fake gh command", args, file=sys.stderr)
raise SystemExit(2)
'''


def make_executable(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    path.chmod(0o755)


def run(
    args: list[str],
    *,
    env: dict[str, str],
    login: str,
    data: dict | None = None,
) -> dict:
    command_env = {**env, "FAKE_GH_LOGIN": login}
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=json.dumps(data) if data is not None else None,
        text=True,
        capture_output=True,
        env=command_env,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr + completed.stdout)
    return json.loads(completed.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="github-consensus-flow-") as raw_temp:
        temp = Path(raw_temp)
        gh = temp / "gh"
        db = temp / "db.json"
        log = temp / "gh.log"
        state = temp / "state"
        make_executable(gh, FAKE_GH)
        env = {
            **os.environ,
            "GITHUB_CONSENSUS_GH_BIN": str(gh),
            "GITHUB_CONSENSUS_STATE_DIR": str(state),
            "FAKE_GH_DB": str(db),
            "FAKE_GH_LOG": str(log),
        }
        task = "Choose a rollout plan."
        started = run(
            [
                "start",
                "--repo",
                "acme/project",
                "--participant",
                "alice/codex-desktop",
                "--expected-participants",
                "2",
                "--max-rounds",
                "2",
            ],
            env=env,
            login="alice",
            data={"task": task, "initial_answer": "Use a staged rollout."},
        )
        issue = started["issue_url"]
        prepared = run(["prepare-join", issue], env=env, login="bob")
        assert prepared["task"] == task
        joined = run(
            ["join", issue, "--participant", "bob/codex-desktop"],
            env=env,
            login="bob",
            data={"initial_answer": "Use a shadow rollout first."},
        )
        assert joined["selected_for_roster"] is True
        revealed = run(
            ["reveal", issue, "--participant", "alice/codex-desktop"],
            env=env,
            login="alice",
        )
        assert revealed["phase"] == "DISCUSSION"

        proposal = "Run a shadow phase, then use a staged reversible rollout."
        alice_turn = {
            "answer": proposal,
            "agreements": ["Begin with shadowing."],
            "blocking_disagreements": [],
            "revisions": ["Added shadowing."],
            "proposed_resolution": proposal,
            "verdict": "ACCEPT",
        }
        after_alice = run(
            ["post-turn", issue, "--participant", "alice/codex-desktop"],
            env=env,
            login="alice",
            data=alice_turn,
        )
        assert after_alice["expected_next_participant"] == "bob/codex-desktop"
        after_bob = run(
            ["post-turn", issue, "--participant", "bob/codex-desktop"],
            env=env,
            login="bob",
            data={**alice_turn, "revisions": ["Accepted staged cutover."]},
        )
        assert after_bob["status"] == "CONSENSUS"

        finalized = run(
            ["finalize", issue, "--participant", "alice/codex-desktop"],
            env=env,
            login="alice",
            data={
                "conclusion": proposal,
                "discussion_summary": "Alice added Bob's shadow phase; Bob accepted the staged cutover.",
                "termination_reason": after_bob["termination_reason"],
            },
        )
        assert finalized["final_summary"]["conclusion"] == proposal

        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        prepare_views = [
            record
            for record in records
            if record["login"] == "bob"
            and record["args"][:2] == ["issue", "view"]
        ]
        assert "comments" not in prepare_views[0]["args"][prepare_views[0]["args"].index("--json") + 1]
        database = json.loads(db.read_text(encoding="utf-8"))
        assert len(database["comments"]) == 6
        print("ok: start, blind join, reveal, ordered turns, consensus, and finalization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
