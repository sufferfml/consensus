# Privacy and data flow

Consensus has no hosted backend, analytics endpoint, or project-owned telemetry.
The external CLIs and providers can have their own telemetry, storage, and terms.

| Data | Destination |
| --- | --- |
| Local task, inspected files, tool results and peer positions | Configured Codex and Claude providers or gateway |
| Local task, raw responses and discussion records | Unique local system-temp run directory printed by the helper |
| GitHub task, revealed answers, proposals, final summary | Selected GitHub Issue; visible to repository readers |
| Initial answers and commitment nonces | `~/.codex/github-agent-consensus/`, or the configured state directory |
| CLI authentication | Existing CLI/user settings and inherited environment |

There is no automatic redaction. Agents may inspect files allowed by their CLI
configuration; the plugin does not establish a new data-access boundary around
every tool. The GitHub helper does not itself upload arbitrary workspace files,
but an agent's submitted answer can quote private content.

You control local retention. Deleting an active GitHub participant's state can
make its commitment impossible to reveal. Removing local records does not delete
provider records, GitHub comments, notifications, forks or copies made by others.
Deleting an Issue is not a guarantee that all copies disappear.

For project security reports, follow [SECURITY.md](SECURITY.md). Use the relevant
provider's policies for requests concerning provider-side storage.
