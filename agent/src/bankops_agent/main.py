import logging.config

import uvicorn
from pydantic import ValidationError

from bankops_agent.app import create_app
from bankops_agent.config import Settings
from bankops_agent.logging import create_logger, emit_event


def run() -> None:
    try:
        settings = Settings()
    except ValidationError:
        emit_event(create_logger(), "configuration_invalid")
        raise SystemExit(2) from None
    # Suppress server access/exception diagnostics which can render paths and request details.
    logging.config.dictConfig({
        "version": 1, "disable_existing_loggers": True,
        "handlers": {"discard": {"class": "logging.NullHandler"}},
        "root": {"handlers": ["discard"], "level": "CRITICAL"},
    })
    logger = create_logger(settings.log_level)
    emit_event(logger, "service_started")
    uvicorn.run(create_app(settings, logger=logger), host=str(settings.host), port=settings.port,
                log_config=None, access_log=False, server_header=False)


if __name__ == "__main__":
    run()
