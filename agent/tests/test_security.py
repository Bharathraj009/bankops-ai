import hashlib
from fastapi.testclient import TestClient
import pytest
from bankops_agent.app import create_app
from bankops_agent.config import Settings

TOKEN = 'isolated-security-regression-token-only'
DIGEST = hashlib.sha256(TOKEN.encode()).hexdigest()


@pytest.mark.parametrize('settings', [Settings(environment='production'), Settings(host='0.0.0.0')])
def test_exposed_configuration_fails_closed(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get('/health').status_code == 200
        assert client.post('/workflows/investigate').status_code == 503
        assert client.get('/incidents/detect').status_code == 503
        assert client.get('/remediation/proposals/unused').status_code == 503


def test_deployment_token_does_not_grant_approval_roles():
    with TestClient(create_app(Settings(environment='production', api_token_sha256=DIGEST))) as client:
        assert client.get('/incidents/detect').status_code == 401
        # Auth succeeds; unknown resource stays 404, without an external call.
        response=client.get('/unknown',headers={'Authorization':'Bearer '+TOKEN})
        assert response.status_code == 404
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert 'x-correlation-id' in response.headers
        assert client.post('/remediation/proposals/x/approve',headers={'Authorization':'Bearer '+TOKEN},json={}).status_code == 503
        assert client.get('/unknown',headers=[('Authorization','Bearer '+TOKEN),('Authorization','Bearer '+TOKEN)]).status_code == 401


@pytest.mark.parametrize('headers',[
    {'Origin':'https://attacker.invalid'}, {'Origin':'null'},
    {'Host':'attacker.invalid'}, {'Sec-Fetch-Site':'cross-site'},
    {'Origin':'http://testserver@attacker.invalid'},
    {'Origin':'http://testserver?private=1'},
])
def test_browser_attacks_blocked_before_workflow(headers):
    with TestClient(create_app(Settings())) as client:
        response=client.post('/workflows/investigate',headers=headers)
        assert response.status_code == 403
        assert 'attacker' not in response.text
        assert 'access-control-allow-origin' not in response.headers


def test_same_origin_and_token_configuration():
    with TestClient(create_app(Settings())) as client:
        assert client.get('/health',headers={'Origin':'http://testserver'}).status_code == 200
    with pytest.raises(ValueError):Settings(api_token_sha256='short-private-value')
    with pytest.raises(ValueError):Settings(allowed_hosts=['*'])


def test_deployment_key_cannot_replace_proposer_or_reviewer(tmp_path):
    import secrets
    proposer, reviewer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    settings=Settings(environment='production',api_token_sha256=DIGEST,
        approval_db_path=str(tmp_path/'isolated.sqlite3'),
        approval_proposer_token_sha256=hashlib.sha256(proposer.encode()).hexdigest(),
        approval_reviewer_token_sha256=hashlib.sha256(reviewer.encode()).hexdigest())
    with TestClient(create_app(settings)) as client:
        created=client.post('/remediation/proposals',headers={'Authorization':'Bearer '+proposer},
            json={'action':'CHECK_SERVICE_HEALTH','evidence_references':['rule.banking_unavailable']})
        assert created.status_code == 201
        path='/remediation/proposals/'+created.json()['proposal_id']+'/approve'
        decision={'reason':'reviewed_evidence'}
        assert client.post(path,headers={'Authorization':'Bearer '+TOKEN},json=decision).status_code == 401
        assert client.post(path,headers={'Authorization':'Bearer '+proposer},json=decision).status_code == 403
        assert client.post(path,headers={'Authorization':'Bearer '+reviewer},json=decision).status_code == 200


@pytest.mark.parametrize('role',['proposer','reviewer'])
def test_deployment_and_approval_credential_reuse_rejected(tmp_path,role):
    hashes={'proposer':hashlib.sha256(b'isolated-proposer-credential').hexdigest(),
            'reviewer':hashlib.sha256(b'isolated-reviewer-credential').hexdigest()}
    with pytest.raises(ValueError):
        Settings(api_token_sha256=hashes[role],approval_db_path=str(tmp_path/'test.sqlite3'),
            approval_proposer_token_sha256=hashes['proposer'],approval_reviewer_token_sha256=hashes['reviewer'])
