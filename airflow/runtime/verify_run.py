"""Explicit opt-in, single persisted manual verification run; no financial writes."""
import argparse
from datetime import UTC, datetime
from pathlib import Path
import json

from inspect_local import api, authenticate

DAG = '/api/v2/dags/bankops_daily_reconciliation'
STATE = Path(__file__).resolve().parents[1] / '.local-run.json'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trigger-once',action='store_true')
    options = parser.parse_args()
    token = authenticate()
    if not STATE.exists():
        if not options.trigger_once: raise SystemExit('Use --trigger-once for one manual verification run')
        identifier = 'step55_' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S')
        # Persist before sending: a failed request must be inspected, never blindly retried.
        STATE.write_text(json.dumps({'run_id':identifier}))
        api(DAG,method='PATCH',body={'is_paused':False},token=token)
        api(DAG + '/dagRuns',method='POST',body={'dag_run_id':identifier,'logical_date':None,'conf':{}},token=token)
    identifier = json.loads(STATE.read_text())['run_id']
    run = api(DAG + '/dagRuns/' + identifier,token=token)
    instances = api(DAG + '/dagRuns/' + identifier + '/taskInstances',token=token)['task_instances']
    result = {'run_id':identifier,'state':run['state'],'tasks':[
        {k:t.get(k) for k in ('task_id','state','try_number','start_date','end_date')} for t in instances]}
    if run['state'] in ('success','failed'):
        api(DAG,method='PATCH',body={'is_paused':True},token=token)
        result['dag_paused_after_verification'] = True
    print(json.dumps(result))


if __name__ == '__main__': main()
