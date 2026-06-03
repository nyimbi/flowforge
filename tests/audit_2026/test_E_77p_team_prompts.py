"""E-77p — Per-domain team prompts directory structure tests.

Verifies that the team-prompts scaffold under
python/flowforge-jtbd/team-prompts/ is present and well-formed for
the first three domains: insurance, healthcare, banking.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _repo_root() -> Path:
	for parent in Path(__file__).resolve().parents:
		if (parent / "pyproject.toml").is_file() and (parent / "docs").is_dir():
			return parent
	raise AssertionError("could not locate flowforge repo root")


_TEAM_PROMPTS = (
	_repo_root()
	/ "python"
	/ "flowforge-jtbd"
	/ "team-prompts"
)

_REQUIRED_DOMAINS = ("insurance", "healthcare", "banking")
_REQUIRED_DOMAIN_FILES = ("author.md", "reviewer.md", "citations.yaml", "doc-types.yaml")


def test_E_77p_team_prompts_present_for_first_three() -> None:
	"""E-77p: author.md, reviewer.md, citations.yaml, doc-types.yaml exist for all three domains."""
	assert _TEAM_PROMPTS.is_dir(), (
		f"team-prompts directory missing: {_TEAM_PROMPTS}"
	)
	for domain in _REQUIRED_DOMAINS:
		domain_dir = _TEAM_PROMPTS / domain
		assert domain_dir.is_dir(), f"team-prompts/{domain}/ directory missing"
		for fname in _REQUIRED_DOMAIN_FILES:
			fpath = domain_dir / fname
			assert fpath.is_file(), (
				f"team-prompts/{domain}/{fname} missing"
			)
			assert fpath.stat().st_size > 0, (
				f"team-prompts/{domain}/{fname} is empty"
			)


def test_E_77p_registry_has_three_teams() -> None:
	"""E-77p: team-prompts/registry.yaml contains exactly 3 active teams."""
	registry_path = _TEAM_PROMPTS / "registry.yaml"
	assert registry_path.is_file(), f"team-prompts/registry.yaml missing: {registry_path}"
	data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
	assert isinstance(data, dict), "registry.yaml must be a YAML mapping"
	assert "teams" in data, "registry.yaml must have a 'teams' key"
	teams = data["teams"]
	assert isinstance(teams, list), "registry.yaml 'teams' must be a list"
	assert len(teams) == 3, (
		f"registry.yaml must contain exactly 3 teams, got {len(teams)}"
	)
	team_domains = {t["domain"] for t in teams}
	for domain in _REQUIRED_DOMAINS:
		assert domain in team_domains, (
			f"registry.yaml missing team for domain '{domain}'"
		)
	for team in teams:
		for field in ("team_id", "domain", "tier", "status"):
			assert field in team, (
				f"registry.yaml team entry missing field '{field}': {team}"
			)


def test_E_77p_template_scaffold_present() -> None:
	"""E-77p: _template/ directory contains author.md and reviewer.md."""
	template_dir = _TEAM_PROMPTS / "_template"
	assert template_dir.is_dir(), f"team-prompts/_template/ directory missing: {template_dir}"
	for fname in ("author.md", "reviewer.md"):
		fpath = template_dir / fname
		assert fpath.is_file(), f"team-prompts/_template/{fname} missing"
		assert fpath.stat().st_size > 0, f"team-prompts/_template/{fname} is empty"


def test_E_77p_citation_extract_has_entries() -> None:
	"""E-77p: each domain's citations.yaml is a non-empty list."""
	for domain in _REQUIRED_DOMAINS:
		citations_path = _TEAM_PROMPTS / domain / "citations.yaml"
		assert citations_path.is_file(), (
			f"team-prompts/{domain}/citations.yaml missing"
		)
		data = yaml.safe_load(citations_path.read_text(encoding="utf-8"))
		assert isinstance(data, list), (
			f"team-prompts/{domain}/citations.yaml must be a YAML list, got {type(data).__name__}"
		)
		assert len(data) > 0, (
			f"team-prompts/{domain}/citations.yaml must contain at least one entry"
		)
		# each entry must have id, text, domain, jurisdiction
		for i, entry in enumerate(data):
			for field in ("id", "text", "domain", "jurisdiction"):
				assert field in entry, (
					f"team-prompts/{domain}/citations.yaml entry [{i}] missing field '{field}'"
				)
