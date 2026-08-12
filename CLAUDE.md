# CLAUDE.md

Working conventions for agents on this repository.

## Approach

- Read existing files before writing. Don't re-read within the same turn
  unless something else (a hook, another agent, a git operation) may have
  changed it since.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless the task needs their content directly: a
  citation, a conflict check, a direct question about that file.
- No sycophantic openers or closing fluff.
- No emojis or em-dashes in new prose. Existing docs that already use them
  (the research notes, ADR-0001, ADR-0002) are not retrofitted.
- Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.

## Language

Everything in this repository is written in English: code, configuration,
labels, branch names, commit messages, pull requests, issues, ADRs and
documentation. Conversations with the maintainer happen in French — the
repository is the artefact, not the conversation.

## Agent skills

### Issue tracker

Issues live in the GitHub Issues of `thefiven/homelab`, driven with `gh`.
See `docs/agents/issue-tracker.md`.

### Triage labels

The canonical vocabulary is kept as-is — `needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root, ADRs under `docs/adr/`.
See `docs/agents/domain.md`.
