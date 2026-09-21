#!/usr/bin/env python3
"""Coordinate an auditable multi-agent discussion through GitHub Issue comments."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROTOCOL = "codex-agent-consensus/v1"
MARKER_PREFIX = "<!-- codex-agent-consensus:v1:"
MARKER_RE = re.compile(
    r"<!-- codex-agent-consensus:v1:([A-Za-z0-9_-]+) -->"
)
DEFAULT_MAX_ROUNDS = 10
DEFAULT_EXPECTED_PARTICIPANTS = 2
MAX_GITHUB_BODY_BYTES = 60_000


class ProtocolError(RuntimeError):
    """The local state, GitHub transcript, or requested transition is invalid."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def task_hash(task: str) -> str:
    return sha256_text(f"{PROTOCOL}\0task\0{normalize_text(task)}")


def initial_hash(task_digest: str, participant: str, nonce: str, answer: str) -> str:
    material = "\0".join(
        (PROTOCOL, "initial", task_digest, participant, nonce, normalize_text(answer))
    )
    return sha256_text(material)


def resolution_hash(resolution: str) -> str:
    return sha256_text(f"{PROTOCOL}\0resolution\0{normalize_text(resolution)}")


def encode_marker(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{MARKER_PREFIX}{encoded} -->"


def decode_marker(body: str) -> dict[str, Any] | None:
    match = MARKER_RE.search(body or "")
    if not match:
        return None
    encoded = match.group(1)
    encoded += "=" * (-len(encoded) % 4)
    try:
        value = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"Malformed protocol marker: {exc}") from exc
    if not isinstance(value, dict) or value.get("protocol") != PROTOCOL:
        raise ProtocolError("Unsupported or malformed protocol marker")
    return value


def ensure_body_size(body: str) -> None:
    size = len(body.encode("utf-8"))
    if size > MAX_GITHUB_BODY_BYTES:
        raise ProtocolError(
            f"Rendered GitHub body is {size} bytes; keep it below "
            f"{MAX_GITHUB_BODY_BYTES} bytes"
        )


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not normalize_text(value):
        raise ProtocolError(f"{field} must be a non-empty string")
    return normalize_text(value)


def require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and normalize_text(item) for item in value
    ):
        raise ProtocolError(f"{field} must be a list of non-empty strings")
    return [normalize_text(item) for item in value]


def read_json_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Standard input must be one JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ProtocolError("Standard input must be one JSON object")
    return value


def validate_participant(value: str) -> str:
    participant = normalize_text(value)
    if len(participant) > 100 or not re.fullmatch(r"[A-Za-z0-9_.@/+:-]+", participant):
        raise ProtocolError(
            "Participant id must be 1-100 characters using letters, digits, or _ . @ / + : -"
        )
    return participant


def resolve_binary() -> str:
    override = os.environ.get("GITHUB_CONSENSUS_GH_BIN")
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        found = shutil.which(override)
        if found:
            return found
        raise ProtocolError(f"GITHUB_CONSENSUS_GH_BIN is unavailable: {override}")
    found = shutil.which("gh")
    if not found:
        raise ProtocolError("Required command not found on PATH: gh")
    return found


class GitHub:
    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or resolve_binary()

    def run(
        self,
        args: Sequence[str],
        *,
        input_text: str | None = None,
        timeout: int = 60,
    ) -> str:
        try:
            completed = subprocess.run(
                [self.binary, *args],
                input=input_text,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProtocolError(f"Could not run gh {' '.join(args[:2])}: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            if len(detail) > 2000:
                detail = detail[-2000:]
            raise ProtocolError(f"gh {' '.join(args[:2])} failed: {detail}")
        return completed.stdout.strip()

    def login(self) -> str:
        return validate_participant(self.run(["api", "user", "--jq", ".login"]))

    def repo(self) -> str:
        return self.run(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])

    def issue(
        self, reference: str, repo: str | None, *, include_comments: bool
    ) -> dict[str, Any]:
        fields = "number,url,title,state,body,author"
        if include_comments:
            fields += ",comments"
        args = ["issue", "view", reference, "--json", fields]
        if repo:
            args.extend(["--repo", repo])
        try:
            value = json.loads(self.run(args))
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"gh issue view returned invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ProtocolError("gh issue view did not return an object")
        return value

    def create_issue(self, repo: str, title: str, body: str) -> str:
        return self.run(
            ["issue", "create", "--repo", repo, "--title", title, "--body-file", "-"],
            input_text=body,
        )

    def comment(self, reference: str, repo: str | None, body: str) -> str:
        args = ["issue", "comment", reference, "--body-file", "-"]
        if repo:
            args.extend(["--repo", repo])
        return self.run(args, input_text=body)


def parse_issue_identity(url: str) -> tuple[str, int]:
    match = re.search(r"/([^/]+)/([^/]+)/issues/(\d+)(?:$|[/?#])", url)
    if not match:
        raise ProtocolError(f"Could not parse repository and issue number from URL: {url}")
    return f"{match.group(1)}/{match.group(2)}", int(match.group(3))


def parse_issue(issue: dict[str, Any]) -> dict[str, Any]:
    body = issue.get("body")
    if not isinstance(body, str):
        raise ProtocolError("Issue body is missing")
    metadata = decode_marker(body)
    if not metadata or metadata.get("kind") != "ISSUE":
        raise ProtocolError("This is not a Codex agent-consensus issue")
    task = require_string(metadata.get("task"), "issue task")
    if metadata.get("task_hash") != task_hash(task):
        raise ProtocolError("Issue task hash does not match the original task")
    initiator = validate_participant(require_string(metadata.get("initiator"), "initiator"))
    author = issue.get("author")
    author_login = author.get("login") if isinstance(author, dict) else None
    if author_login != initiator.split("/", 1)[0]:
        raise ProtocolError("Issue author does not match the declared initiator")
    expected = metadata.get("expected_participants")
    rounds = metadata.get("max_rounds")
    if not isinstance(expected, int) or not 2 <= expected <= 8:
        raise ProtocolError("Issue expected_participants must be between 2 and 8")
    if not isinstance(rounds, int) or not 1 <= rounds <= 10:
        raise ProtocolError("Issue max_rounds must be between 1 and 10")
    commitment = require_string(
        metadata.get("initiator_commitment"), "initiator commitment"
    )
    if not re.fullmatch(r"[0-9a-f]{64}", commitment):
        raise ProtocolError("Issue initiator commitment is invalid")
    metadata["task"] = task
    metadata["initiator"] = initiator
    metadata["expected_participants"] = expected
    metadata["max_rounds"] = rounds
    return metadata


def state_root() -> Path:
    configured = os.environ.get("GITHUB_CONSENSUS_STATE_DIR")
    root = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".codex" / "github-agent-consensus"
    )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def state_path(repo: str, issue_number: int, participant: str) -> Path:
    repo_dir = state_root() / repo.replace("/", "__")
    repo_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = sha256_text(participant)[:16]
    return repo_dir / f"issue-{issue_number}--{identity}.json"


def save_state(state: dict[str, Any]) -> Path:
    path = state_path(state["repo"], state["issue_number"], state["participant"])
    # Unique, owner-only temporary file from creation, followed by atomic replace.
    # Never expose the independent answer through a world-readable staging file.
    fd, name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def load_state(repo: str, issue_number: int, participant: str | None) -> tuple[dict[str, Any], Path]:
    if participant:
        path = state_path(repo, issue_number, validate_participant(participant))
        candidates = [path] if path.is_file() else []
    else:
        repo_dir = state_root() / repo.replace("/", "__")
        candidates = sorted(repo_dir.glob(f"issue-{issue_number}--*.json")) if repo_dir.is_dir() else []
    if not candidates:
        raise ProtocolError(
            "No local participant state for this issue. Start or join the discussion on this machine first."
        )
    if len(candidates) > 1:
        raise ProtocolError("Multiple local participant states exist; specify --participant")
    path = candidates[0]
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"Could not read local participant state: {exc}") from exc
    if not isinstance(state, dict):
        raise ProtocolError("Local participant state is malformed")
    return state, path


def event_from_comment(comment: dict[str, Any], index: int) -> dict[str, Any] | None:
    body = comment.get("body")
    if not isinstance(body, str):
        return None
    try:
        payload = decode_marker(body)
    except ProtocolError as exc:
        return {"index": index, "error": str(exc), "payload": None}
    if not payload:
        return None
    author = comment.get("author")
    login = author.get("login") if isinstance(author, dict) else None
    return {
        "index": index,
        "author": login,
        "created_at": comment.get("createdAt"),
        "url": comment.get("url"),
        "payload": payload,
    }


def validate_event_author(event: dict[str, Any], participant: str) -> None:
    expected = participant.split("/", 1)[0]
    if event.get("author") != expected:
        raise ProtocolError(
            f"GitHub comment author {event.get('author')!r} does not match participant {participant!r}"
        )


def has_initial_event(
    issue: dict[str, Any],
    *,
    kind: str,
    participant: str,
    commitment: str,
) -> bool:
    comments = issue.get("comments", [])
    if not isinstance(comments, list):
        return False
    for index, comment in enumerate(comments):
        if not isinstance(comment, dict):
            continue
        event = event_from_comment(comment, index)
        if not event or not isinstance(event.get("payload"), dict):
            continue
        payload = event["payload"]
        if (
            payload.get("kind") == kind
            and payload.get("participant") == participant
            and payload.get("initial_hash") == commitment
            and event.get("author") == participant.split("/", 1)[0]
        ):
            return True
    return False


def validate_commit(payload: dict[str, Any], issue_meta: dict[str, Any]) -> tuple[str, str]:
    if payload.get("kind") != "INITIAL_COMMIT":
        raise ProtocolError("not an initial commitment")
    participant = validate_participant(require_string(payload.get("participant"), "participant"))
    digest = require_string(payload.get("initial_hash"), "initial_hash")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ProtocolError("initial_hash is invalid")
    if payload.get("task_hash") != issue_meta["task_hash"]:
        raise ProtocolError("commitment uses a different task hash")
    return participant, digest


def validate_reveal(
    payload: dict[str, Any],
    issue_meta: dict[str, Any],
    commitments: dict[str, tuple[str, int]],
) -> tuple[str, str]:
    if payload.get("kind") != "INITIAL_REVEAL":
        raise ProtocolError("not an initial reveal")
    participant = validate_participant(require_string(payload.get("participant"), "participant"))
    answer = require_string(payload.get("answer"), "answer")
    nonce = require_string(payload.get("nonce"), "nonce")
    supplied = require_string(payload.get("initial_hash"), "initial_hash")
    calculated = initial_hash(issue_meta["task_hash"], participant, nonce, answer)
    if supplied != calculated:
        raise ProtocolError("initial reveal does not match its commitment")
    if participant == issue_meta["initiator"]:
        committed = issue_meta["initiator_commitment"]
    else:
        committed = commitments.get(participant, (None, -1))[0]
    if committed != supplied:
        raise ProtocolError("initial reveal has no matching earlier commitment")
    return participant, answer


def accepted_consensus(
    roster: list[str], latest: dict[str, dict[str, Any]]
) -> tuple[str | None, str | None]:
    if any(participant not in latest for participant in roster):
        return None, None
    accepted: set[str] = set()
    resolution: str | None = None
    for participant in roster:
        payload = latest[participant]
        if payload.get("verdict") != "ACCEPT" or payload.get("blocking_disagreements") != []:
            return None, None
        digest = payload.get("accepted_resolution_hash")
        proposal = payload.get("proposed_resolution")
        if not isinstance(digest, str) or not isinstance(proposal, str):
            return None, None
        if resolution_hash(proposal) != digest:
            return None, None
        accepted.add(digest)
        resolution = normalize_text(proposal)
    if len(accepted) != 1:
        return None, None
    return accepted.pop(), resolution


def audit(issue: dict[str, Any]) -> dict[str, Any]:
    meta = parse_issue(issue)
    raw_comments = issue.get("comments", [])
    if not isinstance(raw_comments, list):
        raise ProtocolError("GitHub comments payload is malformed")
    events = [
        event
        for index, comment in enumerate(raw_comments)
        if isinstance(comment, dict)
        for event in [event_from_comment(comment, index)]
        if event is not None
    ]
    invalid: list[dict[str, Any]] = []
    commitments: dict[str, tuple[str, int]] = {}
    reveals: dict[str, dict[str, Any]] = {}
    reveal_order: list[str] = []

    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            invalid.append(event)
            continue
        kind = payload.get("kind")
        if kind == "INITIAL_COMMIT":
            try:
                participant, digest = validate_commit(payload, meta)
                validate_event_author(event, participant)
                if participant == meta["initiator"]:
                    raise ProtocolError("initiator commitment belongs in the issue body")
                if participant not in commitments:
                    commitments[participant] = (digest, event["index"])
                elif commitments[participant][0] != digest:
                    raise ProtocolError("initial commitment was changed")
            except ProtocolError as exc:
                invalid.append({**event, "error": str(exc)})
        elif kind == "INITIAL_REVEAL":
            try:
                participant, _answer = validate_reveal(payload, meta, commitments)
                validate_event_author(event, participant)
                if participant in reveals:
                    raise ProtocolError("duplicate initial reveal")
                if participant != meta["initiator"]:
                    commit_index = commitments[participant][1]
                    if commit_index >= event["index"]:
                        raise ProtocolError("commitment must precede reveal")
                reveals[participant] = event
                reveal_order.append(participant)
            except ProtocolError as exc:
                invalid.append({**event, "error": str(exc)})
        elif kind not in {"DISCUSSION", "FINAL"}:
            invalid.append({**event, "error": f"unknown protocol event kind: {kind!r}"})

    selected_joiners = [
        participant
        for participant in reveal_order
        if participant != meta["initiator"]
    ][: meta["expected_participants"] - 1]
    observers = [
        participant
        for participant in reveal_order
        if participant != meta["initiator"] and participant not in selected_joiners
    ]
    roster = [meta["initiator"], *selected_joiners]
    initial_complete = (
        len(roster) == meta["expected_participants"]
        and all(participant in reveals for participant in roster)
    )
    reveal_boundary = (
        max(reveals[participant]["index"] for participant in roster)
        if initial_complete
        else None
    )

    valid_discussion: list[dict[str, Any]] = []
    latest: dict[str, dict[str, Any]] = {}
    next_round = 1
    next_position = 0
    terminal_status: str | None = None
    terminal_reason: str | None = None
    terminal_index: int | None = None
    consensus_digest: str | None = None
    consensus_resolution: str | None = None

    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("kind") != "DISCUSSION":
            continue
        try:
            if not initial_complete or reveal_boundary is None or event["index"] <= reveal_boundary:
                raise ProtocolError("discussion started before all independent answers were revealed")
            if terminal_status:
                raise ProtocolError("discussion turn posted after the protocol had terminated")
            participant = validate_participant(
                require_string(payload.get("participant"), "participant")
            )
            validate_event_author(event, participant)
            if participant != roster[next_position]:
                raise ProtocolError(
                    f"out of turn: expected {roster[next_position]}, received {participant}"
                )
            if payload.get("round") != next_round:
                raise ProtocolError(
                    f"wrong round: expected {next_round}, received {payload.get('round')}"
                )
            if payload.get("task_hash") != meta["task_hash"]:
                raise ProtocolError("discussion turn uses a different task hash")
            answer = require_string(payload.get("answer"), "answer")
            agreements = require_string_list(payload.get("agreements"), "agreements")
            blockers = require_string_list(
                payload.get("blocking_disagreements"), "blocking_disagreements"
            )
            revisions = require_string_list(payload.get("revisions"), "revisions")
            proposal = require_string(payload.get("proposed_resolution"), "proposed_resolution")
            if payload.get("resolution_hash") != resolution_hash(proposal):
                raise ProtocolError("resolution hash does not match proposed_resolution")
            verdict = payload.get("verdict")
            if verdict not in {"CONTINUE", "ACCEPT"}:
                raise ProtocolError("verdict must be CONTINUE or ACCEPT")
            accepted = payload.get("accepted_resolution_hash")
            if verdict == "ACCEPT":
                if blockers:
                    raise ProtocolError("ACCEPT cannot contain blocking disagreements")
                if accepted != payload["resolution_hash"]:
                    raise ProtocolError("ACCEPT must accept the proposed resolution hash")
            elif accepted is not None:
                raise ProtocolError("CONTINUE must not accept a resolution hash")
            normalized = {
                **payload,
                "answer": answer,
                "agreements": agreements,
                "blocking_disagreements": blockers,
                "revisions": revisions,
                "proposed_resolution": proposal,
            }
            valid = {**event, "payload": normalized}
            valid_discussion.append(valid)
            latest[participant] = normalized
            consensus_digest, consensus_resolution = accepted_consensus(roster, latest)
            if consensus_digest:
                terminal_status = "CONSENSUS"
                terminal_reason = (
                    "Every participant's latest valid turn accepted the same resolution hash."
                )
                terminal_index = event["index"]
                continue
            if next_position == len(roster) - 1:
                if next_round == meta["max_rounds"]:
                    terminal_status = "LIMIT_REACHED"
                    terminal_reason = (
                        f"No unanimous resolution after {meta['max_rounds']} complete rounds."
                    )
                    terminal_index = event["index"]
                else:
                    next_round += 1
                    next_position = 0
            else:
                next_position += 1
        except ProtocolError as exc:
            invalid.append({**event, "error": str(exc)})

    final_event: dict[str, Any] | None = None
    if terminal_status:
        for event in events:
            payload = event.get("payload")
            if not isinstance(payload, dict) or payload.get("kind") != "FINAL":
                continue
            try:
                if payload.get("participant") != meta["initiator"]:
                    raise ProtocolError("only the initiator may publish the final summary")
                validate_event_author(event, meta["initiator"])
                if terminal_index is None or event["index"] <= terminal_index:
                    raise ProtocolError("final summary must be posted after protocol termination")
                require_string(payload.get("conclusion"), "conclusion")
                require_string(payload.get("discussion_summary"), "discussion_summary")
                require_string(payload.get("termination_reason"), "termination_reason")
                if payload.get("status") != terminal_status:
                    raise ProtocolError("final summary status does not match transcript status")
                if normalize_text(payload["termination_reason"]) != terminal_reason:
                    raise ProtocolError("final summary termination reason does not match transcript")
                if terminal_status == "CONSENSUS" and resolution_hash(
                    payload["conclusion"]
                ) != consensus_digest:
                    raise ProtocolError("final conclusion differs from the accepted resolution")
                final_event = event
                break
            except ProtocolError as exc:
                invalid.append({**event, "error": str(exc)})

    if terminal_status:
        phase = terminal_status
        expected_next = None
    elif not initial_complete:
        if len(selected_joiners) < meta["expected_participants"] - 1:
            phase = "WAITING_FOR_PARTICIPANTS"
        else:
            phase = "WAITING_FOR_INITIATOR_REVEAL"
        expected_next = meta["initiator"] if phase.endswith("REVEAL") else None
    else:
        phase = "DISCUSSION"
        expected_next = roster[next_position]

    initial_answers = {
        participant: reveals[participant]["payload"]["answer"]
        for participant in roster
        if participant in reveals
    }
    return {
        "phase": phase,
        "status": terminal_status,
        "termination_reason": terminal_reason,
        "task": meta["task"],
        "task_hash": meta["task_hash"],
        "initiator": meta["initiator"],
        "expected_participants": meta["expected_participants"],
        "max_rounds": meta["max_rounds"],
        "roster": roster,
        "committed_participants": sorted(commitments),
        "observers": observers,
        "initial_answers": initial_answers,
        "next_round": None if terminal_status else next_round,
        "expected_next_participant": expected_next,
        "valid_discussion": valid_discussion,
        "latest_positions": latest,
        "consensus_resolution_hash": consensus_digest,
        "consensus_resolution": consensus_resolution,
        "invalid_protocol_comments": invalid,
        "final_summary": final_event["payload"] if final_event else None,
    }


def render_issue(meta: dict[str, Any]) -> str:
    body = "\n".join(
        [
            "# Consensus Discussion",
            "",
            f"- Protocol: `{PROTOCOL}`",
            f"- Initiator: `{meta['initiator']}`",
            f"- Expected participants: {meta['expected_participants']}",
            f"- Maximum rounds: {meta['max_rounds']}",
            f"- Task hash: `{meta['task_hash']}`",
            f"- Initiator initial-answer commitment: `{meta['initiator_commitment']}`",
            "",
            "## Original task",
            "",
            meta["task"],
            "",
            "## Protocol",
            "",
            "Participants must independently lock their initial answer before reading Issue comments. "
            "Only then may they reveal it and enter the ordered discussion. Consensus requires every "
            "participant to accept the same resolution hash. Ordinary comments are not protocol turns.",
            "",
            encode_marker(meta),
        ]
    )
    ensure_body_size(body)
    return body


def bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def render_comment(payload: dict[str, Any]) -> str:
    kind = payload["kind"]
    participant = payload["participant"]
    if kind == "INITIAL_COMMIT":
        visible = "\n".join(
            [
                f"## Initial answer committed — `{participant}`",
                "",
                "The answer was locked before this participant read any Issue comments.",
                "",
                f"Commitment: `{payload['initial_hash']}`",
            ]
        )
    elif kind == "INITIAL_REVEAL":
        visible = "\n".join(
            [
                f"## Independent initial answer — `{participant}`",
                "",
                payload["answer"],
                "",
                f"Verified commitment: `{payload['initial_hash']}`",
            ]
        )
    elif kind == "DISCUSSION":
        visible = "\n".join(
            [
                f"## Discussion round {payload['round']} — `{participant}`",
                "",
                f"**Verdict:** {payload['verdict']}",
                "",
                "### Current answer",
                "",
                payload["answer"],
                "",
                "### Agreements",
                "",
                bullets(payload["agreements"]),
                "",
                "### Blocking disagreements",
                "",
                bullets(payload["blocking_disagreements"]),
                "",
                "### Revisions",
                "",
                bullets(payload["revisions"]),
                "",
                "### Proposed resolution",
                "",
                payload["proposed_resolution"],
                "",
                f"Resolution hash: `{payload['resolution_hash']}`",
            ]
        )
    elif kind == "FINAL":
        visible = "\n".join(
            [
                f"## Final summary — {payload['status']}",
                "",
                "### Conclusion",
                "",
                payload["conclusion"],
                "",
                "### Discussion summary",
                "",
                payload["discussion_summary"],
                "",
                "### Termination",
                "",
                payload["termination_reason"],
            ]
        )
    else:
        raise ProtocolError(f"Cannot render unknown event kind: {kind}")
    body = f"{visible}\n\n{encode_marker(payload)}"
    ensure_body_size(body)
    return body


def issue_and_meta(
    github: GitHub, reference: str, repo: str | None, *, comments: bool
) -> tuple[dict[str, Any], dict[str, Any], str, int]:
    issue = github.issue(reference, repo, include_comments=comments)
    meta = parse_issue(issue)
    issue_url = require_string(issue.get("url"), "issue URL")
    parsed_repo, parsed_number = parse_issue_identity(issue_url)
    return issue, meta, parsed_repo, parsed_number


def default_participant(github: GitHub) -> str:
    return validate_participant(f"{github.login()}/codex-desktop")


def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    github = GitHub()
    version = github.run(["--version"]).splitlines()[0]
    auth = github.run(["auth", "status"])
    repo = args.repo
    if args.check_repo and not repo:
        repo = github.repo()
    return {"ok": True, "gh_version": version, "auth_status": auth, "repo": repo}


def cmd_start(args: argparse.Namespace) -> dict[str, Any]:
    data = read_json_input()
    task = require_string(data.get("task"), "task")
    answer = require_string(data.get("initial_answer"), "initial_answer")
    github = GitHub()
    repo = args.repo or github.repo()
    participant = validate_participant(args.participant or default_participant(github))
    nonce = secrets.token_hex(32)
    digest = task_hash(task)
    commitment = initial_hash(digest, participant, nonce, answer)
    meta = {
        "protocol": PROTOCOL,
        "kind": "ISSUE",
        "created_at": utc_now(),
        "task": task,
        "task_hash": digest,
        "initiator": participant,
        "initiator_commitment": commitment,
        "expected_participants": args.expected_participants,
        "max_rounds": args.max_rounds,
    }
    title = args.title or f"[Consensus] {task.splitlines()[0][:80]}"
    issue_url = github.create_issue(repo, title, render_issue(meta))
    parsed_repo, issue_number = parse_issue_identity(issue_url)
    state = {
        "protocol": PROTOCOL,
        "repo": parsed_repo,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "participant": participant,
        "role": "initiator",
        "task_hash": digest,
        "initial_answer": answer,
        "nonce": nonce,
        "initial_hash": commitment,
        "created_at": utc_now(),
    }
    path = save_state(state)
    return {
        "status": "ISSUE_CREATED",
        "issue_url": issue_url,
        "repo": parsed_repo,
        "issue_number": issue_number,
        "participant": participant,
        "initial_commitment": commitment,
        "state_path": str(path),
        "next_action": "Ask other agents to join from the issue URL. The initial answer remains hidden until reveal.",
    }


def cmd_prepare_join(args: argparse.Namespace) -> dict[str, Any]:
    github = GitHub()
    issue, meta, repo, number = issue_and_meta(
        github, args.issue, args.repo, comments=False
    )
    if issue.get("state") != "OPEN":
        raise ProtocolError("The discussion issue is not open")
    return {
        "status": "READY_FOR_BLIND_ANSWER",
        "issue_url": issue["url"],
        "repo": repo,
        "issue_number": number,
        "task": meta["task"],
        "task_hash": meta["task_hash"],
        "initiator": meta["initiator"],
        "expected_participants": meta["expected_participants"],
        "max_rounds": meta["max_rounds"],
        "instruction": "Produce and lock a complete independent answer now. Do not read Issue comments before running join.",
    }


def cmd_join(args: argparse.Namespace) -> dict[str, Any]:
    data = read_json_input()
    answer = require_string(data.get("initial_answer"), "initial_answer")
    github = GitHub()
    issue, meta, repo, number = issue_and_meta(
        github, args.issue, args.repo, comments=False
    )
    if issue.get("state") != "OPEN":
        raise ProtocolError("The discussion issue is not open")
    participant = validate_participant(args.participant or default_participant(github))
    if participant == meta["initiator"]:
        raise ProtocolError("The initiator must use reveal, not join")
    path = state_path(repo, number, participant)
    is_retry = path.is_file()
    if is_retry:
        state, _ = load_state(repo, number, participant)
        if normalize_text(state.get("initial_answer", "")) != answer:
            raise ProtocolError("The initial answer is already locked locally and cannot be changed")
        nonce = state["nonce"]
        commitment = state["initial_hash"]
    else:
        nonce = secrets.token_hex(32)
        commitment = initial_hash(meta["task_hash"], participant, nonce, answer)
        state = {
            "protocol": PROTOCOL,
            "repo": repo,
            "issue_number": number,
            "issue_url": issue["url"],
            "participant": participant,
            "role": "participant",
            "task_hash": meta["task_hash"],
            "initial_answer": answer,
            "nonce": nonce,
            "initial_hash": commitment,
            "created_at": utc_now(),
        }
        save_state(state)

    commit_payload = {
        "protocol": PROTOCOL,
        "kind": "INITIAL_COMMIT",
        "created_at": utc_now(),
        "participant": participant,
        "task_hash": meta["task_hash"],
        "initial_hash": commitment,
    }
    if not is_retry:
        github.comment(args.issue, args.repo, render_comment(commit_payload))
        issue_with_comments = github.issue(args.issue, args.repo, include_comments=True)
    else:
        issue_with_comments = github.issue(args.issue, args.repo, include_comments=True)
        if not has_initial_event(
            issue_with_comments,
            kind="INITIAL_COMMIT",
            participant=participant,
            commitment=commitment,
        ):
            github.comment(args.issue, args.repo, render_comment(commit_payload))
            issue_with_comments = github.issue(args.issue, args.repo, include_comments=True)
    existing = audit(issue_with_comments)
    already_revealed = has_initial_event(
        issue_with_comments,
        kind="INITIAL_REVEAL",
        participant=participant,
        commitment=commitment,
    )
    if not already_revealed:
        reveal_payload = {
            "protocol": PROTOCOL,
            "kind": "INITIAL_REVEAL",
            "created_at": utc_now(),
            "participant": participant,
            "task_hash": meta["task_hash"],
            "initial_hash": commitment,
            "nonce": nonce,
            "answer": answer,
        }
        github.comment(args.issue, args.repo, render_comment(reveal_payload))

    refreshed = github.issue(args.issue, args.repo, include_comments=True)
    status = audit(refreshed)
    selected = participant in status["roster"]
    return {
        "status": "INITIAL_ANSWER_PUBLISHED" if selected else "OBSERVER_NOT_SELECTED",
        "issue_url": refreshed["url"],
        "participant": participant,
        "selected_for_roster": selected,
        "phase": status["phase"],
        "roster": status["roster"],
        "state_path": str(path),
        "next_action": (
            "Wait for the initiator to reveal, then continue when it is your turn."
            if selected
            else "The configured roster was already full; your answer remains recorded as an observer contribution."
        ),
    }


def load_issue_state(
    github: GitHub, args: argparse.Namespace, *, comments: bool
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, str, int]:
    issue, meta, repo, number = issue_and_meta(
        github, args.issue, args.repo, comments=comments
    )
    state, path = load_state(repo, number, getattr(args, "participant", None))
    if state.get("task_hash") != meta["task_hash"]:
        raise ProtocolError("Local state belongs to a different task")
    return issue, meta, state, path, repo, number


def cmd_reveal(args: argparse.Namespace) -> dict[str, Any]:
    github = GitHub()
    issue, meta, state, path, _repo, _number = load_issue_state(
        github, args, comments=True
    )
    participant = state["participant"]
    if participant != meta["initiator"] or state.get("role") != "initiator":
        raise ProtocolError("Only the initiating agent can reveal this committed answer")
    status = audit(issue)
    if participant in status["initial_answers"]:
        return {
            "status": "ALREADY_REVEALED",
            "issue_url": issue["url"],
            "phase": status["phase"],
            "state_path": str(path),
        }
    if len(status["roster"]) < meta["expected_participants"]:
        raise ProtocolError("Wait until the configured number of participants has published initial answers")
    payload = {
        "protocol": PROTOCOL,
        "kind": "INITIAL_REVEAL",
        "created_at": utc_now(),
        "participant": participant,
        "task_hash": meta["task_hash"],
        "initial_hash": state["initial_hash"],
        "nonce": state["nonce"],
        "answer": state["initial_answer"],
    }
    github.comment(args.issue, args.repo, render_comment(payload))
    refreshed = github.issue(args.issue, args.repo, include_comments=True)
    refreshed_status = audit(refreshed)
    return {
        "status": "INITIAL_ANSWER_REVEALED",
        "issue_url": refreshed["url"],
        "phase": refreshed_status["phase"],
        "roster": refreshed_status["roster"],
        "expected_next_participant": refreshed_status["expected_next_participant"],
        "state_path": str(path),
    }


def public_status(issue: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_url": issue["url"],
        "issue_title": issue["title"],
        **result,
    }


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    github = GitHub()
    issue, _meta, _repo, _number = issue_and_meta(
        github, args.issue, args.repo, comments=True
    )
    return public_status(issue, audit(issue))


def cmd_post_turn(args: argparse.Namespace) -> dict[str, Any]:
    data = read_json_input()
    github = GitHub()
    issue, meta, state, _path, _repo, _number = load_issue_state(
        github, args, comments=True
    )
    status = audit(issue)
    participant = state["participant"]
    if status["phase"] != "DISCUSSION":
        raise ProtocolError(f"Cannot post a turn while phase is {status['phase']}")
    if status["expected_next_participant"] != participant:
        raise ProtocolError(
            f"It is {status['expected_next_participant']}'s turn, not {participant}'s"
        )
    answer = require_string(data.get("answer"), "answer")
    agreements = require_string_list(data.get("agreements", []), "agreements")
    blockers = require_string_list(
        data.get("blocking_disagreements", []), "blocking_disagreements"
    )
    revisions = require_string_list(data.get("revisions", []), "revisions")
    proposal = require_string(data.get("proposed_resolution"), "proposed_resolution")
    verdict = data.get("verdict")
    if verdict not in {"CONTINUE", "ACCEPT"}:
        raise ProtocolError("verdict must be CONTINUE or ACCEPT")
    digest = resolution_hash(proposal)
    if verdict == "ACCEPT" and blockers:
        raise ProtocolError("ACCEPT cannot contain blocking disagreements")
    payload = {
        "protocol": PROTOCOL,
        "kind": "DISCUSSION",
        "created_at": utc_now(),
        "participant": participant,
        "task_hash": meta["task_hash"],
        "round": status["next_round"],
        "answer": answer,
        "agreements": agreements,
        "blocking_disagreements": blockers,
        "revisions": revisions,
        "proposed_resolution": proposal,
        "resolution_hash": digest,
        "accepted_resolution_hash": digest if verdict == "ACCEPT" else None,
        "verdict": verdict,
    }
    github.comment(args.issue, args.repo, render_comment(payload))
    refreshed = github.issue(args.issue, args.repo, include_comments=True)
    return public_status(refreshed, audit(refreshed))


def cmd_finalize(args: argparse.Namespace) -> dict[str, Any]:
    data = read_json_input()
    github = GitHub()
    issue, meta, state, _path, _repo, _number = load_issue_state(
        github, args, comments=True
    )
    status = audit(issue)
    if state["participant"] != meta["initiator"]:
        raise ProtocolError("Only the initiator may publish the final summary")
    if status["status"] not in {"CONSENSUS", "LIMIT_REACHED"}:
        raise ProtocolError("Discussion has not reached a terminal state")
    if status["final_summary"]:
        return public_status(issue, status)
    conclusion = require_string(data.get("conclusion"), "conclusion")
    summary = require_string(data.get("discussion_summary"), "discussion_summary")
    reason = require_string(data.get("termination_reason"), "termination_reason")
    if normalize_text(reason) != normalize_text(status["termination_reason"]):
        raise ProtocolError(
            "termination_reason must exactly match the canonical audited termination reason"
        )
    if status["status"] == "CONSENSUS" and resolution_hash(conclusion) != status["consensus_resolution_hash"]:
        raise ProtocolError(
            "For consensus, conclusion must exactly match the unanimously accepted proposed_resolution"
        )
    payload = {
        "protocol": PROTOCOL,
        "kind": "FINAL",
        "created_at": utc_now(),
        "participant": state["participant"],
        "status": status["status"],
        "conclusion": conclusion,
        "discussion_summary": summary,
        "termination_reason": reason,
    }
    github.comment(args.issue, args.repo, render_comment(payload))
    refreshed = github.issue(args.issue, args.repo, include_comments=True)
    return public_status(refreshed, audit(refreshed))


def add_issue_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("issue", help="GitHub Issue URL or number")
    parser.add_argument("--repo", help="[HOST/]OWNER/REPO; optional for an Issue URL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the GitHub Issue transport for multi-agent consensus discussions."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check gh discovery and authentication")
    doctor.add_argument("--repo")
    doctor.add_argument("--check-repo", action="store_true")
    doctor.set_defaults(handler=cmd_doctor)

    start = subparsers.add_parser("start", help="Commit an independent answer and create an Issue")
    start.add_argument("--repo", help="[HOST/]OWNER/REPO; defaults to the current repository")
    start.add_argument("--participant")
    start.add_argument("--expected-participants", type=int, default=DEFAULT_EXPECTED_PARTICIPANTS)
    start.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    start.add_argument("--title")
    start.set_defaults(handler=cmd_start)

    prepare = subparsers.add_parser(
        "prepare-join", help="Read only the Issue body before independent answering"
    )
    add_issue_args(prepare)
    prepare.set_defaults(handler=cmd_prepare_join)

    join = subparsers.add_parser(
        "join", help="Lock, commit, and reveal an independent answer before discussion"
    )
    add_issue_args(join)
    join.add_argument("--participant")
    join.set_defaults(handler=cmd_join)

    reveal = subparsers.add_parser("reveal", help="Reveal the initiator's committed answer")
    add_issue_args(reveal)
    reveal.add_argument("--participant")
    reveal.set_defaults(handler=cmd_reveal)

    status = subparsers.add_parser("status", help="Read and audit the full protocol transcript")
    add_issue_args(status)
    status.set_defaults(handler=cmd_status)

    post_turn = subparsers.add_parser("post-turn", help="Post the next ordered discussion turn")
    add_issue_args(post_turn)
    post_turn.add_argument("--participant")
    post_turn.set_defaults(handler=cmd_post_turn)

    finalize = subparsers.add_parser("finalize", help="Publish the initiator's terminal summary")
    add_issue_args(finalize)
    finalize.add_argument("--participant")
    finalize.set_defaults(handler=cmd_finalize)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "expected_participants", 2) not in range(2, 9):
        raise ProtocolError("--expected-participants must be between 2 and 8")
    if getattr(args, "max_rounds", 10) not in range(1, 11):
        raise ProtocolError("--max-rounds must be between 1 and 10")
    result = args.handler(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProtocolError as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
