# Consensus

This is the installable plugin bundle. See the
[project documentation](https://github.com/sufferfml/consensus) for installation,
the bilingual introduction, contribution guidelines and security limitations.

A Codex Desktop plugin for independent answers followed by structured debate. It supports two modes:

- **Local dual-agent mode:** Codex CLI and Claude Code CLI run independently on the same computer, cross-review one another, and discuss for up to ten rounds.
- **GitHub multi-agent mode:** Codex Desktop agents on different computers use one GitHub Issue as an asynchronous mailbox and auditable transcript.

## Local mode

The local orchestrator starts blind Codex and Claude answers concurrently. Both participants are instructed to perform only safe verification: Codex has a read-only sandbox; Claude uses `--safe-mode --setting-sources user --permission-mode plan --strict-mcp-config`, with Bash limited by the protocol to read-only queries. Safe mode disables Claude customizations while still loading the user's authentication and model selection, including a configured `ANTHROPIC_BASE_URL` gateway. Claude's Bash policy is not an OS-enforced sandbox. The current Codex Desktop agent reviews the result and performs any requested implementation afterward.

Consensus requires bilateral acceptance, no blocking disagreement, and the same normalized proposed resolution. A permission-bypass flag is never used.

Requirements:

- `codex` on `PATH` and logged in
- `claude` on `PATH` and authenticated
- Python 3.10+

Diagnostic:

```bash
python3 scripts/orchestrate.py --doctor
```

Direct use:

```bash
python3 scripts/orchestrate.py --workdir "$PWD" --max-rounds 10 <<'TASK'
Your task here.
TASK
```

Model and run settings:

- `DUAL_AGENT_CODEX_MODEL`
- `DUAL_AGENT_CLAUDE_MODEL`
- `DUAL_AGENT_CLAUDE_MAX_BUDGET_USD`
- `DUAL_AGENT_TIMEOUT_SECONDS`
- `DUAL_AGENT_MAX_ROUNDS`

Claude gateway configuration may be placed in `~/.claude/settings.json` using `ANTHROPIC_BASE_URL` plus the authentication variable required by the gateway. The user's configured Claude model is used automatically; `DUAL_AGENT_CLAUDE_MODEL` remains an explicit per-plugin override.

Each run saves `result.json`, `transcript.md`, raw output, and structured turns in a unique temporary directory.

## GitHub mode

GitHub mode does not need a relay service, webhook, GitHub App, or plugin-owned credentials. It uses the local user's existing `gh` login and repository permissions.

The protocol has four stages:

1. The initiator independently answers and creates an Issue containing the task and a cryptographic commitment—not the answer.
2. Each joining agent reads only the Issue body, locks and commits its independent answer, and only then reads comments and reveals the answer.
3. The selected roster discusses in fixed order. The helper posts new comments and checks hashes against the currently fetched transcript; GitHub itself does not enforce immutability.
4. The initiator publishes the final summary after every participant accepts the same resolution hash, or after ten complete rounds without consensus.

Commands:

```bash
python3 scripts/github_discussion.py doctor --check-repo
python3 scripts/github_discussion.py start --repo OWNER/REPO
python3 scripts/github_discussion.py prepare-join ISSUE_URL
python3 scripts/github_discussion.py join ISSUE_URL
python3 scripts/github_discussion.py reveal ISSUE_URL
python3 scripts/github_discussion.py status ISSUE_URL
python3 scripts/github_discussion.py post-turn ISSUE_URL
python3 scripts/github_discussion.py finalize ISSUE_URL
```

Commands that create answers or summaries accept one JSON object on standard input. Codex Desktop handles that automatically when the plugin is invoked. Private local state is stored under `~/.codex/github-agent-consensus/` with user-only permissions.

The default roster is two agents; the initiator can configure 2–8. The round limit is 1–10 and defaults to ten. Ordinary comments and invalid, duplicate, forged, changed, or out-of-order protocol messages do not count.

This plugin does not poll GitHub. People can invoke “continue discussion” manually or configure their own Codex scheduled task.

## Data boundary

Local mode may send the task and inspected workspace content to the configured model providers or custom gateways. GitHub mode publishes the task, answers, and discussion to everyone with access to the selected repository. Logs are not automatically redacted. Do not use either mode with secrets or data outside the intended sharing boundary. Consensus checks agreement, not factual correctness.
