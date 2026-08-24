from services.ai.evals.cases import CASES, EvalCase
from services.ai.evals.scoring import score_case


def test_eval_cases_cover_every_registered_agent():
    from services.agent_registry import PROFILES

    covered = {case.agent for case in CASES}
    assert set(PROFILES).issubset(covered)


def test_deterministic_eval_requires_expected_tool_selection():
    case = EvalCase("tool", "inventory", "calculate", ("days",), deterministic=True, expected_tool="inventory_stockout_risk")
    missing = score_case(case, answer="days", structured_valid=True, tool_names=[])
    correct = score_case(case, answer="days", structured_valid=True, tool_names=["inventory_stockout_risk"])
    assert missing["tool_selection_valid"] is False
    assert missing["passed"] is False
    assert correct["tool_selection_valid"] is True
    assert correct["passed"] is True


def test_compliance_eval_accepts_refusal_when_authoritative_source_is_missing():
    case = EvalCase("compliance", "compliance", "is this compliant", ("cannot verify",), requires_grounding=True)
    result = score_case(case, answer="I cannot verify this from an authoritative source.", structured_valid=True, sources=[])
    assert result["retrieval_grounding"] is True
    assert result["passed"] is True
