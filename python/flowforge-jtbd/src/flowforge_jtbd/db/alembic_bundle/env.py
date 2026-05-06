"""Default Alembic ``env.py`` for the JTBD bundle.

Mirrors :mod:`flowforge_sqlalchemy.alembic_bundle.env`. Hosts that ship
their own ``env.py`` should add :data:`VERSIONS_DIR` to
``version_locations`` instead of pointing ``script_location`` here.
This file exists so the bundle is *self-contained* — running

::

    alembic -c alembic.ini upgrade r2_jtbd

with ``script_location`` set to
``flowforge_jtbd/db/alembic_bundle`` plus the engine bundle wired in
``version_locations`` produces every flowforge + JTBD table.

Importing :mod:`flowforge_jtbd.db.models` here is intentional —
SQLAlchemy table registration runs at import time, so without it the
target metadata would not contain the JTBD tables.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from flowforge_sqlalchemy import metadata as target_metadata
from sqlalchemy import engine_from_config, pool

# Side-effect import: registers the JTBD models against
# ``flowforge_sqlalchemy.metadata`` so autogenerate / target_metadata
# diff sees them.
import flowforge_jtbd.db.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
	fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
	"""Emit SQL to stdout (no live connection)."""
	url = config.get_main_option("sqlalchemy.url")
	context.configure(
		url=url,
		target_metadata=target_metadata,
		literal_binds=True,
		dialect_opts={"paramstyle": "named"},
	)
	with context.begin_transaction():
		context.run_migrations()


def run_migrations_online() -> None:
	"""Open a sync engine and run."""
	cfg_section: dict[str, Any] = config.get_section(config.config_ini_section) or {}
	connectable = engine_from_config(
		cfg_section,
		prefix="sqlalchemy.",
		poolclass=pool.NullPool,
	)
	with connectable.connect() as connection:
		context.configure(connection=connection, target_metadata=target_metadata)
		with context.begin_transaction():
			context.run_migrations()


if context.is_offline_mode():
	run_migrations_offline()
else:
	run_migrations_online()
