# flowforge changelog

## 0.1.0 — Unreleased

- Initial port ABCs (14 ports per portability spec §2).
- DSL Pydantic models for `WorkflowDef`, `FormSpec`, JTBD bundle.
- JSON schemas under `flowforge.dsl.schema`.
- Whitelisted expression evaluator with 25+ operators.
- Compiler validator: schema, unreachable states, dead-end transitions, duplicate priority, lookup-permission, subworkflow cycle.
- Engine two-phase fire (plan + commit) over an in-memory snapshot store.
- Simulator + replay reconstructor.
- In-memory port fakes for tests.
