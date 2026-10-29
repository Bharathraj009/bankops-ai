"""GET-only Airflow v2 collector. Unknown upstream strings never enter evidence."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Literal
from urllib.parse import quote

import httpx2 as httpx
from pydantic import BaseModel, ConfigDict

DAG = 'bankops_daily_reconciliation'
TASKS = ('validate_read_only_connectivity','execute_reconciliation','validate_results','execution_summary')
RULES = {'completed_double_entry','account_balances','ledger_consistency','lifecycle_ledger'}
STATES = {'success','failed','upstream_failed','queued','running','scheduled','up_for_retry','skipped','deferred','removed','restarting',None}


def unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result: raise ValueError()
        result[key] = value
    return result


class SafeModel(BaseModel):
    model_config = ConfigDict(frozen=True,extra='forbid')


class TaskStatus(SafeModel):
    task: Literal['validate_read_only_connectivity','execute_reconciliation','validate_results','execution_summary']
    state: Literal['success','failed','upstream_failed','queued','running','scheduled','up_for_retry','skipped','deferred','removed','restarting'] | None


class RuleSummary(SafeModel):
    rule: Literal['completed_double_entry','account_balances','ledger_consistency','lifecycle_ledger']
    violations: int


class RunEvidence(SafeModel):
    # Run IDs are used only for fixed-resource lookups and are never returned.
    observed_at: datetime
    state: Literal['success','failed','queued','running']
    outcome: Literal['pass','financial_violations','task_failure','insufficient_data','in_progress']
    summary_status: Literal['PASS','FAIL','INSUFFICIENT_DATA'] | None = None
    checks: tuple[RuleSummary,...] = ()
    tasks: tuple[TaskStatus,...] = ()


class AirflowEvidence(SafeModel):
    source: Literal['airflow'] = 'airflow'
    dag: Literal['bankops_daily_reconciliation'] = DAG
    collected_at: datetime
    status: Literal['disabled','ok','partial','missing','unavailable','timeout','invalid_response']
    truncated: bool = False
    runs: tuple[RunEvidence,...] = ()


def timestamp(value):
    if not isinstance(value,str) or len(value) > 40: raise ValueError()
    result = datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None: raise ValueError()
    return result


def summary(value,start,end):
    if not isinstance(value,dict) or set(value) != {'started_at','completed_at','status','reason','checks'}:
        raise ValueError()
    a,b = timestamp(value['started_at']),timestamp(value['completed_at'])
    if not start <= a <= b <= end: raise ValueError()
    status = value['status']
    rows = value['checks']
    if not isinstance(rows,list) or len(rows) > 4: raise ValueError()
    if status == 'INSUFFICIENT_DATA':
        if rows or value['reason'] != 'source_unavailable_or_incompatible': raise ValueError()
        return status,()
    if status not in ('PASS','FAIL') or value['reason'] != 'snapshot_checked' or len(rows) != 4: raise ValueError()
    result = []
    for row in rows:
        if set(row) != {'rule','status','violations'} or row['rule'] not in RULES: raise ValueError()
        n = row['violations']
        if type(n) is not int or not 0 <= n <= 1000000 or row['status'] != ('FAIL' if n else 'PASS'): raise ValueError()
        result.append(RuleSummary(rule=row['rule'],violations=n))
    if {r.rule for r in result} != RULES or status != ('FAIL' if any(r.violations for r in result) else 'PASS'): raise ValueError()
    return status,tuple(result)


class AirflowCollector:
    def __init__(self,settings,*,transport=None):
        self.settings,self.transport = settings,transport

    async def collect(self):
        now = datetime.now(UTC)
        result = lambda status,**kw:AirflowEvidence(collected_at=now,status=status,**kw)
        if not self.settings.airflow_enabled: return result('disabled')
        runs = []
        try:
            async with asyncio.timeout(self.settings.airflow_timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport,trust_env=False,follow_redirects=False,
                    timeout=self.settings.airflow_timeout_seconds,
                    headers={'Authorization':'Bearer '+self.settings.airflow_api_token.get_secret_value()}) as client:
                    async def get(path,params=None):
                        async with client.stream('GET',str(self.settings.airflow_url).rstrip('/')+'/api/v2/dags/'+DAG+path,params=params) as response:
                            if response.status_code == 404: return None
                            response.raise_for_status()
                            data=bytearray()
                            async for chunk in response.aiter_bytes():
                                if len(data)+len(chunk) > 262144: raise ValueError()
                                data.extend(chunk)
                            return json.loads(data,object_pairs_hook=unique_object)
                    lower = now - timedelta(seconds=self.settings.airflow_window_seconds)
                    listing = await get('/dagRuns',{'limit':self.settings.airflow_max_runs,'order_by':'-run_after','run_after_gte':lower.isoformat()})
                    if listing is None: return result('missing')
                    records = listing['dag_runs']
                    total = listing['total_entries']
                    if not isinstance(records,list) or len(records) > self.settings.airflow_max_runs or type(total) is not int or total < len(records): raise ValueError()
                    partial = total > len(records)
                    seen = set()
                    for row in records:
                        try:
                            identifier = row['dag_run_id']
                            if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_:+.\-]{1,200}',identifier) or identifier in ('.','..') or identifier in seen: raise ValueError()
                            seen.add(identifier)
                            observed = timestamp(row['run_after'])
                            if not lower <= observed <= now: continue
                            state = row['state']
                            if state not in ('success','failed','queued','running'): raise ValueError()
                            index = len(runs)
                            runs.append(RunEvidence(observed_at=observed,state=state,outcome='task_failure' if state == 'failed' else 'in_progress' if state in ('queued','running') else 'insufficient_data'))
                            path='/dagRuns/'+quote(identifier,safe='')
                            tasks = await get(path+'/taskInstances',{'limit':5})
                            if tasks is None: raise ValueError()
                            items = tasks['task_instances']
                            if not isinstance(items,list) or len(items) != 4 or tasks['total_entries'] != 4: raise ValueError()
                            statuses=[]
                            for task in items:
                                if task['task_id'] not in TASKS or task['state'] not in STATES: raise ValueError()
                                statuses.append(TaskStatus(task=task['task_id'],state=task['state']))
                            if {t.task for t in statuses} != set(TASKS): raise ValueError()
                            code,checks = None,()
                            if next(t.state for t in statuses if t.task == 'execute_reconciliation') == 'success':
                                execution = next(t for t in items if t['task_id'] == 'execute_reconciliation')
                                execution_start,execution_end = timestamp(execution['start_date']),timestamp(execution['end_date'])
                                if not lower <= execution_start <= execution_end <= now: raise ValueError()
                                xcom = await get(path+'/taskInstances/execute_reconciliation/xcomEntries/return_value')
                                if xcom is not None:
                                    code,checks=summary(xcom['value'],execution_start,execution_end)
                            if state in ('queued','running'): outcome='in_progress'
                            elif state == 'failed':
                                outcome = 'financial_violations' if code == 'FAIL' else 'insufficient_data' if code == 'INSUFFICIENT_DATA' else 'task_failure'
                            elif code == 'PASS' and all(t.state == 'success' for t in statuses): outcome='pass'
                            else: outcome='insufficient_data'
                            runs[index] = RunEvidence(observed_at=observed,state=state,outcome=outcome,summary_status=code,checks=checks,tasks=tuple(statuses))
                        except (ValueError,KeyError,TypeError,AttributeError,httpx.HTTPError):
                            partial=True
                    return result('partial' if partial else 'ok' if runs else 'missing',runs=tuple(runs),truncated=total > len(records))
        except (TimeoutError,httpx.TimeoutException): return result('timeout',runs=tuple(runs))
        except httpx.HTTPError: return result('unavailable',runs=tuple(runs))
        except (ValueError,KeyError,TypeError,AttributeError,RecursionError,OverflowError): return result('invalid_response',runs=tuple(runs))
