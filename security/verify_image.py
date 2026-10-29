"""Network-isolated agent image smoke test; no live endpoints/credentials."""

import json
import subprocess
import time
from uuid import uuid4


def main():
    name = "bankops-step66-image-" + uuid4().hex[:12]
    command = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--network",
        "none",
        "--name",
        name,
        "bankops-agent:step66-security",
    ]
    subprocess.run(command, check=True, capture_output=True)
    try:
        code = """
import json,os,urllib.request,urllib.error
assert os.getuid()==10001
assert not any(k in os.environ for k in ('BANKOPS_DB_PASSWORD','BANKOPS_DB_ADMIN_DSN','BANKOPS_MIGRATION_DB_PASSWORD','DATABASE_URL'))
def status(path):
    try:return urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=2).status
    except urllib.error.HTTPError as error:return error.code
assert status('/health')==200
assert status('/evidence/prometheus')==503
assert status('/remediation/proposals/00000000-0000-0000-0000-000000000000')==503
print(json.dumps({'non_root':True,'health':200,'private_api_fail_closed':503,'approvals_disabled':503,'banking_credentials_absent':True}))
"""
        for _ in range(40):
            result = subprocess.run(
                ["docker", "exec", "-i", name, "python", "-"],
                input=code,
                text=True,
                capture_output=True,
            )
            if result.returncode == 0:
                print(json.dumps(json.loads(result.stdout)))
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Isolated image smoke test failed; diagnostics suppressed")
    finally:
        subprocess.run(["docker", "stop", name], check=True, capture_output=True)


if __name__ == "__main__":
    main()
