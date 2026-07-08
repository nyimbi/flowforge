"""Rich output helpers shared by the flowforge CLI."""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.markup import escape


console = Console()
err_console = Console(stderr=True)


class CliState:
	"""Process-local CLI display state set by the root callback."""

	verbose: bool = False
	quiet: bool = False


state = CliState()


def configure_verbosity(*, verbose: bool, quiet: bool) -> None:
	"""Set global verbosity flags for command output."""

	state.verbose = verbose
	state.quiet = quiet


def verbose(message: str) -> None:
	"""Print a verbose-only diagnostic message."""

	if state.verbose and not state.quiet:
		console.print(f"[dim]{escape(message)}[/]", markup=True)


def success(message: str) -> None:
	"""Print a consistent success prefix."""

	if not state.quiet:
		console.print(f"[bold green]Success[/]: {escape(message)}", markup=True)


def error(what: str, *, why: str, next_step: str) -> None:
	"""Print a consistent error with cause and next action."""

	err_console.print(
		f"[bold red]Error[/]: {escape(what)}\n"
		f"[yellow]Why:[/] {escape(why)}\n"
		f"[yellow]Hint:[/] {escape(next_step)}",
		markup=True,
	)


def warning(message: str, *, next_step: str | None = None) -> None:
	"""Print a consistent warning with an optional next action."""

	if state.quiet:
		return
	body = f"[yellow]Warning[/]: {escape(message)}"
	if next_step:
		body += f"\n[yellow]Hint:[/] {escape(next_step)}"
	console.print(body, markup=True)


def install_rich_echo(typer_module: Any) -> None:
	"""Route ``typer.echo`` through Rich consoles while preserving plain text.

	Existing command modules use ``typer.echo`` heavily. Installing this shim
	keeps their output captured by Typer tests, but still satisfies the CLI-wide
	Console output contract.
	"""

	if getattr(typer_module.echo, "_flowforge_rich_echo", False):
		return

	def _rich_echo(
		message: object | None = None,
		file: Any | None = None,
		nl: bool = True,
		err: bool = False,
		color: bool | None = None,
		**_: Any,
	) -> None:
		_ = color
		text = "" if message is None else str(message)
		end = "\n" if nl else ""
		if state.quiet and not err:
			return
		if file not in (None, sys.stdout, sys.stderr):
			file.write(text + end)
			return

		target = err_console if err or file is sys.stderr else console
		lower = text.lower()
		if err and lower.startswith("error:"):
			detail = text.split(":", 1)[1].strip()
			target.print(
				"[bold red]Error[/]: "
				f"error: {escape(detail)}\n"
				"[yellow]Why:[/] The command rejected the input or an operation failed.\n"
				"[yellow]Hint:[/] Fix the input and retry, or run the command with --help.",
				markup=True,
				soft_wrap=True,
				end=end,
			)
			return
		if err and lower.startswith("warning:"):
			detail = text.split(":", 1)[1].strip()
			target.print(
				"[yellow]Warning[/]: "
				f"warning: {escape(detail)}\n"
				"[yellow]Hint:[/] Review the finding before continuing.",
				markup=True,
				soft_wrap=True,
				end=end,
			)
			return

		target.print(text, markup=False, highlight=False, emoji=False, soft_wrap=True, end=end)

	_rich_echo._flowforge_rich_echo = True  # type: ignore[attr-defined]
	typer_module.echo = _rich_echo
