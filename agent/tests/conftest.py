import io
import os

import pytest

from bankops_agent.logging import create_logger


@pytest.fixture(autouse=True)
def clean_agent_environment(monkeypatch):
    for key in list(os.environ):
        if key.upper().startswith("BANKOPS_AGENT_"):
            monkeypatch.delenv(key)


@pytest.fixture
def log_output():
    stream = io.StringIO()
    return create_logger(stream=stream), stream
