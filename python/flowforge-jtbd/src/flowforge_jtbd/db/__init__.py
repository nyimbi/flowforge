"""SQLAlchemy storage layer for JTBD specs, compositions, and lockfiles.

The ORM models share metadata with :mod:`flowforge_sqlalchemy` so that
the standard alembic bundle (``flowforge_sqlalchemy.alembic_bundle``)
can pick them up and the engine + JTBD layers stay in one
:class:`sqlalchemy.MetaData`. The dedicated alembic revision
``r2_jtbd`` chained after ``r1_initial`` creates the new tables and
installs Postgres-only RLS policies.

Tables:

* :class:`JtbdLibrary` — ``jtbd_libraries``.
* :class:`JtbdDomain` — ``jtbd_domains``.
* :class:`JtbdSpecRow` — ``jtbd_specs``. The ``Row`` suffix
  disambiguates from :class:`flowforge_jtbd.dsl.JtbdSpec` (the
  pydantic model that round-trips through the ``spec`` JSONB column).
* :class:`JtbdCompositionRow` — ``jtbd_compositions``.
* :class:`JtbdCompositionPin` — ``jtbd_compositions_pins``.
* :class:`JtbdLockfileRow` — ``jtbd_lockfiles``.
"""

from __future__ import annotations

from .models import (
	JtbdCompositionPin,
	JtbdCompositionRow,
	JtbdDomain,
	JtbdLibrary,
	JtbdLibraryStatus,
	JtbdLockfileRow,
	JtbdSpecRow,
	JtbdSpecRowStatus,
)

__all__ = [
	"JtbdCompositionPin",
	"JtbdCompositionRow",
	"JtbdDomain",
	"JtbdLibrary",
	"JtbdLibraryStatus",
	"JtbdLockfileRow",
	"JtbdSpecRow",
	"JtbdSpecRowStatus",
]
