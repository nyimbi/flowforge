"""Integration test for v0.3.0 W2 / item 12 — OpenTelemetry by construction.

Imports the generated ``claim_intake`` adapter from
``examples/insurance_claim/generated/`` and fires an event end-to-end
under an in-memory OpenTelemetry exporter. Asserts the resulting
``flowforge.fire`` span carries the canonical attribute set documented
at :data:`flowforge.ports.tracing.STANDARD_SPAN_ATTRIBUTES`, and that
the engine-fire latency histogram lands in the configured
``HistogramMetricsPort``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("opentelemetry")

from flowforge import config as ff_config
from flowforge.ports.metrics import FIRE_DURATION_HISTOGRAM
from flowforge.ports.tracing import STANDARD_SPAN_ATTRIBUTES
from flowforge.ports.types import Principal
from flowforge.testing.port_fakes import InMemoryMetrics
from opentelemetry import trace as _otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


pytestmark = pytest.mark.asyncio


_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXAMPLE = _REPO_ROOT / "examples" / "insurance_claim" / "generated"


def _import_generated_adapter() -> Any:
	"""Import ``claim_intake_adapter.py`` from the example tree.

	The example tree isn't an installed package so we side-load via
	``importlib.util.spec_from_file_location``. The adapter module
	references its sibling compensation_handlers + the workflows JSON
	via relative paths, so we register the parent package on sys.modules
	first to satisfy ``..claim_intake.compensation_handlers`` imports.
	"""

	# Register parent packages (src.<pkg>.<...>) so relative imports work.
	src = _EXAMPLE / "backend" / "src" / "insurance_claim_demo"
	pkg_dir = src
	# Inject namespaces: insurance_claim_demo, .adapters, .claim_intake.
	for ns in ("insurance_claim_demo", "insurance_claim_demo.adapters", "insurance_claim_demo.claim_intake"):
		if ns in sys.modules:
			continue
		mod_path = pkg_dir
		if ns.endswith(".adapters"):
			mod_path = pkg_dir / "adapters"
		elif ns.endswith(".claim_intake"):
			mod_path = pkg_dir / "claim_intake"
		spec = importlib.util.spec_from_file_location(
			ns,
			mod_path / "__init__.py",
			submodule_search_locations=[str(mod_path)],
		)
		assert spec is not None and spec.loader is not None
		module = importlib.util.module_from_spec(spec)
		sys.modules[ns] = module
		# claim_intake/__init__.py and adapters/__init__.py exist as
		# empty shims; loader will create them lazily on first attr
		# access. Only execute if the file actually exists.
		if (mod_path / "__init__.py").is_file():
			spec.loader.exec_module(module)
	# Now load the adapter module itself.
	adapter_path = src / "adapters" / "claim_intake_adapter.py"
	spec = importlib.util.spec_from_file_location(
		"insurance_claim_demo.adapters.claim_intake_adapter",
		adapter_path,
	)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	# Override the workflow-definition path: the template's
	# ``parents[3]`` resolves to ``backend/`` in the example layout but
	# the actual definition lives at ``generated/workflows/...``. Hosts
	# typically copy the workflows under ``backend/`` at install time;
	# this test side-steps that by pointing the adapter at the source
	# location.
	setattr(
		module,
		"_DEF_PATH",
		_EXAMPLE / "workflows" / module.WORKFLOW_KEY / "definition.json",
	)
	return module


@pytest.fixture
def otel_exporter() -> InMemorySpanExporter:
	"""Install an in-memory tracer provider for span capture."""

	current = _otel_trace.get_tracer_provider()
	if not isinstance(current, TracerProvider):
		current = TracerProvider()
		_otel_trace.set_tracer_provider(current)
	exporter = InMemorySpanExporter()
	current.add_span_processor(SimpleSpanProcessor(exporter))
	return exporter


@pytest.fixture
def reset_config() -> None:
	"""Reset flowforge.config to in-memory fakes per test."""

	ff_config.reset_to_fakes()
	# Force-replace metrics with a fresh InMemoryMetrics so we observe
	# only this test's histogram observations.
	ff_config.metrics = InMemoryMetrics()
	return None


async def test_generated_adapter_emits_fire_span_with_canonical_attrs(
	otel_exporter: InMemorySpanExporter,
	reset_config: None,
) -> None:
	"""Generated adapter wraps fire() in a ``flowforge.fire`` span.

	Verifies all canonical attributes documented by
	``STANDARD_SPAN_ATTRIBUTES`` are present.
	"""

	adapter = _import_generated_adapter()
	# Ensure the adapter picked up our process-wide tracer provider.
	assert getattr(adapter, "_OTEL_TRACER", None) is not None, \
		"generated adapter failed to import opentelemetry — was the [otel] extra installed?"

	principal = Principal(user_id="test-user", roles=("claims-officer",), is_system=False)
	result = await adapter.fire_event(
		"submit",
		payload={"claimant_name": "Alice", "loss_date": "2026-01-01", "claim_amount": 1234.56},
		principal=principal,
		tenant_id="tenant-otel-test",
	)
	assert result.new_state, "fire returned no new state"

	finished = otel_exporter.get_finished_spans()
	fire_spans = [s for s in finished if s.name == "flowforge.fire"]
	assert fire_spans, f"no flowforge.fire span emitted (got {[s.name for s in finished]})"
	span = fire_spans[-1]
	attrs = dict(span.attributes or {})
	for key in STANDARD_SPAN_ATTRIBUTES:
		assert key in attrs, f"missing canonical attribute {key} on flowforge.fire span"
	assert attrs["flowforge.tenant_id"] == "tenant-otel-test"
	assert attrs["flowforge.jtbd_id"] == "claim_intake"
	assert attrs["flowforge.event"] == "submit"
	assert attrs["flowforge.principal_user_id"] == "test-user"
	# new_state attribute set after fire returns; it's an extension key.
	assert attrs.get("flowforge.new_state") == result.new_state


async def test_generated_adapter_records_fire_duration_histogram(
	otel_exporter: InMemorySpanExporter,
	reset_config: None,
) -> None:
	"""Generated adapter records into ``flowforge.fire.duration_seconds``."""

	adapter = _import_generated_adapter()
	principal = Principal(user_id="test-user", roles=("claims-officer",), is_system=False)
	await adapter.fire_event(
		"submit",
		payload={"claimant_name": "Bob", "loss_date": "2026-01-01", "claim_amount": 1.0},
		principal=principal,
		tenant_id="tenant-otel-test",
	)
	# InMemoryMetrics implements record_histogram so the adapter takes
	# that path (the histogram observation lands in .histograms, not .points).
	hist_names = {name for (name, _value, _labels) in ff_config.metrics.histograms}
	assert FIRE_DURATION_HISTOGRAM in hist_names, \
		f"fire-duration histogram not recorded; got {hist_names!r}"
	# Standard label set is honoured.
	tenant_obs = [
		(name, value, labels)
		for (name, value, labels) in ff_config.metrics.histograms
		if name == FIRE_DURATION_HISTOGRAM
	]
	assert tenant_obs, "no observations under the fire-duration name"
	_, value, labels = tenant_obs[0]
	assert value >= 0
	assert labels.get("tenant_id") == "tenant-otel-test"
	assert labels.get("jtbd_id") == "claim_intake"
