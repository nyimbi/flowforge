"""Out-of-band migration scripts for ``flowforge_audit_pg``.

These are *not* alembic migrations. The audit-pg schema is created via
``flowforge_audit_pg.sink.create_tables()`` for fresh deploys. Scripts in
this package handle in-place migrations on already-deployed databases —
they're idempotent, run under operator control, and do not chain like
alembic revisions.

E-37 / AU-01 backfill: import explicitly via
``from flowforge_audit_pg.migrations import audit_ordinal_backfill`` and
invoke ``audit_ordinal_backfill.main([...])``.
"""

from __future__ import annotations
