# Coding Agent entry point

Read **[AGENT.md](./docs/AGENT.md)** as the primary working agreement. Then read **[商机挖掘系统_渐进式实现交接.md](./docs/商机挖掘系统_渐进式实现交接.md)** for product direction and **[DECISION_LOG.md](./docs/DECISION_LOG.md)** for ongoing decision recording.

This file exists solely for agent environments that discover `AGENTS.md` by default. `AGENT.md` is the authoritative requested instructions file; do not maintain conflicting copies.

## Optional Retrieval Backend: XERJ

XERJ is an optional local search and retrieval backend available through the `xerj` CLI. It complements existing code exploration tools rather than replacing them.

### Capabilities and Advantages

When properly indexed, XERJ can provide:

- Indexed full-text search across source code, documentation, and structured data.
- AST-assisted symbol and definition lookup with source locations.
- Ranked passage retrieval, reducing unnecessary file reads and context consumption.
- Vector and hybrid retrieval where supported and configured.
- Cross-file discovery and retrieval from larger or unfamiliar codebases.

These capabilities are opportunities, not guaranteed improvements. Actual usefulness depends on the task, index coverage, freshness, and retrieval quality. Default vectorization does not imply neural semantic understanding.

### Workspace Activation

XERJ is optional and may not be installed, running, or configured for the current workspace.

When indexed retrieval seems useful:

1. Check CLI availability using `command -v xerj` or the platform equivalent.
2. Check whether the configured local XERJ instance is reachable and the current workspace is indexed.
3. If indexing is needed, use `xerj autoindex <workspace-root> --prefix <workspace-prefix> --dry-run` to inspect the proposed scope and cost.
4. Use a stable, workspace-specific prefix to avoid collisions with unrelated projects.
5. When the operation is reasonably small and authorized by the current task, indexing may proceed. Request user approval for substantial indexing operations, unclear data boundaries, or material resource consumption.
6. Search the workspace with `xerj search --prefix <workspace-prefix> "<query>"`, or use `xerj def` for symbol discovery.

### This Workspace's Configured Instance

The concrete values for this repository are fixed; use them instead of the placeholders above. Wrappers live in `tools/xerj/` and `tools/xerj/README.md` documents the details.

| Setting | Value |
|---|---|
| Indexed root | `P:\CRM` (main workspace only; never a worktree) |
| Prefix | `crm-main` |
| Endpoint | `http://127.0.0.1:9200` (also claims 9201/9202), loopback only |
| Embedding | `lexical` (offline; not neural semantics) |
| Runtime state | `P:\CRM\.tower\xerj` — hidden, excluded from autoindex and git |
| Index mode | `--no-semantic --no-graph --code-analyzer code` |

Start, stop, and status (PowerShell, copy-paste):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-start.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-status.ps1   # add -Map
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-stop.ps1
```

Indexing is dry-run by default. Review the scope first, then apply; re-running the same `-Apply` command is the incremental update:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-index.ps1           # dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-index.ps1 -Apply    # first and incremental
```

Do not add `--yes`, `--drop-indexed`, or `--replace-prefix` automatically; those accept a reduced plan or delete indexed documents and need an explicit human decision. A non-zero exit (3 = skipped/refused files, 4 = decision required) must be reported, not retried blindly.

Query compactly and verify hits against the current file:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-search.ps1 -Query "module + identifier + behavior" -K 3 -Full 500
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-search.ps1 -Def -Query "ExactSymbol" -Lang typescript
```

Migration: stop the node, copy `data\`, `state\`, and `logs\` from `.tower\xerj` to a new absolute directory, set `XERJ_CRM_HOME` to that directory before starting, then verify with `-Map` and a known query. Scripts never delete the old directory or any index; keep both until verification passes.

Security boundaries: never print or commit `admin.key`; do not share node logs (the first launch log may contain a one-time console setup link); do not capture or share `-Foreground` output on a fresh runtime for the same reason; keep the node on loopback and default auth; do not enable neural/proxy embeddings, MCP, external feedback, or model downloads. The current corpus contains project documents only — this loopback setup is an experiment, not a production security boundary for real customer data.

Consult `xerj --help` and relevant subcommand help when needed. Avoid loading extensive documentation into context unnecessarily.

### Tool Selection and Fallback

- Choose retrieval methods according to the task's information needs, expected accuracy, latency, and context cost.
- XERJ may be particularly useful for broad exploration, unfamiliar implementations, conceptual discovery, and locating relevant definitions.
- Indexed search is not inherently better for every task. Direct inspection or other retrieval approaches may be more effective.
- Treat search results as evidence candidates, not authoritative representations of the current codebase. Verify important findings against current source files when appropriate.
- If XERJ is unavailable, its index is stale or incomplete, or its results are ineffective, briefly note the limitation when relevant and continue using another suitable approach.
- No specific fallback tool or fixed retrieval sequence is prescribed. Choose according to your capabilities and the task.
- Do not repeatedly retry ineffective searches or spend disproportionate effort repairing an optional retrieval backend.

### Operational Boundaries

- Do not automatically install software, enable MCP integrations, download external corpora, or submit external feedback.
- Do not index sensitive or unrelated directories without authorization.
- Do not modify or delete unrelated indices.
- Keep retrieval outputs focused and avoid injecting large search results into context without a clear need.
- Indexing is an optimization, not a prerequisite for completing the user's task.

**Principle:** Optimize for reliable task completion and useful evidence, not for maximizing XERJ usage.