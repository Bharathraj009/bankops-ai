"""ASGI correlation scope, including framework-generated error responses."""

import logging
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bankops_agent.logging import UUID_PATTERN, correlation_id, emit_event


class CorrelationMiddleware:
    def __init__(self, app: ASGIApp, logger: logging.Logger) -> None:
        self.app = app
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        values = [value for name, value in scope.get("headers", []) if name.lower() == b"x-correlation-id"]
        supplied = values[0].decode("latin-1") if len(values) == 1 and len(values[0]) == 36 else ""
        identifier = supplied.lower() if UUID_PATTERN.fullmatch(supplied) else str(uuid4())
        token = correlation_id.set(identifier)
        status = 500

        async def correlated_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-correlation-id"]
                message = {**message, "headers": [*headers, (b"x-correlation-id", identifier.encode("ascii"))]}
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        finally:
            try:
                emit_event(self.logger, "http_request_completed", status=status)
            finally:
                correlation_id.reset(token)
