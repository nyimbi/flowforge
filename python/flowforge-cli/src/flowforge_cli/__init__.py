"""flowforge-cli — typer-based command-line front end for flowforge.

The public surface is intentionally small: callers use the ``flowforge``
console-script entry point installed by :mod:`flowforge_cli.main`. Tests
import ``app`` from :mod:`flowforge_cli.main` and drive it through
:class:`typer.testing.CliRunner`.
"""

from .main import app

__all__ = ["app"]
__version__ = "0.1.0"
