# Audit Reasoning Notes

This file records the evidence-weighting behind the UI/UX audit. It is intentionally written as an audit rationale, not as private chain-of-thought.

## Audit Lens

The dashboard was assessed as an operations console for workflow runtime users. A world-class version should let an operator answer these questions quickly:

- What is running, failing, delayed, or blocked?
- Which workflow and instance caused the issue?
- What state, transition, task, audit event, outbox entry, or actor explains it?
- What action can the operator safely take next?
- Is the data current?

The CLI was assessed as both an authoring tool and an operator tool. A world-class version should support:

- First-run success through examples and clear help.
- CI automation through stable output, documented exit codes, and JSON.
- Human operation through progress, color, prompts, and safe defaults.
- Discoverability through coherent command groups and missing-command coverage.

## Dashboard Reasoning

`dashboard.py` is a compact server-rendered page set. That is an acceptable starting point because it avoids a frontend build and can be mounted quickly by host apps. The tradeoff is that every UX feature is now hand-built inside Python string concatenation.

The strongest positive evidence is that the file already has useful core routes:

- JSON health endpoint
- Overview
- Instance list
- Instance detail
- Task queue
- Audit log

The strongest negative evidence is that HTML output is assembled from f-strings and unescaped values. This affects all pages and must be fixed before investing in more UI. It is not just a security concern; any unexpected markup in workflow metadata can damage page layout and operator trust.

The dashboard docstring also creates product risk. It promises pagination, task resolution, history, and audit hash-chain verification status, but the implementation does not deliver those behaviors. That mismatch can mislead host teams that mount the dashboard expecting production-grade operational capability.

Bootstrap presence was counted as a positive, but only a small one. A CSS framework is present, yet the UI mostly uses default Bootstrap components. Visual quality, accessibility, mobile ergonomics, and dark mode all need deliberate implementation.

Real-time capability was scored as missing for the dashboard even though `flowforge_fastapi.ws` exists. The relevant product question is whether the dashboard user sees live updates. `dashboard.py` imports HTMX but does not use polling, WebSocket, SSE, or partial updates.

## CLI Reasoning

The CLI has a better baseline than the dashboard because Typer supplies readable help, command discovery, required argument markers, and styled terminal layout. The requested help output confirmed the top-level, `jtbd`, and `audit` command groups render cleanly.

The core UX problem is not framework choice. It is product shaping:

- Too many commands live at root.
- Common examples are absent.
- Some help text includes internal release labels.
- Output behavior is inconsistent across commands.
- JSON output and exit code documentation are partial.
- Long operations do not expose progress.
- Interactive behavior is mostly a tutorial pause, not a prompt strategy.

The source search found only the tutorial raw `input()` pause as an interactive prompt pattern. That supports the finding that interactive UX is shallow. The same search did not find a shared progress/status abstraction, which supports the progress-indicator finding.

Unicode status marks are useful when rendered well, and the source uses them in several places. The audit treats this as a mixed result: it improves scanability in modern terminals, but it should be governed by a shared console helper with `NO_COLOR` and plain-output fallbacks.

## Priority Rationale

Priority order favors foundational fixes before polish:

1. Escaping/templates first because unsafe rendering affects every dashboard view.
2. Dashboard contract correction second because inaccurate built-in docs create false confidence.
3. Instance drill-down and workflow visualization next because they are the highest-value operator workflows.
4. Table controls and real-time updates next because they improve daily usability across current pages.
5. Accessibility, mobile, and dark mode are treated as product requirements, not optional polish, but they become easier once the rendering layer and layout are stabilized.
6. CLI grouping and examples precede progress/prompt polish because users must first find the right command and understand how to run it.
7. Shared CLI helpers and snapshot tests come before broad command-by-command polish so behavior stays consistent.

## Confidence and Gaps

Confidence is high for the dashboard findings because the full file was read and all routes are in one module.

Confidence is medium-high for CLI findings because the top-level app, command inventory, requested help output, representative subcommand help, and targeted source searches were reviewed. A command-by-command runtime audit with fixtures was not performed, so detailed behavior of every command output remains a follow-up task.

No browser screenshots, axe scans, or terminal snapshot tests were run. The audit is source-and-help-output based.
