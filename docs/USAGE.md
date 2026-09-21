# Usage guide

## Install and select the plugin

From a terminal with Codex plugin support:

```bash
codex plugin marketplace add sufferfml/consensus
codex plugin add consensus@consensus
```

Open a new Codex Desktop task and select **consensus** in the plugin picker.
The skill is named `consensus:dual-agent-consensus`; it supports both local and
GitHub mode despite the retained skill-directory name.

The following Python examples run from a clone of this repository. When working
in another project, use the absolute path to the script in your clone or installed
plugin and pass that project's path as `--workdir`.

## Local Codex + Claude

Both CLIs must be discoverable on `PATH` and authenticated with the intended
providers. No interactive Claude terminal is required; each turn runs a print
command, resuming the same participant session after the initial answer.

```bash
python3 plugins/consensus/scripts/orchestrate.py \
  --workdir "$PWD" --max-rounds 10 <<'CONSENSUS_TASK'
Compare the two deployment plans in this project. Answer independently, then
cross-review. Return a recommended plan, evidence and unresolved tradeoffs.
CONSENSUS_TASK
```

The initial answers run concurrently without peer answers in their prompts.
Then each round consists of a Codex turn followed by a Claude turn. The Desktop
agent is the moderator and user-facing summarizer. The standalone Python helper
returns structured results and a transcript, not an additional model-written
summary or implementation.

| Output | Meaning |
| --- | --- |
| `CONSENSUS` | Both explicitly accept the same normalized resolution with no blockers |
| `LIMIT_REACHED` | Limit reached without exact agreement; inspect both final positions |
| `ERROR` | A participant failed; any successfully captured answer is retained |

The orchestrator exits 0 for both consensus and round-limit termination, and 1
for orchestration errors. Always inspect `status`, not just the shell exit code.
Each turn has a default 600-second timeout; this is not a whole-run timeout.
The default round limit is 10; the local CLI accepts explicit limits from 1–50.
GitHub mode accepts 1–10 rounds.

### Models and executable selection

| Environment variable | Effect |
| --- | --- |
| `DUAL_AGENT_CODEX_MODEL` | Pass `--model` to Codex |
| `DUAL_AGENT_CLAUDE_MODEL` | Pass `--model` to Claude; overrides user's default model |
| `DUAL_AGENT_CODEX_BIN` | Path or command name for Codex |
| `DUAL_AGENT_CLAUDE_BIN` | Path or command name for Claude |
| `DUAL_AGENT_CLAUDE_MAX_BUDGET_USD` | Optional Claude budget **per turn**, not for the whole debate |
| `DUAL_AGENT_TIMEOUT_SECONDS` | Default timeout per participant turn |
| `DUAL_AGENT_MAX_ROUNDS` | Default local discussion-round limit |

Flags override timeout and round-count defaults. These legacy variable names are
intentional compatibility interfaces; renaming the plugin does not rename them.
Choose model identifiers available to your account/gateway. Consensus does not
silently substitute a different model when one fails.

Environment variables must be visible to the process that launches the helper.
An `export` in an unrelated terminal generally does not configure a Desktop app
already running or launched from the Dock.

### Claude custom gateways

Consensus reads Claude's **user** settings via
`--safe-mode --setting-sources user`. Put your gateway and model in your existing
`~/.claude/settings.json`; do not place that file in this repository. For example:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://gateway.example.com",
    "ANTHROPIC_AUTH_TOKEN": "REPLACE_LOCALLY"
  },
  "model": "YOUR_GATEWAY_MODEL"
}
```

This is a fragment to merge with your settings, not a reason to overwrite the
whole file. `ANTHROPIC_AUTH_TOKEN` is for Bearer authentication. If your gateway
requires `x-api-key`, use `ANTHROPIC_API_KEY` instead. Configure the model name
recognized by the gateway; endpoint selection does not itself map model names.
See Claude's [gateway documentation](https://code.claude.com/docs/en/llm-gateway).

The plugin intentionally avoids `--restricted`, which ignores ordinary user
settings, and never supplies a permission-bypass flag. Safe mode retains
authentication/model selection while disabling customizations. The available
tools are `Read,Glob,Grep,Bash,WebFetch,WebSearch`; read-only Bash usage is also a
protocol instruction. See [security limitations](../SECURITY.md).

### Records and failures

The final JSON includes `run_dir` and `transcript_path`. The directory contains
`task.txt`, schema, structured turns, raw CLI output and `result.json`.
By default it is under the operating system's temporary directory. Use
`--output-root /your/private/directory` for records you want to retain.
The underlying CLIs can also persist their own session records.

Successful CLI invocations are logged before structured output parsing. A
subprocess timeout or nonzero exit does not currently preserve its full partial
output in the transcript. Failures during a discussion stop the run; the helper
has no automatic whole-debate checkpoint/resume command. Do not invent the
missing participant's position.

If both participants agree but their `proposed_resolution` strings differ, the
result is not strict consensus. On acceptance they should copy the proposed
resolution exactly and put notes elsewhere. The moderator must not silently
change the recorded result to consensus.

## GitHub multi-agent mode

Use a repository where participants already have permission to create or comment
on Issues. Each machine uses its own `gh` login. Agents can be backed by different
providers as long as they obey the protocol and use the helper's JSON schema.
There is no generic autonomous-agent server or authentication service.

### 1. Initiator: independent answer and Issue

Prepare your independent answer before reading any peer responses, then run:

```bash
python3 plugins/consensus/scripts/github_discussion.py start \
  --repo OWNER/REPO --expected-participants 2 --max-rounds 10 <<'START_JSON'
{
  "task": "Should the first release use a staged rollout?",
  "initial_answer": "Yes: start with a small cohort and retain a rollback path."
}
START_JSON
```

Save the returned Issue URL. The Issue contains the task and an answer commitment;
the answer and nonce remain in private local state until reveal.

### 2. Joiner: read only the task, then lock an answer

```bash
python3 plugins/consensus/scripts/github_discussion.py prepare-join ISSUE_URL
```

Do not open comments or call `status` yet. Write an independent answer from the
task alone and submit it:

```bash
python3 plugins/consensus/scripts/github_discussion.py join ISSUE_URL <<'JOIN_JSON'
{"initial_answer": "Begin with shadow traffic, then a small reversible rollout."}
JOIN_JSON
```

The helper locks the answer, posts a commitment, then reads comments and reveals
the answer. A retry must reuse the same locked answer. The earliest valid joiner
reveals fill the roster; additional joiners are observers, not voters.

By default a participant ID is `GITHUB_LOGIN/codex-desktop`. Use an explicit
`--participant GITHUB_LOGIN/agent-name` for another adapter or multiple agents
sharing an account. The prefix must match the actual comment author's login.
Use the same ID for subsequent stateful commands. Sharing a GitHub account does
not establish independent identities.

### 3. Reveal, inspect status, and discuss in order

Once enough joiners have revealed, the initiator runs:

```bash
python3 plugins/consensus/scripts/github_discussion.py reveal ISSUE_URL
python3 plugins/consensus/scripts/github_discussion.py status ISSUE_URL
```

Only `expected_next_participant` may post a discussion turn:

```bash
python3 plugins/consensus/scripts/github_discussion.py post-turn ISSUE_URL <<'TURN_JSON'
{
  "answer": "Use shadow traffic, followed by a small reversible rollout.",
  "agreements": ["Retain rollback and limit initial exposure."],
  "blocking_disagreements": [],
  "revisions": ["Added a shadow-traffic phase."],
  "proposed_resolution": "Use shadow traffic, followed by a small reversible rollout.",
  "verdict": "ACCEPT"
}
TURN_JSON
```

Choose `CONTINUE` if disagreement remains. To accept a peer proposal, copy its
`proposed_resolution` exactly. The helper calculates hashes; do not manufacture
them manually. A round consists of one turn per selected participant in order.
The protocol can terminate as soon as all latest valid positions accept the same
resolution, including part-way through a later round.

### 4. Initiator: final summary

After `status` returns `CONSENSUS` or `LIMIT_REACHED`, the initiator sends:

```bash
python3 plugins/consensus/scripts/github_discussion.py finalize ISSUE_URL <<'FINAL_JSON'
{
  "conclusion": "Use shadow traffic, followed by a small reversible rollout.",
  "discussion_summary": "The initiator added the joiner's shadow phase; both accepted a reversible rollout.",
  "termination_reason": "Every participant's latest valid turn accepted the same resolution hash."
}
FINAL_JSON
```

Copy `termination_reason` from actual status. On consensus, `conclusion` must
match the accepted resolution; at the round limit, state each side's conclusion
and unresolved decisions. The helper does not automatically close the Issue.

### State, retries, scheduling

Private state is stored in `~/.codex/github-agent-consensus/`. The directory and
wire protocol names are retained from Discuss. `GITHUB_CONSENSUS_STATE_DIR`
selects a separate state directory and `GITHUB_CONSENSUS_GH_BIN` selects `gh`.
Do not delete state while a commitment still needs to be revealed.

Use `status` before retrying a request with an uncertain network outcome. Do not
run concurrent writers for the same participant. In particular, retrying `start`
can create another Issue; it has no idempotency key. If local storage fails after
Issue creation, the unrevealable discussion needs a new start.

Waiting for a colleague does not consume discussion rounds. There is no built-in
participant deadline or background poller. People can invoke "continue" or set
their own Codex scheduled task. GitHub Enterprise and adversarial multi-tenant
deployments are not currently verified.

## Updating and migrating

To update the registered Git marketplace, inspect available commands with
`codex plugin marketplace --help`, upgrade that marketplace, and reinstall
`consensus@consensus`. Open a new Desktop task to load the new skill instructions.

To migrate from Discuss, install Consensus first, then:

```bash
codex plugin remove discuss@personal
```

This removes the old installed plugin/cache, not its source folder or saved
discussion state. Existing tasks may still contain old skill paths; use a new
task. Legacy `DUAL_AGENT_*`, `GITHUB_CONSENSUS_*`, skill directory and protocol
markers remain supported.

To switch between a local checkout and Git as the marketplace source, inspect
`codex plugin marketplace list`, remove only the `consensus` marketplace using
the CLI, then add the intended source and reinstall. Do not manually edit Codex
configuration or remove unrelated marketplaces.
