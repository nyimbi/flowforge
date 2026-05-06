"""Alembic bundle that ships the JTBD storage tables.

The bundle is chained after :data:`flowforge_sqlalchemy.alembic_bundle`:
``r1_initial`` (engine tables) → ``r2_jtbd`` (JTBD tables + RLS).
Hosts wire both versions directories into ``version_locations``::

    from flowforge_sqlalchemy.alembic_bundle import VERSIONS_DIR as ENGINE_VERSIONS
    from flowforge_jtbd.db.alembic_bundle import VERSIONS_DIR as JTBD_VERSIONS

    config.set_main_option(
        "version_locations",
        f"{config.get_main_option('script_location')}/versions"
        f" {ENGINE_VERSIONS} {JTBD_VERSIONS}",
    )

The default ``env.py`` shipped here registers
:data:`flowforge_sqlalchemy.metadata` (which already contains every
JTBD model after this package is imported) as the target metadata, so
``alembic upgrade r2_jtbd`` from a host that has not customised env.py
still produces the right tables.
"""

from __future__ import annotations

from pathlib import Path

BUNDLE_DIR: str = str(Path(__file__).parent)
VERSIONS_DIR: str = str(Path(__file__).parent / "versions")

__all__ = ["BUNDLE_DIR", "VERSIONS_DIR"]
