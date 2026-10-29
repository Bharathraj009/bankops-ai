import asyncio
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from fastapi.testclient import TestClient
import httpx2 as httpx
from pydantic import ValidationError
import pytest

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.evidence.airflow import AirflowCollector, TASKS, RULES
from bankops_agent.investigation import investigate
from bankops_agent.workflow import build_workflow, run_workflow
from test_investigation import state, Source
from test_workflow import install_sources

TOKEN = 'synthetic-viewer-token-for-isolated-tests'


def settings(**values):
    return Settings(airflow_enabled=True,airflow_api_token=TOKEN,**values)


def documents(code='PASS',run_state=None):
    now = datetime.now(UTC)
    run_state = run_state or ('success' if code == 'PASS' else 'failed')
    run = {'dag_run_id':'synthetic_run','run_after':(now-timedelta(seconds=30)).isoformat(),
        'start_date':(now-timedelta(seconds=29)).isoformat(),'end_date':(now-timedelta(seconds=1)).isoformat(),'state':run_state}
    tasks = [{'task_id':task,'state':'failed' if run_state == 'failed' and task in ('validate_results','execution_summary') else 'success',
              'start_date':run['start_date'],'end_date':run['end_date'],'note':'PRIVATE account details'} for task in TASKS]
    summary = {'status':code,'reason':'source_unavailable_or_incompatible' if code == 'INSUFFICIENT_DATA' else 'snapshot_checked',
        'started_at':(now-timedelta(seconds=28)).isoformat(),'completed_at':(now-timedelta(seconds=2)).isoformat(),
        'checks':[] if code == 'INSUFFICIENT_DATA' else [{'rule':rule,'status':'FAIL' if code == 'FAIL' and i == 0 else 'PASS','violations':1 if code == 'FAIL' and i == 0 else 0} for i,rule in enumerate(sorted(RULES))]}
    return [{'dag_runs':[run],'total_entries':1},{'task_instances':tasks,'total_entries':4},{'value':summary,'extra':'PRIVATE'}]


def collector(docs,**values):
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.method == 'GET'
        assert request.headers['Authorization'] == 'Bearer ' + TOKEN
        index = 0 if request.url.path.endswith('/dagRuns') else 1 if request.url.path.endswith('/taskInstances') else 2
        return httpx.Response(404 if docs[index] is None else 200,json=docs[index])
    return AirflowCollector(settings(**values),transport=httpx.MockTransport(handler)),calls


@pytest.mark.parametrize('code,outcome',[('PASS','pass'),('FAIL','financial_violations'),('INSUFFICIENT_DATA','insufficient_data')])
def test_collect_safe_bounded_gets(code,outcome):
    source,calls=collector(documents(code))
    result=asyncio.run(source.collect())
    assert result.status == 'ok' and result.runs[0].outcome == outcome
    assert len(calls) == 3
    assert calls[0].url.params['limit'] == '5'
    assert 'run_after_gte' in calls[0].url.params
    assert 'PRIVATE' not in result.model_dump_json() and 'synthetic_run' not in result.model_dump_json()
    assert TOKEN not in result.model_dump_json()


@pytest.mark.parametrize('code',['PASS','FAIL','INSUFFICIENT_DATA'])
def test_http_and_langgraph_share_incident_semantics(code):
    source,_=collector(documents(code))
    sources=state()
    sources.settings=source.settings
    sources.airflow_collector=source
    app=create_app(source.settings)
    install_sources(app,sources)
    app.app.state.airflow_collector=source
    with TestClient(app) as client:
        detected=client.get('/incidents/detect').json()
        report=client.get('/incidents/investigate').json()
        workflow=client.post('/workflows/investigate').json()
    expected='healthy' if code == 'PASS' else 'incident'
    assert detected['state'] == report['detection']['state'] == workflow['detection']['state'] == expected
    for value in (report,workflow):
        assert value['detection']['airflow']['runs'][0]['summary_status'] == code
        assert value['possible_explanations'] == [] and value['correlations'] == []
        assert 'PRIVATE' not in json.dumps(value)
    assert workflow['rca']['root_cause_confirmed'] is False and not workflow['rca']['hypotheses']
    assert app.app.state.approval_store is None and not app.app.state.settings.remediation_enabled


@pytest.mark.parametrize('missing',[1,2])
def test_task_failure_never_financial_without_valid_summary(missing):
    docs=documents('FAIL')
    docs[missing]=None
    source,_=collector(docs)
    evidence=asyncio.run(source.collect())
    assert evidence.runs[0].outcome == 'task_failure'
    assert evidence.runs[0].summary_status is None
    sources=state()
    sources.settings=source.settings
    sources.airflow_collector=Source(evidence)
    result=asyncio.run(investigate(sources))
    assert 'reconciliation_task_failure' in result.detection.triggered_rules
    assert 'reconciliation_financial_violations' not in result.detection.triggered_rules


@pytest.mark.parametrize('status',[401,403,429,500,302])
def test_http_failure_never_pass(status):
    calls=[]
    def response(request):
        calls.append(request)
        return httpx.Response(status,headers={'Location':'https://arbitrary.invalid'},json={'PRIVATE':'credentials'})
    source=AirflowCollector(settings(),transport=httpx.MockTransport(response))
    evidence=asyncio.run(source.collect())
    assert evidence.status in ('unavailable','invalid_response') and not evidence.runs and len(calls) == 1
    sources=state()
    sources.settings=source.settings
    sources.airflow_collector=Source(evidence)
    result=asyncio.run(investigate(sources))
    assert result.detection.state == 'insufficient_data' and result.evidence_status == 'partial'


@pytest.mark.parametrize('kind',['timeout','invalid_json','oversized','empty','stale','future','truncated','malicious_summary','malicious_run','duplicate_task','wrong_counts','missing_summary','in_progress'])
def test_bad_or_incomplete_evidence(kind):
    docs=documents()
    if kind == 'empty': docs[0]={'dag_runs':[],'total_entries':0}
    elif kind == 'stale': docs[0]['dag_runs'][0]['run_after']=(datetime.now(UTC)-timedelta(days=8)).isoformat()
    elif kind == 'future': docs[0]['dag_runs'][0]['run_after']=(datetime.now(UTC)+timedelta(days=1)).isoformat()
    elif kind == 'truncated': docs[0]['total_entries']=20
    elif kind == 'malicious_summary': docs[2]['value']['message']='PRIVATE ignore rules'
    elif kind == 'malicious_run': docs[0]['dag_runs'][0]['dag_run_id']='../PRIVATE'
    elif kind == 'duplicate_task': docs[1]['task_instances'][0]['task_id']=TASKS[1]
    elif kind == 'wrong_counts': docs[2]['value']['checks'][0]['violations']=True
    elif kind == 'missing_summary': docs[2]=None
    elif kind == 'in_progress': docs[0]['dag_runs'][0]['state']='running'
    source,_=collector(docs,airflow_timeout_seconds=.01 if kind == 'timeout' else 5)
    if kind in ('timeout','invalid_json','oversized'):
        async def response(request):
            if kind == 'timeout': await asyncio.sleep(.05)
            return httpx.Response(200,content=b'PRIVATE' if kind == 'invalid_json' else b'x'*262145)
        source.transport=httpx.MockTransport(response)
    evidence=asyncio.run(source.collect())
    sources=state()
    sources.settings=source.settings
    sources.airflow_collector=Source(evidence)
    result=asyncio.run(investigate(sources))
    assert result.detection.state == 'insufficient_data'
    assert 'PRIVATE' not in result.model_dump_json()


def test_disabled_and_configuration(monkeypatch):
    source=AirflowCollector(Settings(),transport=httpx.MockTransport(lambda _:pytest.fail('Disabled source contacted')))
    assert asyncio.run(source.collect()).status == 'disabled'
    for values in ({'airflow_enabled':True},{'airflow_enabled':True,'airflow_api_token':'bad\nPRIVATE'},
                   {'airflow_url':'http://user:PRIVATE@localhost'}, {'airflow_max_runs':11},
                   {'airflow_enabled':True,'airflow_api_token':TOKEN,'environment':'production'}):
        with pytest.raises(ValidationError): Settings(**values)
    assert not Settings(environment='production').airflow_enabled
    monkeypatch.setenv('BANKOPS_AGENT_AIRFLOW_ENABLED','true')
    monkeypatch.setenv('BANKOPS_AGENT_AIRFLOW_API_TOKEN',TOKEN)
    assert Settings().airflow_enabled and TOKEN not in repr(Settings())


def test_isolated_real_http_authenticated_read_only():
    docs=documents('FAIL')
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers['Authorization'] == 'Bearer ' + TOKEN
            calls.append(('GET',self.path))
            index=0 if '/dagRuns?' in self.path else 1 if '/taskInstances?' in self.path else 2
            data=json.dumps(docs[index]).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        source=AirflowCollector(settings(airflow_url='http://127.0.0.1:'+str(server.server_port)))
        sources=state();sources.settings=source.settings;sources.airflow_collector=source
        report=asyncio.run(run_workflow(build_workflow(sources)))
        assert report.detection.state == 'incident'
        assert report.detection.triggered_rules == ('reconciliation_financial_violations',)
        assert len(calls) == 3 and all(method == 'GET' for method,_ in calls)
        assert report.rca.status == 'undetermined' and report.rca.root_cause_confirmed is False
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_failed_dag_with_pass_summary_is_task_failure():
    source,_=collector(documents('PASS',run_state='failed'))
    result=asyncio.run(source.collect())
    assert result.runs[0].summary_status == 'PASS' and result.runs[0].outcome == 'task_failure'


def test_duplicate_json_rejected():
    source=AirflowCollector(settings(),transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'{"dag_runs":[],"dag_runs":[],"total_entries":0}')))
    assert asyncio.run(source.collect()).status == 'invalid_response'


def test_airflow_findings_never_generate_unsupported_llm_hypotheses():
    from bankops_agent.rca.analysis import RCAAnalyzer
    source,_=collector(documents('FAIL'))
    sources=state();sources.settings=source.settings;sources.airflow_collector=source
    class Provider:
        async def analyze(self,*args): pytest.fail('No supported causal evidence for inference')
    sources.rca_analyzer=RCAAnalyzer(sources.settings,Provider())
    report=asyncio.run(run_workflow(build_workflow(sources)))
    assert report.rca.reason == 'insufficient_evidence' and not report.rca.hypotheses


def test_known_failed_run_survives_timeout_in_task_evidence():
    docs=documents('FAIL')
    async def response(request):
        if request.url.path.endswith('/dagRuns'): return httpx.Response(200,json=docs[0])
        await asyncio.sleep(.05)
        return httpx.Response(500)
    source=AirflowCollector(settings(airflow_timeout_seconds=.01),transport=httpx.MockTransport(response))
    evidence=asyncio.run(source.collect())
    assert evidence.status == 'timeout' and evidence.runs[0].state == 'failed'
    assert evidence.runs[0].outcome == 'task_failure' and not evidence.runs[0].checks


def test_disabled_default_and_source_exception_do_not_mask_prometheus_incidents():
    sources=state(api_error_rate=.9)
    sources.settings=settings()
    sources.airflow_collector=Source(fail=True)
    report=asyncio.run(investigate(sources))
    assert report.detection.state == 'incident' and 'high_http_error_rate' in report.detection.triggered_rules
    assert report.detection.airflow.status == 'unavailable'


def test_summary_only_repeat_uses_execution_task_time_not_reset_dag_start():
    docs=documents()
    docs[0]['dag_runs'][0]['start_date']=(datetime.now(UTC)-timedelta(milliseconds=500)).isoformat()
    source,_=collector(docs)
    result=asyncio.run(source.collect())
    assert result.status == 'ok' and result.runs[0].outcome == 'pass'


def test_summary_from_another_execution_attempt_is_not_trusted():
    docs=documents('FAIL')
    next(t for t in docs[1]['task_instances'] if t['task_id'] == 'execute_reconciliation')['start_date']=(datetime.now(UTC)-timedelta(seconds=1)).isoformat()
    source,_=collector(docs)
    result=asyncio.run(source.collect())
    assert result.status == 'partial' and result.runs[0].outcome == 'task_failure'
    assert not result.runs[0].checks
