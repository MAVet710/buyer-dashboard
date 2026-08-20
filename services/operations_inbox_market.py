"""Durable exception layer that turns Buyer Dash into an operating command center."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import sessionmaker

from modules.commercial_finance.models import CommercialInvoice
from modules.doobie_actions.models import ActionProposal
from modules.extraction.analytics import build_extraction_exceptions, build_run_board
from modules.migration_center.models import MigrationBatch
from modules.production_erp.service import ProductionERPService
from services.operations_inbox import InboxItem


class MarketOperationsInbox:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def build(self, organization_id: str, facility_id: str, *, limit: int = 12) -> list[InboxItem]:
        items: list[InboxItem] = []
        inspector = inspect(self.engine)
        tables = set(inspector.get_table_names())
        if "migration_batches" in tables:
            items.extend(self._migration_items(organization_id, facility_id))
        if "production_run_events" in tables:
            items.extend(self._production_items(organization_id, facility_id))
        if "commercial_invoices" in tables:
            items.extend(self._finance_items(organization_id, facility_id))
        if "action_proposals" in tables:
            items.extend(self._action_items(organization_id, facility_id))
        if "extraction_runs" in tables:
            items.extend(self._extraction_items(organization_id, facility_id))
        return sorted(items, key=lambda item: (-item.score, -item.financial_impact, item.title))[: max(1, limit)]

    def _migration_items(self, organization_id: str, facility_id: str) -> list[InboxItem]:
        with self._sessions() as session:
            rows = list(session.scalars(select(MigrationBatch).where(MigrationBatch.organization_id == organization_id, MigrationBatch.facility_id == facility_id, MigrationBatch.status == "review").order_by(MigrationBatch.created_at.desc()).limit(10)))
        result = []
        for row in rows:
            unresolved = int(row.review_records + row.unmapped_records + row.conflict_records)
            if unresolved <= 0:
                continue
            result.append(InboxItem(key=f"market:migration:{row.id}", area="Migration", title=f"{row.filename or row.entity_type.title()} cutover needs review", detail=f"{unresolved} record(s) are unresolved; Buyer Dash will not guess through the cutover.", severity="high", score=96 + min(10, unresolved / 10), financial_impact=0.0, action_label="Resolve Cutover", evidence=(f"Exact matches {row.matched_records}", f"Conflicts {row.conflict_records}", f"Unmapped {row.unmapped_records}")))
        return result

    def _production_items(self, organization_id: str, facility_id: str) -> list[InboxItem]:
        try:
            rows = ProductionERPService(self.engine).queue_summary(organization_id, facility_id)
        except Exception:
            return []
        result = []
        for row in rows:
            attention = str(row.get("Attention") or "")
            if attention == "Normal":
                continue
            qa = attention == "QA HOLD"
            impact = float(row.get("COGS") or 0)
            result.append(InboxItem(key=f"market:production:{row['order_id']}", area="Production", title=f"{row['Order']} · {attention}", detail=("Finished/WIP value is blocked behind QA." if qa else "The order has material requirements but no active reservations."), severity="critical" if qa else "high", score=105 if qa else 88, financial_impact=impact, action_label="Open Production", product_name=str(row.get("Product") or ""), evidence=(f"Planned {float(row.get('Planned') or 0):,.0f}", f"Tracked COGS ${impact:,.2f}")))
        return result

    def _finance_items(self, organization_id: str, facility_id: str) -> list[InboxItem]:
        today = date.today()
        with self._sessions() as session:
            invoices = list(session.scalars(select(CommercialInvoice).where(CommercialInvoice.organization_id == organization_id, CommercialInvoice.facility_id == facility_id, CommercialInvoice.status.notin_(("paid","void"))).order_by(CommercialInvoice.due_date).limit(50)))
        result = []
        for invoice in invoices:
            balance = float(invoice.balance_usd or 0)
            days = (today - invoice.due_date).days
            if days > 0:
                result.append(InboxItem(key=f"market:finance:{invoice.id}", area="Finance", title=f"{invoice.invoice_number} is {days} day(s) overdue", detail="Cash is outside terms and should be collected or reconciled.", severity="critical" if days > 30 else "high", score=102 if days > 30 else 90, financial_impact=balance, action_label="Open A/R", evidence=(f"Balance ${balance:,.2f}", f"Due {invoice.due_date.isoformat()}")))
            elif invoice.status == "draft":
                result.append(InboxItem(key=f"market:invoice-draft:{invoice.id}", area="Finance", title=f"{invoice.invoice_number} is still draft", detail="The order has an invoice but it has not been released to the customer.", severity="medium", score=68, financial_impact=balance, action_label="Review Invoice", evidence=(f"Balance ${balance:,.2f}",)))
        return result

    def _action_items(self, organization_id: str, facility_id: str) -> list[InboxItem]:
        with self._sessions() as session:
            proposals = list(session.scalars(select(ActionProposal).where(ActionProposal.organization_id == organization_id, ActionProposal.facility_id == facility_id, ActionProposal.status.in_(("proposed","approved","failed"))).order_by(ActionProposal.financial_impact_usd.desc()).limit(25)))
        result = []
        for proposal in proposals:
            severity = "high" if proposal.risk_level in {"high","compliance"} else "medium"
            score = 86 if proposal.status == "approved" else 74
            if proposal.status == "failed":
                severity, score = "critical", 104
            result.append(InboxItem(key=f"market:action:{proposal.id}", area="Doobie", title=proposal.title, detail=f"{proposal.status.title()} {proposal.action_type.replace('_',' ')} action · {proposal.risk_level} risk.", severity=severity, score=score, financial_impact=float(proposal.financial_impact_usd or 0), action_label="Review Action", evidence=(f"Status {proposal.status}", f"Impact ${float(proposal.financial_impact_usd or 0):,.2f}")))
        return result

    def _extraction_items(self, organization_id: str, facility_id: str) -> list[InboxItem]:
        try:
            board = build_run_board(self.engine, organization_id, facility_id, include_closed=False)
            exceptions = build_extraction_exceptions(board)
        except Exception:
            return []
        result = []
        for exception in exceptions[:10]:
            impact = 0.0
            if not board.empty and "run_id" in board.columns:
                match = board.loc[board["run_id"].astype(str) == str(exception.run_id)]
                if not match.empty:
                    impact = float(match.iloc[0].get("COGS") or 0)
            result.append(InboxItem(key=f"market:extraction:{exception.run_id}", area="Extraction", title=exception.title, detail=exception.detail, severity=exception.severity, score=float(exception.priority), financial_impact=impact, action_label="Open Run 360", evidence=(f"Run {exception.batch_number}", f"Tracked COGS ${impact:,.2f}")))
        return result


def build_market_operations_inbox(engine: Engine, organization_id: str, facility_id: str, *, limit: int = 12) -> list[InboxItem]:
    return MarketOperationsInbox(engine).build(organization_id, facility_id, limit=limit)
