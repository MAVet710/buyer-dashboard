"""Regression gates for bounded Extraction reads and single-connection safety.
All records are synthetic and local. These tests never load production credentials.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from modules.coman.models import Base, Facility, InventoryLot, Organization, Product
from modules.extraction.models import (ExtractionRun, ExtractionRunInput, ExtractionRunOutput,
    ExtractionCostEvent, ExtractionQAEvent, ExtractionTollJob)
from modules.extraction.performance import ExtractionPerformanceService
from modules.extraction.performance_models import ExtractionResourceEvent
from modules.product_master.models import ProductValueEvent
from backend.app.routers.extraction_parity import overview


@pytest.fixture()
def case(tmp_path):
    engine = create_engine('sqlite+pysqlite:///' + str(tmp_path / 'isolated.db'),
        poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=0.05)
    Base.metadata.create_all(engine)
    with Session(engine) as s, s.begin():
        s.add_all([Organization(id='org-a', name='Synthetic A', slug='synthetic-a'),
                   Organization(id='org-b', name='Synthetic B', slug='synthetic-b')])
        s.flush()
        s.add_all([Facility(id=f, organization_id=o, name=f, code=f, production_enabled=True)
                   for f, o in [('fac-a', 'org-a'), ('fac-sibling', 'org-a'), ('fac-b', 'org-b')]])
        s.add(Product(id='prod-a', organization_id='org-a', sku='QA', name='Crude Oil',
            item_type='wip', base_unit='g', retail_price=12))
        s.add(Product(id='prod-source', organization_id='org-a', sku='BIO-QA', name='Biomass', item_type='cannabis', base_unit='g'))
        s.flush()
        s.add(InventoryLot(id='lot-a', organization_id='org-a', facility_id='fac-a',
            product_id='prod-source', lot_code='SYNTHETIC', status='available'))
        for rid, org, fac in [('run-a', 'org-a', 'fac-a'), ('run-sibling', 'org-a', 'fac-sibling'), ('run-b', 'org-b', 'fac-b')]:
            s.add(ExtractionRun(id=rid, organization_id=org, facility_id=fac, batch_number=rid,
                method='Ethanol', workflow_key='ethanol_crude', created_by='QA', updated_by='QA',
                manual_input_weight_g=80, manual_finished_output_g=8, manual_cogs_usd=15,
                estimated_revenue_usd=90))
        s.flush()
        s.add(ExtractionRunInput(id='input-a', organization_id='org-a', facility_id='fac-a',
            run_id='run-a', lot_id='lot-a', consumed_quantity=100, reserved_quantity=100,
            planned_quantity=100, unit='g', reserved_by='QA'))
        for i, status, quantity in [(1, 'quarantine', 20), (2, 'waste', 5), (3, 'destroyed', 7)]:
            s.add(ExtractionRunOutput(id=f'output-{i}', organization_id='org-a', facility_id='fac-a',
                run_id='run-a', product_id='prod-a', position=i, output_label=f'QA-{i}',
                quantity=quantity, unit='g', status=status, created_by='QA'))
        s.add(ExtractionCostEvent(organization_id='org-a', facility_id='fac-a', run_id='run-a',
            category='labor', amount_usd=40, actor='QA'))
        s.add(ExtractionQAEvent(organization_id='org-a', facility_id='fac-a', run_id='run-a',
            event_type='failure', result='failed', actor='QA'))
        s.add(ExtractionResourceEvent(organization_id='org-a', facility_id='fac-a', run_id='run-a',
            resource_type='solvent', resource_name='Synthetic', quantity=10, recovered_quantity=8,
            unit='g', cost_usd=5, actor='QA'))
    yield engine
    engine.dispose()


def _overview(engine, organization='org-a', facility='fac-a'):
    return overview(SimpleNamespace(organization_id=organization, facility_id=facility), engine)


def test_metrics_keep_resource_cost_with_only_one_connection(case):
    result = ExtractionPerformanceService(case).run_metrics('org-a', 'fac-a', 'run-a')
    assert result['resource_cost'] == 5
    assert result['solvent_recovery_pct'] == 80
    assert result['projected_output_value'] == 240
    assert case.pool.checkedout() == 0


def test_overview_preserves_mass_cogs_qa_and_scoping(case):
    result = _overview(case)
    assert len(result['runs']) == 1
    row = result['runs'][0]
    assert row['id'] == 'run-a'
    assert row['input_weight_g'] == 100
    assert row['finished_output_g'] == 25  # Existing mass contract includes waste, not destroyed.
    assert row['yield_pct'] == 25
    assert row['residual_loss_g'] == 75
    assert row['cogs_usd'] == 40
    assert row['cost_per_output_unit'] == 2
    assert row['est_revenue_usd'] == 240  # Valuation excludes waste and destroyed output.
    assert row['qa_hold'] is True and row['coa_status'] == 'Failed'
    assert _overview(case, facility='fac-sibling')['runs'][0]['id'] == 'run-sibling'
    assert _overview(case, organization='org-b', facility='fac-b')['runs'][0]['id'] == 'run-b'
    assert _overview(case, organization='org-b', facility='fac-a')['runs'] == []


def test_overview_query_budget_does_not_grow_per_run(case, record_property):
    queries = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)
    event.listen(case, 'before_cursor_execute', capture)
    try:
        _overview(case)
        one_run = len(queries)
        with Session(case) as s, s.begin():
            for i in range(30):
                s.add(ExtractionRun(organization_id='org-a', facility_id='fac-a', batch_number=f'BULK-{i}',
                    method='Ethanol', workflow_key='ethanol_crude', created_by='QA', updated_by='QA'))
        queries.clear()
        result = _overview(case)
        record_property('sql_statements_one_run', one_run)
        record_property('sql_statements_31_runs', len(queries))
        assert len(result['runs']) == 31
        assert one_run == 1, f'{one_run} SQL statements for one run'
        assert len(queries) == 1, f'{len(queries)} SQL statements for 31 runs'
        assert not any(q.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'ALTER', 'CREATE')) for q in queries)
        assert case.pool.checkedout() == 0
    finally:
        event.remove(case, 'before_cursor_execute', capture)


def test_overview_preserves_manual_fallback_and_empty_result(case):
    row = _overview(case, facility='fac-sibling')['runs'][0]
    assert (row['input_weight_g'], row['finished_output_g'], row['cogs_usd'], row['est_revenue_usd']) == (80, 8, 15, 90)
    empty = _overview(case, facility='does-not-exist')
    assert empty['runs'] == [] and empty['summary']['runs'] == 0


def test_detail_rejects_foreign_scope(case):
    with pytest.raises(ValueError):
        ExtractionPerformanceService(case).run_metrics('org-b', 'fac-b', 'run-a')


@pytest.mark.parametrize('wholesale,retail,expected', [(4, 9, 80), (0, 3, 60), (0, 0, 240)])
def test_valuation_uses_latest_event_then_existing_fallback(case, wholesale, retail, expected):
    now = datetime.now(timezone.utc)
    with Session(case) as s, s.begin():
        for kind, amount, when in [('wholesale_price', 99, now-timedelta(days=2)),
                ('wholesale_price', wholesale, now), ('retail_price', retail, now)]:
            s.add(ProductValueEvent(organization_id='org-a', product_id='prod-a',
                value_type=kind, amount=amount, effective_at=when, actor='QA'))
    assert _overview(case)['runs'][0]['est_revenue_usd'] == expected


def test_traceability_summary_counts_run_and_output_without_payloads(case):
    from modules.traceability.models import TraceabilityTransaction
    with Session(case) as s, s.begin():
        for i, kind, entity, org, fac in [
                (1, 'extraction_run', 'run-a', 'org-a', 'fac-a'),
                (2, 'extraction_output', 'output-1', 'org-a', 'fac-a'),
                (3, 'extraction_output', 'output-3', 'org-a', 'fac-a'),
                (4, 'extraction_run', 'run-b', 'org-b', 'fac-b')]:
            s.add(TraceabilityTransaction(organization_id=org, facility_id=fac,
                provider='metrc', operation_type='synthetic-review-only', entity_type=kind,
                entity_id=entity, idempotency_key=f'synthetic-{i}', requested_by='QA'))
    assert _overview(case)['runs'][0]['traceability_count'] == 3


def test_toll_summary_uses_existing_scoped_job(case):
    from modules.coman.models import Customer
    with Session(case) as s, s.begin():
        s.add(Customer(id='customer-a', organization_id='org-a', name='Synthetic client'))
        s.flush()
        s.add(ExtractionTollJob(organization_id='org-a', facility_id='fac-a', run_id='run-a',
            customer_id='customer-a', processing_fee_usd=25, created_by='QA'))
    result = _overview(case)
    assert result['summary']['toll_jobs'] == 1
    assert result['runs'][0]['toll_job']['processing_fee_usd'] == 25
    assert result['runs'][0]['toll_job']['invoice_status'] == 'Draft'


def test_missing_optional_resource_table_is_zero_without_an_extra_checkout(case):
    ExtractionResourceEvent.__table__.drop(case)  # This fixture owns a disposable SQLite DB only.
    assert ExtractionPerformanceService(case).run_metrics('org-a', 'fac-a', 'run-a')['resource_cost'] == 0
    assert case.pool.checkedout() == 0


def test_resource_probe_failure_is_not_silently_reported_as_zero(case, monkeypatch):
    import modules.extraction.performance as performance
    class BrokenInspector:
        def has_table(self, name):
            raise RuntimeError('Synthetic database read failure')
    monkeypatch.setattr(performance, 'inspect', lambda bind: BrokenInspector())
    with pytest.raises(RuntimeError, match='Synthetic database read failure'):
        ExtractionPerformanceService(case).run_metrics('org-a', 'fac-a', 'run-a')
    assert case.pool.checkedout() == 0


def test_overview_has_explicit_scope_and_batch_bounds(case):
    from modules.extraction.overview import load_extraction_overview
    with pytest.raises(ValueError):
        load_extraction_overview(case, '', 'fac-a')
    with pytest.raises(ValueError):
        load_extraction_overview(case, 'org-a', 'fac-a', limit=501)
    runs, facts = load_extraction_overview(case, 'org-a', 'fac-a', limit=1)
    assert len(runs) == len(facts) == 1
