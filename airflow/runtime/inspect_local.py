"""Read-only local health/discovery inspection; never print authentication material."""
from pathlib import Path
import json
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:18081'


def api(path, *, method='GET', body=None, token=None):
    headers = {'Content-Type':'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(BASE + path,headers=headers,method=method,
        data=None if body is None else json.dumps(body).encode())
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request,timeout=10) as response: return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError('Airflow HTTP status ' + str(error.code)) from None


def authenticate():
    values = dict(line.split('=',1) for line in (Path(__file__).resolve().parents[1] / '.env.local').read_text().splitlines() if '=' in line)
    return api('/auth/token',method='POST',body={'username':'localadmin','password':values['BANKOPS_AIRFLOW_UI_PASSWORD']})['access_token']


if __name__ == '__main__':
    print(json.dumps(api('/api/v2/monitor/health')))
    token = authenticate()
    data = api('/api/v2/dags',token=token)
    print(json.dumps([{'dag_id':d['dag_id'],'is_paused':d['is_paused']} for d in data['dags']]))
