"""DMN (Decision Model and Notation) decision table evaluator.

Provides a simplified DMN 1.3-compatible decision table engine for
embedding rule-based decisions inside workflow guards and effects.

Usage::

    from flowforge.dmn import DmnTable, DmnRule, DmnCondition, evaluate_dmn

    table = DmnTable(
        id="loan_eligibility",
        name="Loan Eligibility",
        hit_policy=HitPolicy.FIRST,
        rules=[
            DmnRule(
                id="r1",
                conditions=[
                    DmnCondition(field="applicant.credit_score", op="ge", value=700),
                    DmnCondition(field="applicant.income", op="ge", value=50000),
                ],
                outputs={"eligible": True, "max_amount": 100000},
            ),
            DmnRule(
                id="r2",
                conditions=[
                    DmnCondition(field="applicant.credit_score", op="lt", value=700),
                ],
                outputs={"eligible": False, "max_amount": 0},
            ),
        ],
    )

    results = evaluate_dmn(table, context={"applicant": {"credit_score": 750, "income": 60000}})
    # results == [{"eligible": True, "max_amount": 100000}]
"""

from .evaluator import evaluate_dmn, evaluate_dmn_single
from .models import DmnCondition, DmnRule, DmnTable, HitPolicy

__all__ = [
	"DmnCondition",
	"DmnRule",
	"DmnTable",
	"HitPolicy",
	"evaluate_dmn",
	"evaluate_dmn_single",
]
