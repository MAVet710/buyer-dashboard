from modules.doobie_response import format_doobie_response


def test_complete_v4_response_is_visible_in_buyer_dash():
    rendered = format_doobie_response(
        {
            "answer": "Buy 14g Hybrid Flower.",
            "explanation": "Cover is below target.",
            "recommendations": ["Order 24 units"],
            "risk_flags": ["Three days of cover"],
            "inefficiencies": ["Duplicate low-velocity SKUs"],
            "confidence": "high",
            "sources": ["https://masscannabiscontrol.com"],
            "routed_mode": "buyer",
            "routed_by": "Detected from your question",
            "ai": {"provider": "groq", "model": "openai/gpt-oss-120b"},
        }
    )

    assert "Buy 14g Hybrid Flower" in rendered
    assert "Order 24 units" in rendered
    assert "Three days of cover" in rendered
    assert "Duplicate low-velocity SKUs" in rendered
    assert "masscannabiscontrol.com" in rendered
    assert "AI: groq / openai/gpt-oss-120b" in rendered


def test_clarification_and_unverified_rule_are_explicit():
    rendered = format_doobie_response(
        {
            "answer": "Which state are you operating in?",
            "needs_clarification": True,
            "missing_context": ["jurisdiction", "license_type"],
            "rule_verified": False,
            "compliance_context": {"code": None},
        }
    )

    assert "More context needed" in rendered
    assert "jurisdiction, license_type" in rendered
    assert "Exact rule not verified" in rendered
