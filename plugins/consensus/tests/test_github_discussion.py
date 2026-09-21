#!/usr/bin/env python3
"""Protocol tests that do not contact GitHub."""

from __future__ import annotations

import importlib.util
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "github_discussion.py"
SPEC = importlib.util.spec_from_file_location("github_discussion", SCRIPT)
assert SPEC and SPEC.loader
github_discussion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(github_discussion)


def comment(payload: dict) -> dict:
    return {
        "body": github_discussion.render_comment(payload),
        "author": {"login": payload["participant"].split("/", 1)[0]},
        "createdAt": payload["created_at"],
        "url": "https://github.test/comment",
    }


def initial_fixture(max_rounds: int = 2) -> tuple[dict, dict, dict, str, str, dict]:
    task = "Choose the safest migration plan."
    digest = github_discussion.task_hash(task)
    initiator = "alice/codex-desktop"
    peer = "bob/codex-desktop"
    alice_nonce = "alice-nonce"
    bob_nonce = "bob-nonce"
    alice_answer = "Migrate in two reversible stages."
    bob_answer = "Start with a read-only shadow migration."
    alice_hash = github_discussion.initial_hash(
        digest, initiator, alice_nonce, alice_answer
    )
    bob_hash = github_discussion.initial_hash(digest, peer, bob_nonce, bob_answer)
    metadata = {
        "protocol": github_discussion.PROTOCOL,
        "kind": "ISSUE",
        "created_at": "2026-09-04T00:00:00+00:00",
        "task": task,
        "task_hash": digest,
        "initiator": initiator,
        "initiator_commitment": alice_hash,
        "expected_participants": 2,
        "max_rounds": max_rounds,
    }
    issue = {
        "url": "https://github.com/acme/project/issues/7",
        "title": "Test discussion",
        "state": "OPEN",
        "body": github_discussion.render_issue(metadata),
        "author": {"login": "alice"},
        "comments": [],
    }
    commit = {
        "protocol": github_discussion.PROTOCOL,
        "kind": "INITIAL_COMMIT",
        "created_at": "2026-09-04T00:01:00+00:00",
        "participant": peer,
        "task_hash": digest,
        "initial_hash": bob_hash,
    }
    bob_reveal = {
        "protocol": github_discussion.PROTOCOL,
        "kind": "INITIAL_REVEAL",
        "created_at": "2026-09-04T00:02:00+00:00",
        "participant": peer,
        "task_hash": digest,
        "initial_hash": bob_hash,
        "nonce": bob_nonce,
        "answer": bob_answer,
    }
    alice_reveal = {
        "protocol": github_discussion.PROTOCOL,
        "kind": "INITIAL_REVEAL",
        "created_at": "2026-09-04T00:03:00+00:00",
        "participant": initiator,
        "task_hash": digest,
        "initial_hash": alice_hash,
        "nonce": alice_nonce,
        "answer": alice_answer,
    }
    return issue, commit, bob_reveal, initiator, peer, alice_reveal


def discussion(
    participant: str,
    digest: str,
    round_number: int,
    verdict: str,
    proposal: str,
) -> dict:
    proposal_hash = github_discussion.resolution_hash(proposal)
    return {
        "protocol": github_discussion.PROTOCOL,
        "kind": "DISCUSSION",
        "created_at": f"2026-09-04T00:1{round_number}:00+00:00",
        "participant": participant,
        "task_hash": digest,
        "round": round_number,
        "answer": proposal,
        "agreements": ["Use a reversible rollout."],
        "blocking_disagreements": [] if verdict == "ACCEPT" else ["Need peer confirmation."],
        "revisions": [],
        "proposed_resolution": proposal,
        "resolution_hash": proposal_hash,
        "accepted_resolution_hash": proposal_hash if verdict == "ACCEPT" else None,
        "verdict": verdict,
    }


def test_independent_phase_and_consensus() -> None:
    issue, commit, bob_reveal, initiator, peer, alice_reveal = initial_fixture()
    issue["comments"] = [comment(commit), comment(bob_reveal)]
    waiting = github_discussion.audit(issue)
    assert waiting["phase"] == "WAITING_FOR_INITIATOR_REVEAL"
    assert initiator not in waiting["initial_answers"]

    issue["comments"].append(comment(alice_reveal))
    ready = github_discussion.audit(issue)
    assert ready["phase"] == "DISCUSSION"
    assert ready["expected_next_participant"] == initiator
    assert ready["roster"] == [initiator, peer]

    proposal = "Use a shadow migration, then two reversible cutover stages."
    digest = ready["task_hash"]
    issue["comments"].append(
        comment(discussion(initiator, digest, 1, "CONTINUE", proposal))
    )
    issue["comments"].append(
        comment(discussion(peer, digest, 1, "ACCEPT", proposal))
    )
    round_two = github_discussion.audit(issue)
    assert round_two["phase"] == "DISCUSSION"
    assert round_two["next_round"] == 2
    assert round_two["expected_next_participant"] == initiator

    issue["comments"].append(
        comment(discussion(initiator, digest, 2, "ACCEPT", proposal))
    )
    consensus = github_discussion.audit(issue)
    assert consensus["status"] == "CONSENSUS"
    assert consensus["consensus_resolution"] == proposal
    assert consensus["expected_next_participant"] is None

    final_payload = {
        "protocol": github_discussion.PROTOCOL,
        "kind": "FINAL",
        "created_at": "2026-09-04T00:30:00+00:00",
        "participant": initiator,
        "status": "CONSENSUS",
        "conclusion": proposal,
        "discussion_summary": "Both agents combined shadowing with reversible stages.",
        "termination_reason": consensus["termination_reason"],
    }
    issue["comments"].append(comment(final_payload))
    finalized = github_discussion.audit(issue)
    assert finalized["final_summary"]["conclusion"] == proposal


def test_round_limit_and_tampered_reveal() -> None:
    issue, commit, bob_reveal, initiator, peer, alice_reveal = initial_fixture(
        max_rounds=1
    )
    tampered = {**bob_reveal, "answer": "Changed after commitment."}
    issue["comments"] = [comment(commit), comment(tampered), comment(alice_reveal)]
    invalid = github_discussion.audit(issue)
    assert invalid["phase"] == "WAITING_FOR_PARTICIPANTS"
    assert invalid["invalid_protocol_comments"]

    forged_commit = comment(commit)
    forged_commit["author"] = {"login": "mallory"}
    issue["comments"] = [forged_commit, comment(bob_reveal), comment(alice_reveal)]
    forged = github_discussion.audit(issue)
    assert forged["phase"] == "WAITING_FOR_PARTICIPANTS"

    issue["comments"] = [comment(commit), comment(bob_reveal), comment(alice_reveal)]
    digest = github_discussion.audit(issue)["task_hash"]
    proposal = "Keep separate conclusions."
    issue["comments"].extend(
        [
            comment(discussion(initiator, digest, 1, "CONTINUE", proposal)),
            comment(discussion(peer, digest, 1, "CONTINUE", proposal)),
        ]
    )
    limited = github_discussion.audit(issue)
    assert limited["status"] == "LIMIT_REACHED"
    assert "1 complete rounds" in limited["termination_reason"]


def main() -> int:
    test_independent_phase_and_consensus()
    test_round_limit_and_tampered_reveal()
    print("ok: commitment, reveal, ordered rounds, hash consensus, and limit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
