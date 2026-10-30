"""Ephemeral investigation graph with optional, validated hypothesis analysis."""

from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from bankops_agent.detection.rules import DetectionResult
from bankops_agent.evidence.jaeger import JaegerEvidence
from bankops_agent.evidence.logs import LogEvidence
from bankops_agent.investigation import (
    InvestigationReport, assemble_report, collect_detection, collect_support,
)
from bankops_agent.rca.analysis import RCAAnalyzer, RCAResult


class WorkflowReport(InvestigationReport):
    rca: RCAResult


class InvestigationState(TypedDict):
    started_at: datetime
    decision: NotRequired[DetectionResult]
    traces: NotRequired[JaegerEvidence]
    logs: NotRequired[LogEvidence]
    report: NotRequired[InvestigationReport]
    rca: NotRequired[RCAResult]


def build_workflow(sources):
    """Collectors stay in a closure, never in graph state or caller input."""
    async def detection(state: InvestigationState):
        return {"decision": await collect_detection(sources)}

    async def evidence_collection(state: InvestigationState):
        traces, logs = await collect_support(sources)
        return {"traces": traces, "logs": logs}

    def report_assembly(state: InvestigationState):
        return {"report": assemble_report(state["started_at"], state["decision"], state["traces"], state["logs"],
                                         evidence_mode=sources.settings.evidence_mode)}

    async def rca(state: InvestigationState):
        analyzer = getattr(sources, "rca_analyzer", None) or RCAAnalyzer(sources.settings)
        return {"rca": await analyzer.analyze(state["report"])}

    graph = StateGraph(InvestigationState)
    graph.add_node("detection", detection)
    graph.add_node("evidence_collection", evidence_collection)
    graph.add_node("report_assembly", report_assembly)
    graph.add_node("rca", rca)
    graph.add_edge(START, "detection")
    graph.add_edge(START, "evidence_collection")
    graph.add_edge(["detection", "evidence_collection"], "report_assembly")
    graph.add_edge("report_assembly", "rca")
    graph.add_edge("rca", END)
    return graph.compile()


async def run_workflow(graph) -> WorkflowReport:
    # Override ambient LangSmith tracing settings; no evidence export or callbacks.
    with tracing_context(enabled=False):
        result = await graph.ainvoke({"started_at": datetime.now(UTC)},
                                    config={"callbacks": [], "recursion_limit": 5})
    return WorkflowReport(**result["report"].model_dump(), rca=result["rca"])
