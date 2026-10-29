import logging
import sqlite3

from fastapi import FastAPI

from bankops_agent.api.health import router
from bankops_agent.api.evidence import router as evidence_router
from bankops_agent.api.incidents import router as incidents_router
from bankops_agent.api.traces import router as traces_router
from bankops_agent.api.logs import router as logs_router
from bankops_agent.api.workflows import router as workflows_router
from bankops_agent.api.approvals import router as approvals_router
from bankops_agent.api.executions import router as executions_router
from bankops_agent.api.verifications import router as verifications_router
from bankops_agent.remediation.store import ApprovalStore
from bankops_agent.workflow import build_workflow
from bankops_agent.rca.analysis import RCAAnalyzer
from bankops_agent.rca.provider import create_provider
from bankops_agent.evidence.logs import LogCollector
from bankops_agent.evidence.airflow import AirflowCollector
from bankops_agent.evidence.jaeger import JaegerCollector
from bankops_agent.evidence.prometheus import PrometheusCollector
from bankops_agent.config import SERVICE_NAME, Settings
from bankops_agent.logging import create_logger
from bankops_agent.middleware import CorrelationMiddleware
from bankops_agent.security import SecurityBoundary


def create_app(settings: Settings | None = None, *, logger: logging.Logger | None = None) -> CorrelationMiddleware:
    settings = settings if settings is not None else Settings()
    api = FastAPI(title=SERVICE_NAME, debug=False, docs_url=None, redoc_url=None, openapi_url=None)
    api.add_middleware(SecurityBoundary, settings=settings)
    api.state.settings = settings
    api.state.approval_store = None
    if settings.approval_db_path is not None:
        try:
            api.state.approval_store = ApprovalStore(settings.approval_db_path)
        except (OSError, sqlite3.Error):
            pass  # Fail closed without exposing local paths or credentials.
    api.state.prometheus_collector = PrometheusCollector(settings)
    api.state.jaeger_collector = JaegerCollector(settings)
    api.state.log_collector = LogCollector(settings)
    api.state.airflow_collector = AirflowCollector(settings)
    api.state.rca_analyzer = RCAAnalyzer(settings, create_provider(settings))
    api.state.investigation_workflow = build_workflow(api.state)
    api.include_router(router)
    api.include_router(evidence_router)
    api.include_router(incidents_router)
    api.include_router(traces_router)
    api.include_router(logs_router)
    api.include_router(workflows_router)
    api.include_router(approvals_router)
    api.include_router(executions_router)
    api.include_router(verifications_router)
    # Wrap FastAPI's error handling too, so error responses retain their correlation header.
    return CorrelationMiddleware(api, logger if logger is not None else create_logger(settings.log_level))
