# Changelog

## 0.1.0 — 2026-09-22

First public release, renamed from the locally developed Discuss plugin.

- Local independent Codex/Claude answers, session continuation and bounded debate.
- GitHub commitment/reveal, ordered 2–8 participant discussions and final summaries.
- Preserve the `codex-agent-consensus/v1` wire protocol, legacy configuration
  variable names, and existing local state location for compatibility.
- Retain user-level Claude gateway/model configuration through safe mode.
- Reject failed Claude responses even when partial structured output is present.
- Validate GitHub disagreement/revision fields and final termination reasons.
- Create owner-only temporary state files and atomically replace completed state.
- Add marketplace installation, bilingual introduction, usage and protocol guides,
  MIT licensing, contribution/security policies, CI and release checks.
