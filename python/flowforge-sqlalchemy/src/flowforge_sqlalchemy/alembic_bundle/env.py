"""Default Alembic ``env.py`` for the bundled migrations.

Hosts that ship their own ``env.py`` should add
:data:`flowforge_sqlalchemy.alembic_bundle.VERSIONS_DIR` to
``version_locations`` instead of pointing ``script_location`` here. This
file exists so the bundle is *self-contained* — the test suite (and any
host that just wants the flowforge tables) can run

::

    alembic -c alembic.ini upgrade r1_initial

with ``script_location`` set to ``flowforge_sqlalchemy/alembic_bundle``.

Online and offline modes both wire :data:`flowforge_sqlalchemy.metadata`
as ``target_metadata``.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

from flowforge_sqlalchemy import metadata as target_metadata

# Alembic Config is the .ini file in use; ``config.config_file_name`` is
# ``None`` when invoked via the Python API.
config = context.config
if config.config_file_name is not None:
	fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
	"""Run in 'offline' mode — emit SQL to stdout."""
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
	"""Run in 'online' mode — open a sync engine and execute."""
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
