from __future__ import annotations


def _dq_caution(payload: dict) -> str:
    dq = payload.get("data_quality", {}) or {}
    warns = []
    if int(dq.get("rows_needing_review", 0)) > 0:
        warns.append("rows needing review")
    if int(dq.get("missing_category_count", 0)) > 0:
        warns.append("missing categories")
    if int(dq.get("missing_price_count", 0)) > 0:
        warns.append("missing pricing")
    if not warns:
        return ""
    return f" Data quality includes {', '.join(warns)}, so findings should be treated directionally where noted."


def build_market_read(payload) -> str:
    return "Competitor menus show clear pressure in core shopped categories, with depth and promotional activity concentrated where buyers compete for routine basket share." + _dq_caution(payload)


def build_price_intelligence_narrative(payload) -> str:
    return "Price pressure is uneven by segment. Prioritize subcategories where competitor average pricing is sustainably below our current position before broad pricing actions."


def build_assortment_narrative(payload) -> str:
    return "Assortment risk is highest where competitor SKU depth and package-size breadth exceed our current offer. Where we hold depth advantages, use placement and feature strategy before discounting."


def build_promo_pressure_narrative(payload) -> str:
    return "Promotional intensity is concentrated in specific subcategories rather than market-wide. Monitor velocity impact and avoid reflexive margin giveback in low-pressure segments."


def build_opportunity_risk_narrative(payload) -> str:
    return "Highest-value opportunities appear in competitor-heavy segments with weak overlap to our current menu, while near-term risk sits in subcategories where we are both lighter and higher priced."


def build_data_quality_narrative(payload) -> str:
    return "Saved HTML snapshots support directional competitor intelligence. Embedded-menu shell captures and missing fields should be resolved before making final depth conclusions."


def build_executive_recommendations(payload) -> list[str]:
    return [
        "Protect margin by targeting price moves only in subcategories with confirmed competitor pressure.",
        "Close high-risk assortment gaps where competitor depth materially exceeds ours.",
        "Use feature strategy to amplify our depth advantages before adding discount dependency.",
    ]
