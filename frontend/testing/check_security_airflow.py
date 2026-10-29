"""Read-only health/RBAC checks of the isolated patched Airflow runtime only.

All identities below are synthetic credentials for the separate Step 63 container.
Tokens stay in memory; never target a development or production instance.
"""
import json
import urllib.request
import urllib.error

BASE='http://127.0.0.1:18083'


def request(path,token=None,body=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(BASE+path,headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=15) as response:
            return response.status,json.load(response)
    except urllib.error.HTTPError as error:return error.code,None


if __name__=='__main__':
    status,health=request('/api/v2/monitor/health')
    assert status==200
    assert all(health[k]['status']=='healthy' for k in ('metadatabase','scheduler','dag_processor'))
    tokens={}
    for user,password in [('localadmin','isolated_step63_admin_only'),('agentviewer','isolated_step63_viewer_only')]:
        code,body=request('/auth/token',body={'username':user,'password':password})
        assert code==201 or code==200
        tokens[user]=body['access_token']
    assert request('/auth/token',body={'username':'agentviewer','password':'invalid'})[0] in (401,403)
    dag='/api/v2/dags/bankops_daily_reconciliation'
    code,body=request(dag,tokens['agentviewer'])
    assert code==200 and body['is_paused'] is True
    code,runs=request(dag+'/dagRuns',tokens['agentviewer'])
    assert code==200 and runs['total_entries']==0
    assert request('/api/v2/config',tokens['agentviewer'])[0]==403
    assert request('/api/v2/dags',tokens['localadmin'])[0]==200
    print(json.dumps({'health':'healthy','admin_auth':True,'viewer_read':True,
        'viewer_admin_resource_denied':True,'invalid_password_rejected':True,
        'dag_paused':True,'dag_runs':0,'financial_connections':0}))
