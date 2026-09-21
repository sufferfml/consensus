# GitHub Multi-Agent Mode

Use GitHub Issues as an asynchronous shared mailbox and transcript for agents running in different Codex Desktop apps. There is no relay server, webhook, polling loop, GitHub App, or plugin-managed permission system. The helper uses the local user's existing `gh` authentication and repository access.

The current Codex Desktop agent is a discussion participant. The initiator also becomes the final moderator. A single invocation publishes at most one discussion turn, so a person or their separately configured Codex automation decides when to check again.

## Resolve the helper

Resolve the plugin root as `Path(reference_file).parents[3]` (equivalently `../../..` from the `references/` directory). The helper is:

```text
<plugin-root>/scripts/github_discussion.py
```

It stores one private local state file per Issue and participant under `~/.codex/github-agent-consensus/`. The initiator's initial answer and nonce stay there until reveal. Set `GITHUB_CONSENSUS_STATE_DIR` only for deliberate isolation or testing.

Use `python3 .../github_discussion.py doctor --check-repo` when setup or authentication needs diagnosis. GitHub permissions remain the user's responsibility; do not change scopes or repository settings unless explicitly asked.

## Phase A — start a discussion

Trigger examples include “发起 GitHub 讨论” or “create an agent discussion issue.”

1. Extract the full task and produce a complete independent answer before creating or reading any discussion Issue.
2. Do not publish the answer in the Issue body. Feed the task and finished answer to `start`; it stores the answer locally, creates a cryptographic commitment, and puts only the commitment plus task in the new Issue.
3. Default to two expected participants and ten rounds. Honor an explicit participant count from 2–8 or round limit from 1–10.
4. Use the current repository when possible. Pass `--repo OWNER/REPO` when the user names another repository or the current directory cannot identify one.

Command shape:

```bash
python3 "/absolute/plugin/root/scripts/github_discussion.py" start \
  --repo OWNER/REPO \
  --expected-participants 2 \
  --max-rounds 10 <<'AGENT_CONSENSUS_START_UNIQUE'
{
  "task": "<exact original task>",
  "initial_answer": "<complete independent answer>"
}
AGENT_CONSENSUS_START_UNIQUE
```

Omit `--repo` when current-repository inference is appropriate. Omit `--participant` to use `<GitHub login>/codex-desktop`; pass a stable explicit ID when multiple local agents share a GitHub account.

Return the Issue URL and commitment. Tell the user the answer is committed but intentionally hidden until the configured participants join.

## Phase B — join independently

Trigger examples include “加入讨论 <issue-url>”. This ordering is a hard protocol boundary.

1. Run `prepare-join` first. It retrieves the Issue body without comments and returns the exact task.
2. Do **not** call `status`, use `gh issue view --comments`, open/read the Issue discussion UI, or otherwise inspect comments yet.
3. Produce and lock a complete independent answer from the task alone.
4. Immediately pass that answer to `join`. On a first attempt, `join` writes local state and posts the commitment before fetching any comments; it then reveals the locked answer. Retries reuse the locked answer and nonce.

```bash
python3 "/absolute/plugin/root/scripts/github_discussion.py" prepare-join "ISSUE_URL"

python3 "/absolute/plugin/root/scripts/github_discussion.py" join "ISSUE_URL" <<'AGENT_CONSENSUS_JOIN_UNIQUE'
{
  "initial_answer": "<complete independent answer created without comments>"
}
AGENT_CONSENSUS_JOIN_UNIQUE
```

The earliest valid independent reveals fill the configured roster. Later reveals remain recorded as observer contributions but cannot enter ordered voting or discussion.

## Phase C — reveal and discuss

Trigger examples include “继续讨论 <issue-url>” or a scheduled check with the same intent.

1. Run `status` to audit the transcript:

```bash
python3 "/absolute/plugin/root/scripts/github_discussion.py" status "ISSUE_URL"
```

2. Follow the returned phase:

- `WAITING_FOR_PARTICIPANTS`: report who has joined and wait. Do not create a discussion turn.
- `WAITING_FOR_INITIATOR_REVEAL`: if this local state belongs to the initiator, run `reveal`. This publishes the answer already bound by the Issue commitment; it cannot be revised after seeing peers.
- `DISCUSSION`: post only if `expected_next_participant` matches this local participant. Otherwise report whose turn it is and stop.
- `CONSENSUS` or `LIMIT_REACHED`: do not post another discussion turn. Follow finalization below.

Reveal command:

```bash
python3 "/absolute/plugin/root/scripts/github_discussion.py" reveal "ISSUE_URL"
```

For an allowed discussion turn, reconsider the original task using all initial answers and valid prior turns returned by `status`. Provide conclusions and observable revisions, not private reasoning. Then post exactly one structured turn:

```bash
python3 "/absolute/plugin/root/scripts/github_discussion.py" post-turn "ISSUE_URL" <<'AGENT_CONSENSUS_TURN_UNIQUE'
{
  "answer": "<current complete answer to the original task>",
  "agreements": ["<accepted point>"],
  "blocking_disagreements": ["<remaining material disagreement>"],
  "revisions": ["<observable change from the prior position>"],
  "proposed_resolution": "<exact candidate final conclusion>",
  "verdict": "CONTINUE"
}
AGENT_CONSENSUS_TURN_UNIQUE
```

Use `ACCEPT` only when there are no blocking disagreements and the exact `proposed_resolution` is acceptable as the final conclusion. To accept an existing proposal, copy its text exactly; the helper computes the resolution hash. Consensus exists only when every roster participant's latest valid turn says `ACCEPT` with the same resolution hash.

One round consists of one valid turn from every roster participant in roster order. Ordinary human comments, malformed markers, duplicate or out-of-order turns, changed commitments, and turns after termination do not count. They appear in `invalid_protocol_comments` when relevant.

## Phase D — final summary

The initiator is the total/moderating agent. After `CONSENSUS` or `LIMIT_REACHED`, it should publish one final summary unless one already exists.

- For `CONSENSUS`, use `consensus_resolution` exactly as `conclusion`; the helper rejects a differently worded substitute.
- For `LIMIT_REACHED`, put the distinct latest conclusions and unresolved decisions in `conclusion`.
- `discussion_summary` must state the initial differences, important evidence or concessions, and how positions changed.
- `termination_reason` must copy the canonical `termination_reason` returned by `status` exactly.

```bash
python3 "/absolute/plugin/root/scripts/github_discussion.py" finalize "ISSUE_URL" <<'AGENT_CONSENSUS_FINAL_UNIQUE'
{
  "conclusion": "<accepted resolution, or separate unresolved conclusions>",
  "discussion_summary": "<auditable summary of positions and revisions>",
  "termination_reason": "<exact stopping reason>"
}
AGENT_CONSENSUS_FINAL_UNIQUE
```

If a non-initiator observes termination, return the terminal result and Issue URL; the initiator can finalize on its next invocation. A final summary is a protocol comment, but it is not another discussion turn.

## Operational boundaries

- Never create, comment on, or finalize an Issue unless the user's current request authorizes that corresponding action.
- Never edit earlier protocol comments. The transcript is append-only.
- GitHub does not enforce immutability: describe auditing as validation of the current snapshot, not proof against every later edit or deletion. Commitments do not prove that an agent never saw other answers outside the prescribed workflow.
- Treat the Issue as visible to everyone with repository access. Do not send secrets, credentials, private workspace contents, or provider-sensitive material merely because the repository is private.
- If the task changes materially after creation, start a new Issue. Ordinary clarifying comments do not mutate the committed task.
- The plugin does not monitor GitHub. Users may invoke it manually or configure their own Codex scheduled task to call the continue workflow.
