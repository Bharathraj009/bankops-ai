"""Opt-in isolated governance fixture. Never uses a banking DB or live sources.

Synthetic role secrets are generated into ignored .cache/step61/session.json, never
printed. Actual approval/execution/verification stores and API handlers are used.
Restart reuses this private test database and its state. Remove this fixture's
secrets after verification. No production configuration is modified.
"""
import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"agent"/"src"))
from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.remediation.models import ProposalCreate, ExecutionRequest
from bankops_agent.remediation.execution_store import ExecutionStore
from incident_agent import Metrics, Traces, Logs
import uvicorn


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-test-only',action='store_true',required=True)
    args=parser.parse_args()
    if not args.isolated_test_only: raise SystemExit(2)
    root=Path(__file__).resolve().parents[1]
    directory=root/'.cache'/'step61'
    directory.mkdir(parents=True,exist_ok=True)
    if directory.resolve()!=directory: raise SystemExit('Unsafe fixture directory')
    manifest=directory/'session.json'
    database=directory/'governance.sqlite3'
    if manifest.exists():
        session=json.loads(manifest.read_text())
        if not database.exists(): raise SystemExit('Missing fixture database')
    else:
        if database.exists(): raise SystemExit('Existing fixture database without session')
        session={'proposer':secrets.token_urlsafe(48),'reviewer':secrets.token_urlsafe(48),'ids':{}}
    settings=Settings(environment='test',llm_provider='disabled',llm_url=None,llm_api_key=None,
        approval_db_path=str(database),approval_proposer_token_sha256=hashlib.sha256(session['proposer'].encode()).hexdigest(),
        approval_reviewer_token_sha256=hashlib.sha256(session['reviewer'].encode()).hexdigest(),
        remediation_enabled=True,airflow_enabled=False)
    app=create_app(settings)
    app.app.state.prometheus_collector=Metrics()
    app.app.state.jaeger_collector=Traces()
    app.app.state.log_collector=Logs()
    store=app.app.state.approval_store
    if store is None: raise SystemExit('Fixture storage unavailable')
    if not session['ids']:
        for name,action in [('health','CHECK_SERVICE_HEALTH'),('evidence','REFRESH_INCIDENT_EVIDENCE'),('reject','CHECK_SERVICE_HEALTH'),('race','CHECK_SERVICE_HEALTH'),('concurrent','CHECK_SERVICE_HEALTH'),('running','CHECK_SERVICE_HEALTH'),('failed','CHECK_SERVICE_HEALTH'),('legacy','restart_banking_service')]:
            proposal=store.create(ProposalCreate(action=action,evidence_references=('rule.banking_unavailable',)))
            session['ids'][name]=str(proposal.proposal_id)
            if name in ('running','failed','legacy','concurrent'):
                store.decide(proposal.proposal_id,'APPROVED','reviewed_evidence')
            if name in ('running','failed'):
                executions=ExecutionStore(store)
                executions.claim(proposal.proposal_id,ExecutionRequest(action=action,parameters={'service':'banking-service'}))
                if name=='failed': executions.finish(proposal.proposal_id,'FAILED','timeout')
        fd=os.open(manifest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as target:json.dump(session,target)
    # Actual modules use only the in-memory collectors above; no banking/network IO.
    uvicorn.run(app,host='127.0.0.1',port=18062,access_log=False,log_config=None)


if __name__=='__main__':main()
