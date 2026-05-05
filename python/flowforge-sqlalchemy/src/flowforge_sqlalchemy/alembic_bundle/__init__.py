"""Alembic bundle shipped with flowforge-sqlalchemy.

Hosts include this directory in their Alembic config's
``script_location`` (or extend their own ``versions/`` with these
migrations). The bundle creates every flowforge-managed table; UMS-side
schemas remain the host's responsibility.

Usage from a host's Alembic ``env.py``::

    from flowforge_sqlalchemy import metadata as flowforge_metadata
    from flowforge_sqlalchemy.alembic_bundle import VERSIONS_DIR

    target_metadata = [host_metadata, flowforge_metadata]
    config.set_main_option(
        "version_locations",
        f"{config.get_main_option('script_location')}/versions {VERSIONS_DIR}",
    )

The :data:`VERSIONS_DIR` constant resolves to the absolute filesystem
path of the bundled ``versions/`` directory at import time.
"""

from __future__ import annotations

from pathlib import Path

BUNDLE_DIR: str = str(Path(__file__).parent)
VERSIONS_DIR: str = str(Path(__file__).parent / "versions")

__all__ = ["BUNDLE_DIR", "VERSIONS_DIR"]
