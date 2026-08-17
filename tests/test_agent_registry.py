from services.agent_registry import resolve_agent_profile


def test_top_level_workspace_agents_route_correctly():
    assert resolve_agent_profile("🏷️ White Label / Repack", "").key == "repack"
    assert resolve_agent_profile("🏭 Co-Man Production", "").key == "coman"
    assert resolve_agent_profile("🧪 Extraction Command Center", "").key == "extraction"
    assert resolve_agent_profile("📦 Orders & Fulfillment", "").key == "commercial"
    assert resolve_agent_profile("📥 Data Hub", "").key == "data_hub"


def test_buyer_subsections_get_specialists():
    mode = "🛒 Buyer Operations"
    assert resolve_agent_profile(mode, "📋 Inventory Counts").key == "audit"
    assert resolve_agent_profile(mode, "🧭 Compliance Q&A").key == "compliance"
    assert resolve_agent_profile(mode, "🏷️ Nomenclature Mapper").key == "nomenclature"
    assert resolve_agent_profile(mode, "🧾 PO Builder").key == "purchasing"
    assert resolve_agent_profile(mode, "💰 Purchasing Budget").key == "purchasing"
    assert resolve_agent_profile(mode, "📊 Inventory Dashboard").key == "inventory"
    assert resolve_agent_profile(mode, "🧠 Buyer Intelligence").key == "buyer"


def test_compliance_agent_requires_grounded_answers():
    profile = resolve_agent_profile("🛒 Buyer Operations", "🧭 Compliance Q&A")
    assert profile.compliance_grounded_only is True
