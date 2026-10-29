"""Public dependency advisories only. No source or credentials leave the host."""

import json
from pathlib import Path
import runpy
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend/.cache/step66/dependency-audit.json"


def main():
    inventory = runpy.run_path(str(ROOT / "frontend/testing/security_inventory.py"))
    packages = inventory["inventory"]("bankops-airflow-step63-security:latest")
    if not any(p[0] == "Airflow runtime image" for p in packages):
        raise RuntimeError("Airflow runtime inventory missing")
    image = json.loads(
        subprocess.check_output(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "python",
                "bankops-agent:step66-security",
                "-m",
                "pip",
                "list",
                "--format=json",
            ],
            text=True,
        )
    )
    packages += [("built agent image", "PyPI", p["name"], p["version"]) for p in image]
    python = ROOT / "agent/.venv/Scripts/python.exe"
    installed = json.loads(
        subprocess.check_output(
            [str(python), "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
            text=True,
        )
    )
    packages += [
        ("agent installed environment", "PyPI", p["name"], p["version"]) for p in installed
    ]
    for name in ("database/requirements.txt", "security/requirements-dev.txt"):
        for line in (ROOT / name).read_text().splitlines():
            if "==" in line:
                package, version = line.split("==")
                packages.append((name, "PyPI", package.split("[")[0], version))
    packages = sorted(set(packages))
    queries = [
        {"package": {"ecosystem": ecosystem, "name": package}, "version": version}
        for _, ecosystem, package, version in packages
    ]
    request = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        data=json.dumps({"queries": queries}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        results = json.load(response)["results"]
    if len(results) != len(packages):
        raise RuntimeError("Incomplete advisory lookup")
    affected = [
        {
            "source": source,
            "package": package,
            "version": version,
            "advisories": [v["id"] for v in result.get("vulns", [])],
        }
        for (source, _, package, version), result in zip(packages, results, strict=True)
        if result.get("vulns")
    ]
    report = {
        "status": "FINDINGS" if affected else "PASS",
        "package_coordinates": len(queries),
        "affected": affected,
        "scope": "packaged Maven, agent/DB/tooling Python, built agent and patched Airflow images; npm audited separately",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "package_coordinates": len(queries),
                "affected": len(affected),
            }
        )
    )
    raise SystemExit(1 if affected else 0)


if __name__ == "__main__":
    main()
