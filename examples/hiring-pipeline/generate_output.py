"""Generate hiring-pipeline scaffold from jtbd-bundle.json.

Run from the framework workspace root::

    uv run python examples/hiring-pipeline/generate_output.py [--out-dir /tmp/hiring-out]

Writes generated files under ``out-dir`` (default: ``examples/hiring-pipeline/generated/``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
	parser = argparse.ArgumentParser(description="Generate hiring-pipeline scaffold")
	parser.add_argument(
		"--out-dir",
		type=Path,
		default=Path(__file__).parent / "generated",
		help="Directory to write generated files into (default: examples/hiring-pipeline/generated/)",
	)
	args = parser.parse_args()

	bundle_path = Path(__file__).parent / "jtbd-bundle.json"
	bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

	from flowforge_cli.jtbd import generate

	files = generate(bundle)

	out_dir: Path = args.out_dir
	out_dir.mkdir(parents=True, exist_ok=True)

	for f in files:
		dst = out_dir / f.path
		dst.parent.mkdir(parents=True, exist_ok=True)
		dst.write_text(f.content, encoding="utf-8")

	print(f"wrote {len(files)} files to {out_dir}", file=sys.stderr)
	for f in files:
		print(f.path)


if __name__ == "__main__":
	main()
