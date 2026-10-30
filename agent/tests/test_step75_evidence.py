import asyncio
import json

import pytest

from bankops_agent.rca.analysis import RCAAnalyzer, evidence_catalog
from bankops_agent.workflow import build_workflow, run_workflow
from test_airflow import collector, documents
from test_investigation import state
from test_logs import collect, event


def test_native_info_requires_opt_in_and_is_not_warning_evidence(tmp_path):
    row = event(log={'level': 'INFO', 'logger': 'com.bankops.banking.observability.SafeEventLogger'})
    assert collect(tmp_path, [row]).events == []
    logs = collect(tmp_path, [row], log_include_info=True)
    assert logs.events[0].level == 'INFO'
    assert 'PRIVATE' not in logs.model_dump_json()
    from bankops_agent.investigation import investigate
    sources = state()
    from test_investigation import Source
    sources.log_collector = Source(logs)
    report = asyncio.run(investigate(sources))
    assert not any(row.source == 'log' for row in evidence_catalog(report))


@pytest.mark.parametrize('code,kind', [('FAIL', 'reconciliation_integrity_failure'),
    ('INSUFFICIENT_DATA', 'reconciliation_evidence_gap')])
@pytest.mark.parametrize('invented', [False, True])
def test_reconciliation_requires_current_and_retrieved_grounding(code, kind, invented):
    source, _ = collector(documents(code), rag_enabled=True)
    sources = state()
    sources.settings, sources.airflow_collector = source.settings, source

    class MockedProvider:
        async def analyze(self, evidence, schema):
            current = next(row for row in evidence['observations'] if kind in row['supports'])
            doc = next(row for row in evidence['retrieved_sources'] if kind in row['supports'])
            return json.dumps({'hypotheses': [{'kind': kind, 'confidence': 'low',
                'supporting_evidence': [current['id']], 'retrieved_sources': ['invented' if invented else doc['id']]}],
                'uncertainty': ['causality_unconfirmed'],
                'recommended_investigation_steps': ['collect_additional_evidence']}).encode()

    sources.rca_analyzer = RCAAnalyzer(source.settings, MockedProvider())
    report = asyncio.run(run_workflow(build_workflow(sources)))
    assert report.rca.reason == ('invalid_output' if invented else 'supported_hypotheses')
    assert report.rca.root_cause_confirmed is False


def test_airflow_explicit_ca_preserves_hostname_and_certificate_verification(tmp_path, monkeypatch):
    import ssl
    import bankops_agent.evidence.airflow as module
    path = tmp_path / 'fixture-ca.pem'
    path.write_text('synthetic CA fixture; parsing mocked only in this unit test')
    original = ssl.create_default_context
    seen = []

    def context(*, cafile):
        value = original()
        assert value.check_hostname and value.verify_mode == ssl.CERT_REQUIRED
        seen.append(cafile)
        return value

    monkeypatch.setattr(module.ssl, 'create_default_context', context)
    source, calls = collector(documents(), airflow_ca_file=str(path))
    assert asyncio.run(source.collect()).status == 'ok'
    assert seen == [str(path)] and len(calls) == 3


@pytest.mark.parametrize('path', ['relative-ca.pem', '//untrusted/share/cert.pem'])
def test_airflow_rejects_untrusted_ca_paths_before_transport(path):
    source, calls = collector(documents(), airflow_ca_file=path)
    assert asyncio.run(source.collect()).status == 'invalid_response'
    assert not calls
