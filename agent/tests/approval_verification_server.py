"""Subprocess fixture: local approval service, all outbound/execution attempts blocked."""

import asyncio
import json
import logging
import os
import platform
from pathlib import Path
import socket
import sys
from urllib.parse import urlsplit

import uvicorn

from bankops_agent.app import create_app
from bankops_agent.verify_rca import isolated_settings


async def main():
    root = Path(os.environ["APPROVAL_TEST_ROOT"])
    options = {}
    allowed_ports = set()
    if os.environ.get("APPROVAL_TEST_REMEDIATION") == "1":
        url = os.environ["APPROVAL_TEST_EVIDENCE_URL"]
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
            raise ValueError("Test evidence must be isolated loopback HTTP")
        allowed_ports.add(parsed.port)
        options.update(remediation_enabled=True, remediation_timeout_seconds=1,
            prometheus_url=url, prometheus_timeout_seconds=3, jaeger_url=url, jaeger_timeout_seconds=3,
            log_source_directory=str(root), log_source_filename="synthetic.jsonl")
    settings = isolated_settings(environment="test", approval_db_path=str(root / "approvals.sqlite3"),
        approval_proposer_token_sha256=os.environ["APPROVAL_TEST_PROPOSER_HASH"],
        approval_reviewer_token_sha256=os.environ["APPROVAL_TEST_REVIEWER_HASH"], **options)
    logging.disable(logging.CRITICAL)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    (root / "port.json").write_text(json.dumps({"port": listener.getsockname()[1]}), encoding="utf-8")
    app = create_app(settings)
    if sys.platform == "win32":
        # Python 3.12 platform.win32_ver can shell out to `cmd /c ver`.
        # Fixture-only platform metadata avoids that incidental subprocess;
        # the action-execution guard remains unconditional and unchanged.
        version = sys.getwindowsversion()
        platform.win32_ver = lambda *args, **kwargs: (
            "test", f"{version.major}.{version.minor}.{version.build}", "", "")
    def prohibit_effects(event, args):
        if event == "socket.connect":
            address = args[1]
            if isinstance(address, tuple) and address[0] == "127.0.0.1" and address[1] in allowed_ports:
                return
        if event in ("socket.connect", "subprocess.Popen", "os.system", "os.posix_spawn"):
            with (root / "forbidden-attempt.log").open("a", encoding="utf-8") as output:
                output.write("blocked_external_operation\n")
            raise PermissionError("External operations disabled in verification")
    # The event loop's own Windows socket pair is already initialized.
    sys.addaudithook(prohibit_effects)
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, lifespan="off"))
    await server.serve(sockets=[listener])


if __name__ == "__main__":
    asyncio.run(main())
