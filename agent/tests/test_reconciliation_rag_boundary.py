"""Reconciliation retrieval remains deterministic without external inference."""
import asyncio

from bankops_agent.rca.analysis import RCAAnalyzer
from bankops_agent.workflow import build_workflow, run_workflow
from test_airflow import collector, documents
from test_investigation import state


def test_reconciliation_incident_retrieves_reviewed_local_document_without_inference():
    source, calls = collector(documents('FAIL'), rag_enabled=True)
    sources = state()
    sources.settings = source.settings
    sources.airflow_collector = source

    sources.rca_analyzer = RCAAnalyzer(source.settings)
    report = asyncio.run(run_workflow(build_workflow(sources)))
    assert report.detection.state == 'incident'
    assert 'reconciliation_financial_violations' in report.detection.triggered_rules
    assert report.detection.airflow.runs[0].summary_status == 'FAIL'
    assert len(calls) == 3  # Authenticated mocked Airflow GETs, no real scheduler here.
    assert report.rca.retrieval.status == 'matched'
    assert report.rca.retrieval.sources[0].document_id == 'reconciliation'
    assert all(row.reviewed for row in report.rca.retrieval.sources)
    assert report.rca.reason == 'disabled'
    assert not report.rca.hypotheses and not report.rca.root_cause_confirmed
    assert sources.rca_analyzer.provider is None
