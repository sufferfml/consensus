#!/usr/bin/env python3
"""Regression tests for failure handling and untrusted protocol input."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_github_discussion import (  # noqa: E402
    comment, discussion, github_discussion as gh, initial_fixture,
)

SPEC = importlib.util.spec_from_file_location("orchestrate", ROOT / "scripts/orchestrate.py")
assert SPEC and SPEC.loader
local = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = local
SPEC.loader.exec_module(local)


def position(**changes):
    return {
        "answer": "Ship in stages.", "agreements": [], "blocking_disagreements": [],
        "revisions": [], "proposed_resolution": "Ship in stages.",
        "accepted_peer_position": True, "verdict": "CONSENSUS", **changes,
    }


class IntegrityTests(unittest.TestCase):
    def test_claude_failed_wrapper_cannot_count_as_success(self):
        for flags in ({"is_error": True}, {"subtype": "error_during_execution"}):
            raw = json.dumps({**flags, "structured_output": position()})
            with self.assertRaises(local.OrchestrationError):
                local.claude_payload(raw, "Claude")
        self.assertEqual(local.claude_payload(json.dumps({
            "is_error": False, "structured_output": position(),
        }), "Claude"), position())

    def test_exact_resolution_and_bilateral_acceptance(self):
        self.assertTrue(local.is_consensus(position(), position()))
        self.assertFalse(local.is_consensus(position(), position(accepted_peer_position=False)))
        self.assertFalse(local.is_consensus(position(), position(blocking_disagreements=["Risk"])))
        self.assertFalse(local.is_consensus(position(), position(proposed_resolution="Ship in stages. No edits.")))
        with self.assertRaises(local.OrchestrationError):
            local.validate_turn(position(unexpected="data"), "test")

    def ready_issue(self):
        issue, commit, peer_reveal, initiator, peer, owner_reveal = initial_fixture()
        issue["comments"] = [comment(commit), comment(peer_reveal), comment(owner_reveal)]
        digest = gh.audit(issue)["task_hash"]
        return issue, initiator, peer, digest

    def test_falsey_wrong_type_blockers_are_not_empty_arrays(self):
        for value in (False, None, "", 0, {}):
            issue, initiator, _, digest = self.ready_issue()
            payload = discussion(initiator, digest, 1, "ACCEPT", "Proposal")
            payload["blocking_disagreements"] = value
            # Inject raw marker to bypass the human-facing renderer.
            issue["comments"].append({
                "body": gh.encode_marker(payload), "author": {"login": "alice"},
            })
            result = gh.audit(issue)
            self.assertEqual(result["valid_discussion"], [])
            self.assertEqual(len(result["invalid_protocol_comments"]), 1)

    def test_final_reason_is_checked_on_read_not_only_publication(self):
        issue, initiator, peer, digest = self.ready_issue()
        for participant in (initiator, peer):
            issue["comments"].append(comment(discussion(participant, digest, 1, "ACCEPT", "Proposal")))
        result = gh.audit(issue)
        payload = {
            "protocol": gh.PROTOCOL, "kind": "FINAL", "participant": initiator,
            "created_at": "2026-09-22T00:00:00Z", "status": "CONSENSUS",
            "conclusion": "Proposal", "discussion_summary": "Both accepted.",
            "termination_reason": "Invented reason",
        }
        issue["comments"].append(comment(payload))
        self.assertIsNone(gh.audit(issue)["final_summary"])
        payload["termination_reason"] = result["termination_reason"]
        issue["comments"][-1] = comment(payload)
        self.assertEqual(gh.audit(issue)["final_summary"]["conclusion"], "Proposal")

    def test_changed_commit_is_reported_without_replacing_first(self):
        issue, commit, peer_reveal, _, _, owner_reveal = initial_fixture()
        changed = {**commit, "initial_hash": "0" * 64}
        issue["comments"] = [comment(commit), comment(changed), comment(peer_reveal), comment(owner_reveal)]
        result = gh.audit(issue)
        self.assertEqual(result["phase"], "DISCUSSION")
        self.assertTrue(any("changed" in item["error"] for item in result["invalid_protocol_comments"]))

    def test_state_is_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "GITHUB_CONSENSUS_STATE_DIR": temporary,
        }):
            state = {"repo": "acme/project", "issue_number": 7,
                     "participant": "alice/agent", "initial_answer": "Private"}
            path = gh.save_state(state)
            self.assertEqual(json.loads(path.read_text()), state)
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            gh.save_state({**state, "initial_answer": "Replacement"})
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
            self.assertEqual(json.loads(path.read_text())["initial_answer"], "Replacement")


if __name__ == "__main__":
    unittest.main()
