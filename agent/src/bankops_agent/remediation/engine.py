"""Only approved, fixed-target read-only collectors. No LLM, shell or arbitrary URL."""

import asyncio
from datetime import UTC, datetime

from bankops_agent.detection.rules import detect
from bankops_agent.investigation import investigate
from bankops_agent.remediation.execution_store import ExecutionStore


class RemediationEngine:
    def __init__(self, state):
        self.state = state
        self.store = ExecutionStore(state.approval_store)

    async def execute(self, identifier, request):
        if not self.state.settings.remediation_enabled:
            raise PermissionError("Execution disabled")
        claim = await asyncio.to_thread(self.store.claim, identifier, request)
        status, outcome = "FAILED", "internal_failure"
        try:
            async with asyncio.timeout(self.state.settings.remediation_timeout_seconds):
                if claim.action == "CHECK_SERVICE_HEALTH":
                    metrics = await self.state.prometheus_collector.collect_for_detection()
                    decision = detect(metrics, self.state.settings, detected_at=datetime.now(UTC))
                    rule = next(rule for rule in decision.rules if rule.rule_id == "banking_unavailable")
                    if rule.state != "insufficient_data":
                        status, outcome = "SUCCEEDED", "service_up" if rule.state == "healthy" else "service_down"
                    else: outcome = "source_unavailable"
                elif claim.action == "REFRESH_INCIDENT_EVIDENCE":
                    report = await investigate(self.state)  # Never runs the RCA/LLM graph.
                    if report.evidence_status != "unavailable":
                        status, outcome = "SUCCEEDED", "evidence_refreshed" if report.evidence_status == "complete" else "evidence_partial"
                    else: outcome = "source_unavailable"
        except TimeoutError:
            outcome = "timeout"
        except asyncio.CancelledError:
            await asyncio.shield(asyncio.to_thread(self.store.finish, identifier, "FAILED", "cancelled"))
            raise
        except Exception:
            outcome = "internal_failure"
        return await asyncio.to_thread(self.store.finish, identifier, status, outcome)
