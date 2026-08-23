"""Focused tests for analytics profitability module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from modules.analytics.service import ProfitabilityAnalyticsService
from modules.commercial_finance.models import CommercialInvoice, CommercialInvoiceLine
from modules.extraction.models import ExtractionCostEvent, ExtractionRun
from modules.production_erp.models import ProductionCostEvent


class MockSession:
    """Mock SQLAlchemy session for testing."""

    def __init__(self):
        self.scalars_result = []
        self.scalar_result = None
        self.execute_result = []

    def scalar(self, stmt):
        return self.scalar_result

    def scalars(self, stmt):
        return MockScalars(self.scalars_result)

    def execute(self, stmt):
        return MockExecute(self.execute_result)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockScalars:
    def __init__(self, results):
        self.results = results

    def all(self):
        return self.results


class MockExecute:
    def __init__(self, results):
        self.results = results

    def fetchall(self):
        return self.results


@pytest.fixture
def mock_engine():
    """Create a mock SQLAlchemy engine."""
    return MagicMock()


@pytest.fixture
def analytics_service(mock_engine):
    """Create an analytics service with mocked engine."""
    return ProfitabilityAnalyticsService(mock_engine)


def test_analytics_service_initialization(analytics_service):
    """Test that analytics service initializes correctly."""
    assert analytics_service is not None
    assert analytics_service.engine is not None


def test_supply_chain_margin_no_data(analytics_service):
    """Test supply chain margin calculation with no data."""
    with patch.object(analytics_service, '_sessions') as mock_sessions_factory:
        mock_session = MockSession()
        mock_session.scalar_result = 0.0
        mock_sessions_factory.return_value.__enter__ = lambda self: mock_session
        mock_sessions_factory.return_value.__exit__ = lambda *args: None

        result = analytics_service.supply_chain_margin("org1", "fac1", 30)

        assert result["total_revenue"] == 0.0
        assert result["total_cogs"] == 0.0
        assert result["gross_margin"] == 0.0
        assert result["gross_margin_pct"] == 0.0
        assert result["period_days"] == 30


def test_production_cost_analysis_no_data(analytics_service):
    """Test production cost analysis with no data."""
    with patch.object(analytics_service, '_sessions') as mock_sessions_factory:
        mock_session = MockSession()
        mock_session.execute_result = []
        mock_sessions_factory.return_value.__enter__ = lambda self: mock_session
        mock_sessions_factory.return_value.__exit__ = lambda *args: None

        result = analytics_service.production_cost_analysis("org1", "fac1", 30)

        assert result["total_production_cost"] == 0.0
        assert result["breakdown"] == {}
        assert result["period_days"] == 30


def test_extraction_efficiency_no_runs(analytics_service):
    """Test extraction efficiency with no completed runs."""
    with patch.object(analytics_service, '_sessions') as mock_sessions_factory:
        mock_session = MockSession()
        mock_session.scalars_result = []
        mock_sessions_factory.return_value.__enter__ = lambda self: mock_session
        mock_sessions_factory.return_value.__exit__ = lambda *args: None

        result = analytics_service.extraction_efficiency("org1", "fac1", 30)

        assert result["completed_runs"] == 0
        assert result["avg_yield_pct"] == 0
        assert result["avg_cost_per_output_unit"] == 0
        assert result["period_days"] == 30


def test_product_profitability_no_sales(analytics_service):
    """Test product profitability with no sales."""
    with patch.object(analytics_service, '_sessions') as mock_sessions_factory:
        mock_session = MockSession()
        mock_session.execute_result = []
        mock_sessions_factory.return_value.__enter__ = lambda self: mock_session
        mock_sessions_factory.return_value.__exit__ = lambda *args: None

        result = analytics_service.product_profitability("org1", "fac1", 30)

        assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
