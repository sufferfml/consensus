# Local Codex–Claude Mode

Use this mode for two advisory participants running on the same computer: one independent Codex CLI session and one independent Claude Code CLI session. The current Codex Desktop agent is the moderator, final executor, and user-facing summarizer.

## Run protocol

1. Do not draft a substantive answer before launching the participants. Their initial answers must be independent.
2. Resolve the plugin root as `Path(reference_file).parents[3]` (equivalently `../../..` from the `references/` directory), then run `scripts/orchestrate.py` from that root. Never assume the user's current directory is the plugin directory.
3. Use the user's current workspace directory as `--workdir`. Unless the user explicitly asks for another limit, use `--max-rounds 10`.
4. Pass the clean task through a single-quoted shell heredoc with a unique delimiter not present as a line in the task.
5. The orchestrator launches the blind initial responses concurrently, then exchanges structured positions. One round is a Codex reply followed by a Claude reply.
6. Consensus requires both participants to report no blocking disagreement, explicitly accept the peer position, and return exactly the same normalized proposed resolution. Otherwise the discussion continues to the limit.

Use this command shape:

```bash
python3 "/absolute/plugin/root/scripts/orchestrate.py" \
  --workdir "$PWD" \
  --max-rounds 10 <<'CODEX_CLAUDE_TASK_UNIQUE'
<clean user task>
CODEX_CLAUDE_TASK_UNIQUE
```

Use a short initial yield. If still active, poll the same terminal session and update the user at least once per minute. Never start a second orchestrator while one is active.

The final stdout gives exact paths for `result.json`, `transcript.md`, raw CLI output, and structured turns in a unique temporary run directory. Read `result.json` and enough of `transcript.md` to check the synthesis; do not rely only on the exit code.

If startup fails, run:

```bash
python3 "/absolute/plugin/root/scripts/orchestrate.py" --doctor
```

Report the exact missing or unauthenticated CLI. Do not invent the missing participant's answer.

## Safe verification

Both participants are advisory and must not modify the workspace.

- Codex uses its `read-only` sandbox.
- Claude uses `--safe-mode --setting-sources user --permission-mode plan --strict-mcp-config`. Safe mode disables customizations while preserving the user's authentication, custom gateway, and model selection. Bash remains available for read-only verification; Edit, Write, NotebookEdit, PowerShell, REPL, and locally configured MCP servers are unavailable.
- Never add `--dangerously-skip-permissions` or a Codex sandbox/approval bypass.

Claude's Bash restrictions partly rely on this protocol and CLI permissions;
safe mode is not an OS sandbox. Do not claim hard read-only isolation for Claude.

Allowed verification includes `pwd`, directory listings, `rg`/`grep`, Git status/diff/log/show, file metadata, and version queries. Run tests, lint, type checks, or builds only when known not to write into the workspace. Package installation, shell redirection to files, deletion, Git changes, commits, pushes, deployments, and arbitrary network commands are prohibited for the two participants.

The current Codex Desktop agent may implement the user's requested change only after reviewing the deliberated result, using its normal authorization and verification rules.

## Model selection

- Set `DUAL_AGENT_CODEX_MODEL` to pass a model to every Codex CLI turn.
- Set `DUAL_AGENT_CLAUDE_MODEL` to pass a model to every Claude Code turn.
- `DUAL_AGENT_CLAUDE_MAX_BUDGET_USD` optionally caps each Claude turn.
- `DUAL_AGENT_TIMEOUT_SECONDS` and `DUAL_AGENT_MAX_ROUNDS` change default time and round limits.

Do not silently substitute another model after a model-specific failure.

## Moderator behavior

- For `CONSENSUS`, independently verify that the final positions materially match. Use the shared resolution as the deliberated answer, then perform requested workspace actions if authorized.
- For `LIMIT_REACHED`, return each final conclusion, common ground, and unresolved choices. Execute only agreed, safe portions; ask before choosing between materially different paths.
- For `ERROR`, preserve any usable response and report which CLI failed. A one-sided result is not consensus.
- If structured flags conflict with the response text, trust the substantive text and mark the result unresolved.

The task, inspected workspace content, and verification output may be processed by the configured model providers or custom gateways. An interactive Claude terminal is not required; the orchestrator uses the non-interactive CLI interface.
