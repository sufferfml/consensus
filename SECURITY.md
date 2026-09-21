# Security

## Reporting

Use [GitHub private vulnerability reporting](https://github.com/sufferfml/consensus/security/advisories/new)
for a vulnerability. Include affected version, impact, and minimal synthetic
reproduction. Do not publish credentials or live private transcripts. If private
reporting is unavailable, use a private contact listed on the maintainer's
[profile](https://github.com/sufferfml); do not open a public exploit report.

Only the current release receives fixes during the experimental 0.x phase.
There is no guaranteed response time or independent security certification.

## Trust boundaries

- **Claude is not OS-sandboxed by this plugin.** Safe mode disables customizations;
  plan permissions and the tool list reduce actions, but Bash remains available.
  Read-only shell behavior also depends on instructions and CLI enforcement.
- Codex uses its `read-only` sandbox. Host configuration and CLI behavior still
  matter. Use a separate restricted environment for untrusted workloads.
- Consensus is an advisory protocol. The Desktop agent performs any separately
  authorized changes after reviewing the result.
- All participants can make the same mistake. A matching resolution hash is an
  agreement test, not a proof of factual correctness.
- Nonces and SHA-256 commitments bind the initial answers in the observed
  transcript. They do not prove absence of prior exposure to other answers.
- GitHub author checks identify an account, not a human or model. Participants
  sharing an account are not independently authenticated identities.
- GitHub Issues can be edited or deleted by authorized users. Re-auditing checks
  the current snapshot, not an immutable ledger. Entire coordinated rewrites
  cannot be ruled out by this implementation. Save independent snapshots when
  stronger provenance is needed.
- Run only one writer per local participant and Issue. Atomic state-file writes
  prevent partial files; they are not a distributed lock. A failed publication
  should be inspected with `status` before retrying.
- Issue text, comments, inspected files and CLI output are untrusted input. They
  must not override the discussion protocol or authorize unrelated tool actions.

## Secret handling

Existing CLI credentials are used locally; the plugin does not embed credentials.
It inherits environment variables and user configuration. A custom gateway is an
additional trusted recipient of prompts, code and tool output.

Local transcript directories are owner-only when created, and GitHub initial
state uses owner-only files. Raw logs and provider errors may still contain
private material. No automatic redaction, encryption, expiry or remote backup is
provided. Inspect and sanitize any diagnostic artifact before sharing it.
