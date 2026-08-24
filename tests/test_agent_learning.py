from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, text

from services.agent_registry import PROFILES
from services.ai.datasets import DatasetSpec, LoadedDataset
from services.ai.feedback import AgentFeedbackStore
from services.ai.learning import AgentLearningEngine


def learning_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE ai_agent_learnings (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            facility_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            learning_key TEXT NOT NULL,
            learning_type TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            summary TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            sample_size INTEGER NOT NULL,
            confidence REAL NOT NULL,
            first_observed_at DATETIME NOT NULL,
            last_observed_at DATETIME NOT NULL,
            active BOOLEAN NOT NULL,
            UNIQUE(organization_id, facility_id, agent, learning_key)
        )""")
        connection.exec_driver_sql("""CREATE TABLE ai_agent_feedback (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            facility_id TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            agent TEXT NOT NULL,
            normalized_task_type TEXT NOT NULL,
            sanitized_prompt TEXT NOT NULL,
            tool_names_json TEXT NOT NULL,
            sanitized_tool_outcomes_json TEXT NOT NULL,
            answer TEXT NOT NULL,
            user_rating INTEGER NULL,
            corrected_answer TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            evaluation_score REAL NULL,
            training_approved BOOLEAN NOT NULL,
            learning_approved BOOLEAN NOT NULL,
            learning_approved_at DATETIME NULL
        )""")
        connection.exec_driver_sql("""CREATE TABLE ai_telemetry (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            facility_id TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            request_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            task_category TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            is_local BOOLEAN NOT NULL,
            latency_ms INTEGER NOT NULL,
            tool_call_count INTEGER NOT NULL,
            retrieval_count INTEGER NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            estimated_cost_usd REAL NOT NULL,
            fallback_used BOOLEAN NOT NULL,
            fallback_reason TEXT NOT NULL,
            validation_result TEXT NOT NULL,
            success BOOLEAN NOT NULL
        )""")
    return engine


def loaded(frame: pd.DataFrame, key: str = "history") -> LoadedDataset:
    spec = DatasetSpec(
        key=key,
        domain="test",
        description="historical test data",
        loader=lambda _context: frame,
        allowed_agents=tuple(PROFILES),
        allow_business_columns=True,
    )
    return LoadedDataset(spec=spec, frame=frame, freshness="test-history")


def test_learning_derives_aggregate_associations_without_sensitive_fields():
    frame = pd.DataFrame({
        "input_weight_g": [100 + i * 10 for i in range(20)],
        "finished_output_g": [20 + i * 2 for i in range(20)],
        "yield_pct": [20.0 for _ in range(20)],
        "employee_name": [f"person-{i}" for i in range(20)],
    })
    patterns = AgentLearningEngine(learning_engine()).derive_patterns({"extraction_runs": loaded(frame, "extraction_runs")})
    assert patterns
    assert any("input_weight_g" in row["summary"] and "finished_output_g" in row["summary"] for row in patterns)
    assert all("employee" not in row["summary"].casefold() for row in patterns)
    assert all(row["sample_size"] >= 8 for row in patterns)
    assert all("not proof of causation" in row["summary"] or "validate confounders" in row["summary"] for row in patterns)


def test_learning_is_tenant_facility_and_agent_scoped():
    engine = learning_engine()
    learning = AgentLearningEngine(engine)
    frame = pd.DataFrame({
        "input_weight_g": [100 + i * 10 for i in range(20)],
        "finished_output_g": [20 + i * 2 for i in range(20)],
    })
    datasets = {"runs": loaded(frame, "runs")}
    assert learning.refresh(organization_id="org-a", facility_id="fac-a", agent="extraction", datasets=datasets) > 0

    same = learning.context(organization_id="org-a", facility_id="fac-a", agent="extraction")
    wrong_facility = learning.context(organization_id="org-a", facility_id="fac-b", agent="extraction")
    wrong_org = learning.context(organization_id="org-b", facility_id="fac-a", agent="extraction")
    wrong_agent = learning.context(organization_id="org-a", facility_id="fac-a", agent="buyer")
    assert same["patterns"]
    assert wrong_facility["patterns"] == []
    assert wrong_org["patterns"] == []
    assert wrong_agent["patterns"] == []


def test_corrections_require_learning_approval_without_granting_training_consent():
    engine = learning_engine()
    feedback = AgentFeedbackStore(engine)
    learning = AgentLearningEngine(engine)
    row_id = feedback.save(
        organization_id="org-a",
        facility_id="fac-a",
        agent="buyer",
        task_type="reorder_review",
        sanitized_prompt="What should I order?",
        tool_names=["purchase_recommendations"],
        sanitized_tool_outcomes={},
        answer="Old answer",
        rating=2,
        corrected_answer="Use the approved purchasing policy and current open POs first.",
        provider="local",
        model="test",
    )
    assert learning.context(organization_id="org-a", facility_id="fac-a", agent="buyer")["approved_corrections"] == []
    assert feedback.set_learning_approved(row_id=row_id, organization_id="org-b", facility_id="fac-a", approved=True) is False
    assert feedback.set_learning_approved(row_id=row_id, organization_id="org-a", facility_id="fac-a", approved=True) is True

    buyer = learning.context(organization_id="org-a", facility_id="fac-a", agent="buyer")
    compliance = learning.context(organization_id="org-a", facility_id="fac-a", agent="buyer", compliance_agent=True)
    assert buyer["approved_corrections"][0]["approved_correction"].startswith("Use the approved purchasing policy")
    assert compliance["approved_corrections"] == []
    with engine.connect() as connection:
        row = connection.execute(text("SELECT learning_approved, training_approved FROM ai_agent_feedback WHERE id=:id"), {"id": row_id}).mappings().one()
    assert bool(row["learning_approved"]) is True
    assert bool(row["training_approved"]) is False
    assert feedback.export_approved(organization_id="org-a", facility_id="fac-a") == []


def test_telemetry_becomes_quality_learning_without_raw_prompt_data():
    engine = learning_engine()
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        for index in range(10):
            connection.execute(text("""
                INSERT INTO ai_telemetry
                (id,organization_id,facility_id,timestamp,request_id,agent,task_category,provider,model,is_local,latency_ms,tool_call_count,retrieval_count,input_tokens,output_tokens,estimated_cost_usd,fallback_used,fallback_reason,validation_result,success)
                VALUES (:id,:org,:facility,:ts,:request,:agent,:task,:provider,:model,:local,:latency,0,0,0,0,0,:fallback,'','ok',:success)
            """), {
                "id": f"t-{index}", "org": "org-a", "facility": "fac-a", "ts": now,
                "request": f"r-{index}", "agent": "buyer", "task": "agent_reasoning",
                "provider": "local", "model": "test-model", "local": True,
                "latency": 100 + index, "fallback": index == 9, "success": index != 8,
            })
    learning = AgentLearningEngine(engine)
    assert learning.refresh(organization_id="org-a", facility_id="fac-a", agent="buyer", datasets={}) == 1
    context = learning.context(organization_id="org-a", facility_id="fac-a", agent="buyer")
    telemetry = [row for row in context["patterns"] if row["source"] == "telemetry"]
    assert len(telemetry) == 1
    assert "10 AI requests" in telemetry[0]["summary"]
    assert "prompt" not in telemetry[0]["summary"].casefold()


def test_every_registered_agent_uses_the_same_learning_contract():
    engine = learning_engine()
    learning = AgentLearningEngine(engine)
    for key, profile in PROFILES.items():
        context = learning.context(
            organization_id="org",
            facility_id="facility",
            agent=key,
            compliance_agent=profile.compliance_grounded_only,
        )
        assert set(context) == {"patterns", "approved_corrections", "rules"}
        assert context["rules"]
        if profile.compliance_grounded_only:
            assert context["approved_corrections"] == []
