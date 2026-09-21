# Consensus

[简体中文](README.zh-CN.md) · [Usage guide](docs/USAGE.md) · [Protocol](docs/PROTOCOL.md)

Independent answers first. Discussion second. Agreement you can inspect.

Consensus is a Codex Desktop plugin that asks agents to answer independently, review
each other's positions, and discuss a concrete resolution. It returns agreement or
the remaining disagreements, together with a record of how the discussion ended.

This is an experimental `0.1.0` release, previously developed locally as **Discuss**.
It is a community project, not an official OpenAI or Anthropic product.

## Two ways to work

| | Local mode | GitHub mode |
| --- | --- | --- |
| Participants | Codex CLI + Claude Code CLI | 2–8 agents, including colleagues on other computers |
| Coordinator | Current Codex Desktop task | Initiator; GitHub Issue stores the discussion |
| Independent answers | Two fresh sessions, started concurrently | Answer committed before reading comments, then revealed |
| Discussion | Automatic, default maximum 10 rounds | Ordered turns, advanced manually or by your own automation |
| Result | Local JSON and Markdown transcript | Issue comments and initiator's final summary |

Consensus means every participating agent explicitly accepted the same normalized
resolution text. It does **not** establish that the conclusion is true. Agents can
share blind spots. Review the evidence before acting.

## Install

Use a Codex version with plugin marketplace support:

```bash
codex plugin marketplace add sufferfml/consensus
codex plugin add consensus@consensus
```

Start a **new Codex Desktop task**, select `consensus` in the plugin picker, and
send your question. A Claude terminal does not need to be open.

For local development, clone this repository and register the checkout instead:

```bash
git clone https://github.com/sufferfml/consensus.git
cd consensus
codex plugin marketplace add "$PWD"
codex plugin add consensus@consensus
```

Use one source for the `consensus` marketplace at a time. See
[updating and migrating](docs/USAGE.md#updating-and-migrating) for replacement steps.

## Quick start

In a task with the plugin selected:

> Have Codex and Claude independently evaluate this plan, then discuss it for up
> to 10 rounds. Return the shared conclusion, remaining disagreements, and a
> summary of how the discussion ended: [your plan]

For a colleague:

> Start a GitHub consensus discussion in OWNER/REPO about: [your question]

Share the returned Issue URL. Your colleague selects the plugin in their own
Codex Desktop task and sends:

> Join this discussion: [Issue URL]. Answer independently before reading comments.

Each participant can subsequently send `Continue this discussion: [Issue URL]`.
The plugin advances one eligible discussion turn per invocation. It does not run
a background relay or poll GitHub. You can configure scheduling separately.

## Requirements

- Python 3.10+; the helpers use only the Python standard library.
- Local mode: authenticated `codex` and `claude` commands on `PATH`.
- GitHub mode: authenticated GitHub CLI (`gh`) with access to the selected repository.
- Codex Desktop for the plugin-driven experience; Python helpers also run directly.

The live local flow was tested on macOS with Codex CLI `0.153.0` and Claude Code
`2.1.258`. Hermetic tests run on macOS and Linux; other CLI versions require
compatible command flags. Windows is not currently verified. These are observed
versions, not a claim that they are the newest or the minimum supported versions.

Check setup from a repository checkout:

```bash
python3 plugins/consensus/scripts/orchestrate.py --doctor
python3 plugins/consensus/scripts/github_discussion.py doctor --check-repo
```

The doctor commands inspect executables and authentication; they do not prove
that a model endpoint is reachable. A gateway can work even when OAuth login
status is absent. See the [usage guide](docs/USAGE.md) for models, gateways,
timeouts, direct CLI examples, and troubleshooting.

## Safety and privacy

Codex runs in its read-only sandbox. Claude runs with `--safe-mode`, user settings,
`plan` permissions, strict MCP configuration, and a limited built-in tool list.
Bash is still available; its read-only usage is a protocol instruction, not an
OS-enforced sandbox or a command allowlist. Use trusted workspaces. Neither
participant is intended to implement changes; the Desktop moderator handles
separately authorized implementation.

Local tasks, inspected files and tool results can reach the configured model
providers or custom gateway. Local transcripts may contain sensitive content;
Consensus does not automatically redact them. GitHub mode publishes task text,
answers and discussion to everyone who can access the selected repository.
Credentials stay in your existing CLI configuration; do not commit them here.

The commitment mechanism checks consistency with the published answer. It cannot
prove that an agent never read outside information, nor make GitHub comments
immutable. Read [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md).

## Development

```bash
python3 tools/check.py
```

This runs local and GitHub protocol tests with fake CLI executables. It does not
contact model APIs or post Issues. GitHub Actions runs the same suite and a
separate credential scan. See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution
and testing expectations.

```text
.agents/plugins/marketplace.json   GitHub-installable marketplace
plugins/consensus/                 Installable plugin bundle
  .codex-plugin/plugin.json        Identity and metadata
  skills/dual-agent-consensus/     Agent instructions for both modes
  scripts/                        Python orchestrator and GitHub transport
  tests/                          Offline protocol and CLI tests
docs/                             Human-facing usage, protocol, release notes
tools/check.py                    Dependency-free verification entry point
```

## License

[MIT](LICENSE), copyright 2026 sufferfml. Provider CLIs and services remain subject
to their own licenses and terms; they are not bundled. See [NOTICE](NOTICE).
