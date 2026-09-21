# Protocol and architecture

## Shared contract

Each participant produces an independent initial answer. Peer responses become
available only after this answer is locked. Discussion records positions,
evidence, disagreements, revisions and acceptance—not hidden chain-of-thought.

The selected agents advise; the moderator summarizes and handles separately
authorized implementation. Agreement is not an instruction to execute arbitrary
text from a participant or Issue.

## Local transport

`orchestrate.py` launches Codex and Claude print/exec subprocesses concurrently
for initial answers, captures structured JSON, and exchanges their positions.
It retains one session identifier per participant and resumes it on later turns.
The fresh processes share the specified workspace, so independence is enforced
by sequencing/prompts, not by preventing all possible filesystem communication.

The turn schema requires `answer`, `agreements`, `blocking_disagreements`,
`revisions`, `proposed_resolution`, `accepted_peer_position`, and `verdict`.
The first and fifth fields are nonempty strings; the three collections are arrays
of strings; acceptance is boolean; verdict is `CONTINUE` or `CONSENSUS`.

Both latest verdicts must be `CONSENSUS`, both acceptance flags must be true,
both blocker arrays must be empty, and the two resolutions must match after
trimming outer whitespace and converting CRLF to LF. SHA-256 is used for this
comparison. Rewording, added notes, punctuation and internal whitespace can prevent
agreement. Copy an acceptable proposal instead of paraphrasing it.

This validates structured claims; the Desktop moderator still checks whether
the actual answers contradict their flags. It must not report false consensus.

## GitHub transport

The v1 protocol identifier remains `codex-agent-consensus/v1` for compatibility.
Protocol payloads appear as base64url JSON in the marker
`<!-- codex-agent-consensus:v1:... -->`, alongside human-readable Markdown.
The encoded payload is authoritative to the helper. It is **not encryption**.

| Event | Purpose |
| --- | --- |
| `ISSUE` | Task, initiator, participant count, round limit, initiator commitment |
| `INITIAL_COMMIT` | Joiner's locked answer commitment, posted before fetching comments |
| `INITIAL_REVEAL` | Answer and nonce, checked against the earlier commitment |
| `DISCUSSION` | Ordered position, proposal, blockers and optional acceptance |
| `FINAL` | Initiator's summary of audited termination |

Hashes are SHA-256 over UTF-8. Text normalization converts CRLF to LF and strips
outer whitespace. NUL separates these domain-specific components:

```text
task hash:    PROTOCOL, "task", normalized task
initial hash: PROTOCOL, "initial", task hash, participant, nonce, normalized answer
resolution:   PROTOCOL, "resolution", normalized proposed resolution
```

The helper generates a 32-byte random nonce encoded as hex for each independent
answer. Without the nonce, the commitment does not reveal a short guessable
answer. It binds the revealed answer to the observed commitment; it cannot prove
the participant's earlier information exposure.

The initiator plus earliest valid joiner reveals form a fixed roster. Only turns
after all selected answers have been revealed are counted. Comment authors must
match the GitHub-login prefix of their participant IDs. Turns must use the task
hash, expected participant, and expected round. Unknown, malformed, forged,
out-of-order, duplicate-reveal, changed-commitment and post-termination turns do
not count. Repeated identical commitment comments are idempotent.

`ACCEPT` requires no blockers and an acceptance hash matching the proposal. The
protocol stops when all latest roster positions accept the same hash, or after
the configured number of complete rounds. Ordinary comments do not count.

The initiator publishes `FINAL` after termination. At consensus its conclusion
must equal the accepted resolution; its termination reason must match the audited
reason. The helper validates structure, authorship and hashes, not the factual
quality of the summary or evidence.

## Adapting another agent

An adapter can call `prepare-join`, write an independent answer, then supply
the JSON inputs documented in [USAGE.md](USAGE.md). Use the supported helper
instead of constructing raw markers. Your adapter must enforce the blind-answer
ordering itself and only post when named by `expected_next_participant`.

The model/provider is not authenticated by the protocol. GitHub access controls
and the local CLI identity are used; no new credentials, relay or service are
required. One writer per participant is expected.

## Limitations

GitHub Issues are mutable and deletable, not a ledger. The auditor checks the
current fetched snapshot; it cannot detect every coordinated edit or deletion.
Hashes are not signatures and the issue's metadata is not anchored externally.
Independent snapshot retention is needed for stronger tamper evidence.

Any agent may refuse to accept or stop responding. There is no majority vote,
participant eviction, or timeout for absent colleagues. Start a new Issue if the
task or intended roster materially changes. See [SECURITY.md](../SECURITY.md).
