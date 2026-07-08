"""S-02 unknown expression operators cannot bypass fire() guards."""

from __future__ import annotations

import pytest

from flowforge import config
from flowforge.compiler import validate
from flowforge.dsl import WorkflowDef
from flowforge.engine import fire, new_instance
from flowforge.engine.fire import GuardEvaluationError
from flowforge.expr import EvaluationError, evaluate
from flowforge.ports.types import Principal


@pytest.fixture(autouse=True)
def reset_config() -> None:
	config.reset_to_fakes()


def _workflow_with_guard(expr: object) -> WorkflowDef:
	return WorkflowDef.model_validate(
		{
			"key": "s02_guard",
			"version": "1.0.0",
			"subject_kind": "case",
			"initial_state": "draft",
			"states": [
				{"name": "draft", "kind": "manual_review"},
				{"name": "approved", "kind": "terminal_success"},
			],
			"transitions": [
				{
					"id": "approve",
					"event": "approve",
					"from_state": "draft",
					"to_state": "approved",
					"guards": [{"kind": "expr", "expr": expr}],
				}
			],
		}
	)


@pytest.mark.asyncio
async def test_unknown_operator_in_guard_raises_in_strict_mode() -> None:
	wd = _workflow_with_guard({"unknown_op": [True]})
	report = validate(wd)
	assert any("Unknown operator: unknown_op" in error for error in report.errors)

	inst = new_instance(wd)
	with pytest.raises(GuardEvaluationError) as exc_info:
		await fire(wd, inst, "approve", principal=Principal(user_id="u"))

	assert isinstance(exc_info.value.__cause__, EvaluationError)
	assert "Unknown operator: unknown_op" in str(exc_info.value.__cause__)
	assert inst.state == "draft"
	assert inst.history == []


def test_unknown_operator_literal_dict_in_data_context() -> None:
	expr = {"greater_then": [{"var": "x"}, 0]}

	assert evaluate(expr, {"x": 1}) == expr


@pytest.mark.asyncio
async def test_typo_operator_cannot_pass_guard() -> None:
	expr = {"greater_then": [{"var": "x"}, 0]}
	wd = _workflow_with_guard(expr)
	inst = new_instance(wd, initial_context={"x": 1})

	with pytest.raises(GuardEvaluationError) as exc_info:
		await fire(wd, inst, "approve", principal=Principal(user_id="u"))

	assert "Unknown operator: greater_then" in str(exc_info.value.__cause__)
	assert inst.state == "draft"
	assert inst.history == []


def test_known_operators_still_work_in_strict_mode() -> None:
	ctx = {"x": 5}

	assert evaluate({"==": [{"var": "x"}, 5]}, ctx, strict_ops=True) is True
	assert evaluate({">": [{"var": "x"}, 0]}, ctx, strict_ops=True) is True
	assert evaluate({"<": [{"var": "x"}, 10]}, ctx, strict_ops=True) is True
	assert evaluate(
		{"and": [{"==": [{"var": "x"}, 5]}, {">": [{"var": "x"}, 0]}]},
		ctx,
		strict_ops=True,
	) is True
	assert evaluate(
		{"or": [{"<": [{"var": "x"}, 0]}, {"==": [{"var": "x"}, 5]}]},
		ctx,
		strict_ops=True,
	) is True
