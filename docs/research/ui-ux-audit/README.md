# Flowforge Dashboard and CLI UX Audit

Date: 2026-07-08

Scope:

- FastAPI dashboard source: `python/flowforge-fastapi/src/flowforge_fastapi/dashboard.py`
- FastAPI package inventory: `python/flowforge-fastapi/src/flowforge_fastapi/`
- CLI app wiring: `python/flowforge-cli/src/flowforge_cli/main.py`
- CLI command inventory: `python/flowforge-cli/src/flowforge_cli/commands/`
- Requested CLI help output for `flowforge`, `flowforge jtbd`, and `flowforge audit`

## Executive Summary

The dashboard is useful as a minimal internal ops page, but it is not close to a world-class workflow operations console. It is a single Python file that renders HTML with f-strings, Bootstrap 5 CDN assets, and a few database-backed tables. It has a good starting route set - overview, instances, instance detail, tasks, audit, and JSON health - but lacks the interaction depth operators expect: workflow visualization, live metrics, instance timelines, drill-down payloads, outbox/retry views, actionable task resolution, pagination controls, search, sorting, accessibility hardening, responsive navigation, dark mode, and real-time updates.

The CLI has a stronger foundation because it uses Typer, so top-level help is readable and commands are discoverable. The UX is still uneven. Many commands have terse help, no examples, no grouped workflows for common jobs, no progress indicators, inconsistent output formats, raw `typer.echo` status lines, sparse interactive prompts, and internal release-note language in user-facing help. It is acceptable for maintainers, but not yet polished for first-time users or production operators.

## Dashboard: Current State vs World-Class Standard

| Area | Current State | World-Class Standard |
| --- | --- | --- |
| Rendering foundation | Pure Python f-string HTML. The file explicitly avoids Jinja2 and uses Bootstrap and HTMX CDNs. Database values are interpolated directly into HTML. | Template engine or component renderer with autoescaping, partial templates, testable view models, CSP-friendly assets, and regression coverage for escaping. |
| Visual design | Bootstrap 5.3 is present, but used as default cards, striped tables, badges, and a dark navbar. There is no custom information hierarchy or dashboard design system. | Dense operator console with clear visual hierarchy, stable spacing, status semantics, icons, compact filters, saved views, and consistent interaction states. |
| Information architecture | Routes cover overview, instances, one instance detail, tasks, audit, and health. There is no workflow map, live metrics page, outbox page, retry/error page, or tenant-focused view. | Operations sitemap with workflow definitions, workflow graph, instance timeline, task resolution, outbox/retries, audit verification, SLA/error metrics, and tenant or environment filters. |
| Overview | Four stat cards and recent events. No trends, freshness indicator beyond page render time, alert state, or live refresh. | Time-windowed KPIs, sparklines, queue health, throughput, error rate, SLA breaches, last refresh, and operator actions. |
| Instance list | Exact `def_key` and `state` filters, `LIMIT/OFFSET`, no visible pagination controls, no sort controls, no search, no total count. | Search, multi-filter, date range, tenant/state filters, sortable columns, cursor pagination, total/visible counts, saved filters, export. |
| Instance detail | Shows definition metadata, state, context JSON, and audit event names/timestamps. | State graph with current node, event timeline, payload diff, tasks, outbox entries, retries, actor history, context diff, logs, and direct remediation actions. |
| Tasks | Lists tasks by status with pending/resolved toggle. The file docstring claims a resolve button, but the implementation has no resolve action. | Task inbox with assignment, priority/SLA, bulk actions, detail drawer, resolution form, audit trail, optimistic updates, and permission-aware disabled states. |
| Audit | Lists audit rows and a subject filter. The file docstring claims hash-chain verification status, but the implementation does not compute or display verification. | Verifiable audit explorer with chain status, range verification, event payloads, actor filters, export, tamper warnings, and links to affected workflow entities. |
| Accessibility | Basic semantic HTML exists, but inputs lack explicit labels, nav has no toggler or active state, tables lack captions/scope, badges rely on color, no skip link/focus strategy. | WCAG-grade keyboard flow, labeled controls, active nav state, captions, `scope`, color-independent statuses, focus management, high-contrast support, axe coverage. |
| Mobile responsiveness | Bootstrap grid and `.table-responsive` help, but the collapsed navbar cannot open because there is no toggler. Filter rows and JSON blocks can overflow. | Mobile-first navigation, stacked filters, responsive tables/cards, scroll-safe JSON, stable tap targets, and tested breakpoints. |
| Real-time updates | HTMX is loaded but unused. No `hx-*`, WebSocket, SSE, or polling behavior in the dashboard. A separate FastAPI WebSocket hub exists elsewhere, but the dashboard is not connected to it. | Live metrics and table refresh via WebSocket/SSE or HTMX polling, visible connection state, stale-data warning, and fallback manual refresh. |
| Dark mode | None. Page body is light, with dark nav/table headers only. | `data-bs-theme` or CSS custom properties, system preference support, toggle persistence, contrast-tested status colors. |

## Dashboard Findings

1. **HTML escaping is the highest-risk dashboard issue.** Values from `def_key`, `state`, `tenant_id`, audit `kind`, `actor_id`, task `note`, and instance context are interpolated into HTML without `html.escape` or a template engine. This is both a security and UX integrity problem: malformed or hostile data can break layout or render markup.
2. **The dashboard docstring overstates shipped behavior.** It claims pagination, task resolve button, history, and hash-chain verification status. The implementation has offset parameters but no pagination controls, no resolve action, no state history view beyond audit events, and no hash-chain verification UI.
3. **The UI is a data table, not an operations console.** It is useful for quick inspection, but it does not help an operator understand workflow shape, event flow, queue health, failed transitions, or remediation paths.
4. **Bootstrap is present but not enough.** A proper CSS framework is used, but mostly as default styling. The dashboard lacks a layout system, design tokens, component states, responsive nav behavior, and accessibility conventions.
5. **Real-time capability is nearby but unused.** `flowforge_fastapi.ws` provides a WebSocket fan-out hub, yet `dashboard.py` only includes HTMX and never uses it for polling or live updates.

## CLI: Current State vs World-Class Standard

| Area | Current State | World-Class Standard |
| --- | --- | --- |
| Framework | Typer app with Rich-formatted help. `no_args_is_help=True`. Shell completion disabled. | Typer/Rich foundation plus shell completion, examples, aliases, structured output, command grouping, and task-oriented workflows. |
| Command organization | Many root commands plus `audit` and `jtbd` groups. The root command list is long and mixes scaffolding, validation, migration, audit, AI, and release-health tools. | Clear groups: `project`, `workflow`, `instance`, `task`, `audit`, `jtbd`, `deps`, `dev`, `admin`; common paths surfaced first. |
| Help text | Top-level help is readable, but some descriptions are dense and internally oriented, especially release/audit references. Individual command help usually lacks examples. | Help includes one-line purpose, common examples, input/output expectations, exit codes, and links to docs. Internal roadmap labels stay out of primary help. |
| Error messages | Commands generally print `error: ...` and exit. Some errors include remediation, but many do not. | Errors include cause, action, example fix, and stable exit code. Machine-readable JSON errors available for automation. |
| Output | Mostly plain `typer.echo`. Some commands use Unicode status marks. Some support JSON, but not consistently. | Consistent Rich console output, `--format text|json`, `--quiet`, `--verbose`, `--no-color`, `NO_COLOR`, and stable schemas. |
| Progress | No general progress/status abstraction found. Long operations echo final writes or subprocess commands. | Rich `Progress` or `Status` for generation, validation scans, migrations, AI calls, dependency audits, and remote operations. |
| Interactive prompts | `tutorial` pauses with raw `input()`. No clear use of `typer.prompt` or `typer.confirm`. Force/apply/AI paths are not consistently guarded by prompts. | Typer/Rich prompts with non-interactive flags, dry-run previews, confirmation for destructive writes, and clear CI behavior. |
| Color and icons | Typer help is styled. Command bodies use Unicode check/warn/cross marks and box characters, but no consistent color system. | Semantic color with graceful plain-text fallback, icon policy, and snapshot-tested terminal rendering. |
| Missing operator commands | No first-class dashboard/open command, runtime status, workflow/instance/task list/show commands, task resolve, instance cancel/retry, audit export, metrics, doctor, config, version, or completion command. | CLI covers both authoring and operations, with clear local/offline and remote/server modes. |

## CLI Findings

1. **Typer gives the CLI a real base.** The requested `--help` outputs are readable and discoverable, and the `jtbd` and `audit` groups make some domain boundaries visible.
2. **The root command surface is too flat.** Authoring, migration, audit readiness, dependency upgrade, AI drafting, and tutorial commands compete in one command list.
3. **Help text lacks examples.** Representative commands such as `new`, `validate`, `simulate`, `jtbd lint`, `jtbd ai-draft`, and `tutorial` show option descriptions but no concrete examples section.
4. **Output is not consistently designed.** Some commands emit Unicode marks and structured summaries; others emit raw lines. JSON is available in places but not a cross-CLI contract.
5. **Interactive UX is shallow.** The tutorial has a useful five-step flow and next steps, but interactivity is a pause, not a guided prompt system. Potentially expensive or mutating flows need better preview and confirmation patterns.

## Priority Improvements Ordered by Impact

1. **Replace f-string dashboard rendering with safe templates or explicit escaping.** This is the highest-impact dashboard fix because it protects every page and makes later UI work safer.
2. **Correct the dashboard contract.** Either implement the docstring claims or remove them: visible pagination, task resolve action, history, and audit chain status.
3. **Add instance drill-down as the primary operator workflow.** Build a timeline view with state transitions, tasks, audit events, context snapshots/diffs, outbox entries, retries, and links to workflow definition.
4. **Add workflow visualization.** Show the workflow graph, current state for an instance, transition outcomes, guard failures, and task boundaries.
5. **Add real table controls.** Search, sort, pagination controls, total counts, date/tenant/status filters, and empty/loading/error states should exist on instances, tasks, and audit.
6. **Connect live updates.** Reuse the existing WebSocket hub or add SSE/HTMX polling for stat cards, queues, recent events, and instance timeline freshness.
7. **Make dashboard accessibility and mobile behavior non-negotiable.** Add labels, table captions/scopes, active nav, navbar toggler, skip link, keyboard states, contrast-safe badges, and responsive filter layouts.
8. **Add dark mode and design tokens.** Use Bootstrap `data-bs-theme` or app CSS custom properties with a small status-color palette and tested contrast.
9. **Reorganize the CLI around user jobs.** Move root commands into task-oriented groups and add missing `doctor`, `version`, `completion`, `dashboard`, `workflow`, `instance`, `task`, `metrics`, and `audit export` commands.
10. **Standardize CLI help, errors, output, progress, and prompts.** Add examples, exit codes, Rich progress, JSON/plain output modes, `--quiet`, `--verbose`, `--no-color`, and prompt policies for mutating commands.

## Specific HTML/CSS Changes for the Dashboard

1. **Introduce a safe rendering layer.**
   - Prefer Jinja2 templates with autoescape enabled.
   - If keeping f-strings temporarily, wrap every untrusted value in `html.escape`.
   - Render JSON context inside escaped `<pre><code>` blocks.

2. **Build a reusable page shell.**
   - Add `<a class="skip-link" href="#main">Skip to content</a>`.
   - Use `<nav aria-label="Flowforge dashboard">` and `<main id="main" tabindex="-1">`.
   - Add active nav state with `aria-current="page"`.
   - Add the missing Bootstrap navbar toggler and collapse target.

3. **Add a local dashboard stylesheet.**
   - Keep Bootstrap, but add `dashboard.css` for layout tokens, compact tables, metric cards, focus states, and dark mode.
   - Define CSS variables for status colors, borders, surfaces, spacing, and table density.
   - Avoid relying only on `bg-success`, `bg-warning`, and `bg-danger` for operational semantics.

4. **Upgrade metric cards.**
   - Use a responsive `.metric-grid` with stable card heights.
   - Add labels, sublabels, trend/time-window text, and `aria-label` summaries.
   - Add last-updated and stale-state indicators.

5. **Upgrade list pages.**
   - Replace unlabeled placeholders with explicit `<label>` text.
   - Add global search, tenant filter, date range, state/status select, and reset link.
   - Add `<caption>` and `scope="col"` to tables.
   - Add sortable headers as buttons or links with `aria-sort`.
   - Add previous/next pagination controls and total/visible counts.

6. **Upgrade instance detail.**
   - Add tabs for `Timeline`, `Context`, `Tasks`, `Outbox`, `Audit`, and `Definition`.
   - Add a workflow graph panel with the active state highlighted.
   - Show context diff between events instead of a single static blob.
   - Use responsive JSON blocks: `max-height`, `overflow:auto`, `white-space:pre-wrap`.

7. **Add real-time refresh.**
   - Option A: HTMX polling for partials, for example metric cards every 5 seconds and tables every 15 seconds.
   - Option B: WebSocket/SSE stream wired to the existing event hub, with visible connected/reconnecting/stale states.
   - Keep manual refresh as a fallback.

8. **Add dark mode.**
   - Use `data-bs-theme="auto|light|dark"` with a toggle.
   - Respect `prefers-color-scheme`.
   - Verify contrast for badges, table headers, links, and focus rings.

## Specific CLI Improvements

1. **Add examples to every command.**
   - Use Typer/Rich epilog text or command docstrings with an `Examples:` block.
   - Include one minimal example and one production/operator example per command.

2. **Restructure command groups.**
   - Keep `jtbd` and `audit`, but move root commands into coherent groups:
     - `project new`, `project add-jtbd`
     - `workflow validate`, `workflow simulate`, `workflow diff`, `workflow replay`
     - `instance list`, `instance show`, `instance retry`, `instance cancel`
     - `task list`, `task show`, `task resolve`
     - `audit verify`, `audit export`, `audit health`
     - `deps upgrade`, `deps pre-upgrade-check`
   - Leave backward-compatible aliases for existing root commands.

3. **Add missing lifecycle and operator commands.**
   - `flowforge doctor`
   - `flowforge version`
   - `flowforge completion install|show`
   - `flowforge dashboard open|url`
   - `flowforge metrics`
   - `flowforge audit export`
   - `flowforge jtbd publish`
   - `flowforge jtbd pull-upstream` or remove references to it from user-facing docs/help.

4. **Standardize output modes.**
   - Add global or shared `--format text|json` where practical.
   - Add `--quiet`, `--verbose`, and `--no-color`.
   - Honor `NO_COLOR`.
   - Keep stable JSON schemas for CI.

5. **Improve errors.**
   - Replace bare `error: ...` with a consistent pattern:
     - What failed
     - Why it failed
     - How to fix it
     - Example command
   - Use exit codes consistently and document them in help for commands that are likely to run in CI.

6. **Add progress and status indicators.**
   - Use Rich `Status` for AI calls and remote operations.
   - Use Rich `Progress` for generation, validation scans, migration analysis, bundle diffs, and dependency audits.
   - In CI/non-TTY mode, fall back to concise log lines.

7. **Improve interactive prompts.**
   - Replace raw `input()` with `typer.confirm` or Rich prompts.
   - Add `--yes` for non-interactive confirmation.
   - Add dry-run previews before forceful writes and migrations.
   - Prompt before overwriting non-empty output directories unless `--force` or `--yes` is supplied.

8. **Create shared CLI UX helpers.**
   - `flowforge_cli.console` for Rich console, color policy, tables, errors, success/warning/failure marks.
   - `flowforge_cli.output` for JSON/text formatting contracts.
   - `flowforge_cli.errors` for common exception-to-message mapping.

9. **Snapshot-test CLI help and output.**
   - Add tests for `flowforge --help`, group help, representative command help, error messages, JSON output, and no-color output.
   - This will prevent regressions in command names, descriptions, examples, and exit code behavior.

## Validation Notes

Requested help commands were run. The first direct `uv run` attempts failed because the sandbox could not read the existing home uv cache at `/Users/nyimbiodero/.cache/uv/sdists-v9/.git`. The commands were rerun successfully with `UV_CACHE_DIR=/private/tmp/flowforge-uv-cache`, preserving command behavior while using a readable cache path.

No code was changed. This audit only adds documentation under `docs/research/ui-ux-audit/`.
