from datetime import date

import pandas as pd

from services.operations_inbox import build_operations_inbox
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    DATA_HUB_WORKSPACE,
    INVENTORY_COUNTS_SECTION,
    METRC_INTEGRATIONS_SECTION,
)


def test_operations_inbox_prioritizes_compliance_then_stockout_then_data():
    state = {
        "metrc_sync_failures": [
            {"package": "PKG-1", "error": "rejected"},
            {"package": "PKG-2", "error": "timeout"},
        ],
        "detail_product_cached_df": pd.DataFrame(
            [
                {
                    "Product Name": "Critical Vape 1g",
                    "On Hand": 0,
                    "AvgUnitsPerDay": 3.0,
                    "Unit Cost": 18.0,
                },
                {
                    "Product Name": "Low Cover Flower 3.5g",
                    "On Hand": 8,
                    "AvgUnitsPerDay": 2.0,
                    "DaysOnHand": 4.0,
                    "Unit Cost": 17.0,
                },
            ]
        ),
    }
    status_rows = [
        {"Source": "Inventory", "Status": "Ready"},
        {"Source": "Product Sales", "Status": "Missing"},
    ]

    items = build_operations_inbox(
        state,
        status_rows=status_rows,
        today=date(2026, 8, 20),
    )

    assert items[0].key == "metrc-sync-failures"
    assert items[0].route_section == METRC_INTEGRATIONS_SECTION
    assert items[1].key == "stockout:critical vape 1g"
    assert items[1].route_workspace == BUYER_WORKSPACE
    assert any(item.key == "data-readiness" and item.route_workspace == DATA_HUB_WORKSPACE for item in items)


def test_operations_inbox_detects_expiration_and_late_purchase_orders():
    state = {
        "detail_product_cached_df": pd.DataFrame(
            [
                {
                    "Product Name": "Expiring Gummies 100mg",
                    "On Hand": 20,
                    "AvgUnitsPerDay": 0.5,
                    "DaysOnHand": 40,
                    "Unit Cost": 6.0,
                    "Expiration Date": "2026-08-30",
                }
            ]
        ),
        "demo_commercial_orders_df": pd.DataFrame(
            [
                {
                    "Order Type": "purchase",
                    "Status": "confirmed",
                    "Order Number": "PO-1007",
                    "Vendor": "Demo Vendor",
                    "Order Value": 2400.0,
                    "Due Date": "2026-08-17",
                }
            ]
        ),
    }

    items = build_operations_inbox(state, today=date(2026, 8, 20))

    expiry = next(item for item in items if item.key == "expiry:expiring gummies 100mg")
    assert expiry.severity == "high"
    assert expiry.financial_impact == 120.0
    assert "10 days" in expiry.title

    late_po = next(item for item in items if item.key == "late-po:po 1007")
    assert late_po.severity == "high"
    assert late_po.financial_impact == 2400.0
    assert "3 day(s) late" in late_po.title
    assert late_po.route_section == "🚚 Delivery Impact"


def test_operations_inbox_preserves_resume_audit_route_and_limit():
    state = {
        "inventory_audit_active": {"id": "audit-1"},
        "detail_product_cached_df": pd.DataFrame(
            [
                {
                    "Product Name": f"Low Cover {index}",
                    "On Hand": 1,
                    "AvgUnitsPerDay": 1.0,
                    "DaysOnHand": 1.0,
                }
                for index in range(10)
            ]
        ),
    }

    items = build_operations_inbox(state, today=date(2026, 8, 20), limit=5)

    assert len(items) == 5
    audit_items = build_operations_inbox(
        {"inventory_audit_active": {"id": "audit-1"}},
        today=date(2026, 8, 20),
    )
    assert audit_items[0].route_section == INVENTORY_COUNTS_SECTION
    assert audit_items[0].action_label == "Resume Audit"


def test_operations_inbox_supports_legacy_compact_buyer_cache_columns():
    state = {
        "detail_product_cached_df": pd.DataFrame(
            [
                {
                    "product_name": "Legacy Cache Flower 3.5g",
                    "onhandunits": 12,
                    "avgunitsperday": 2.0,
                    "daysonhand": 6.0,
                    "unit_cost": 20.0,
                    "days_to_expire": 20,
                }
            ]
        )
    }

    items = build_operations_inbox(state, today=date(2026, 8, 20))
    keys = {item.key for item in items}

    assert "stockout:legacy cache flower 3 5g" not in keys
    assert "low-cover:legacy cache flower 3 5g" in keys
    assert "expiry:legacy cache flower 3 5g" in keys
