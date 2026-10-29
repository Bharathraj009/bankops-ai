import json
from . import reconcile

if __name__ == '__main__':
    result = reconcile()
    print(json.dumps(result.to_dict()))
    raise SystemExit({'PASS':0, 'FAIL':1, 'INSUFFICIENT_DATA':2}[result.status])
