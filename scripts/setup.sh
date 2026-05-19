#!/usr/bin/env bash
# One-command local setup for Flowforge contributors and evaluators.
#
# Usage:
#   bash scripts/setup.sh
#
# Optional environment:
#   FLOWFORGE_SKIP_JS=1          skip JS workspace install
#   FLOWFORGE_SKIP_VISREG=1      skip visual-regression harness install
#   FLOWFORGE_SETUP_SMOKE=0      skip CLI smoke checks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN="\033[0;32m"
RED="\033[0;31m"
CYAN="\033[0;36m"
BOLD="\033[1m"
RESET="\033[0m"

ok() { echo -e "${GREEN}[OK]${RESET}  $*"; }
step() { echo -e "\n${BOLD}${CYAN}==> $*${RESET}"; }
fail() { echo -e "${RED}[FAIL]${RESET} $*" >&2; exit 1; }

need() {
	if ! command -v "$1" >/dev/null 2>&1; then
		fail "$1 is required. Install it, then rerun: bash scripts/setup.sh"
	fi
}

step "Checking required tools"
need uv
need python
if [[ "${FLOWFORGE_SKIP_JS:-0}" != "1" ]]; then
	need node
	need pnpm
fi
ok "required tools found"

step "Installing Python workspace with uv"
cd "$ROOT"
uv sync
ok "Python workspace ready"

if [[ "${FLOWFORGE_SKIP_JS:-0}" != "1" ]]; then
	step "Installing JS workspace with pnpm"
	pnpm --dir "$ROOT/js" install --frozen-lockfile
	ok "JS workspace ready"

	if [[ "${FLOWFORGE_SKIP_VISREG:-0}" != "1" ]]; then
		step "Installing visual-regression harness dependencies"
		pnpm --dir "$ROOT/tests/visual_regression" install --frozen-lockfile
		ok "visual-regression harness ready"
	fi
else
	ok "JS workspace skipped by FLOWFORGE_SKIP_JS=1"
fi

if [[ "${FLOWFORGE_SETUP_SMOKE:-1}" != "0" ]]; then
	step "Running CLI smoke checks"
	uv run flowforge --help >/dev/null
	uv run flowforge jtbd-generate --help >/dev/null
	uv run flowforge validate --help >/dev/null
	ok "flowforge CLI is runnable"
fi

cat <<'EOF'

Flowforge setup complete.

Next commands:
  uv run flowforge tutorial --out /tmp/flowforge-demo --no-pause
  uv run flowforge jtbd-generate --jtbd examples/insurance_claim/jtbd-bundle.json --out /tmp/flowforge-insurance --force
  bash scripts/check_all.sh
EOF
