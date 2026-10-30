"""Execute the installed graph with real local evidence and optional fake inference.

Run only inside the disposable Step 73 agent. Fake completion HTTP stays on
loopback, and never represents real model inference.
"""
import argparse
import asyncio
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
from pathlib import Path
import threading

from langsmith import tracing_context

from bankops_agent.app import create_app
from bankops_agent.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["disabled", "mocked", "adversarial"], required=True)
    args = parser.parse_args()
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            context = json.loads(payload["messages"][1]["content"])
            assert all(row["source"] in ("rule", "span", "log") for row in context["observations"])
            assert not any(key in json.dumps(context) for key in
                           ("accountNumber", "sourceAccountId", "destinationAccountId", "password"))
            supported = next(row for row in context["observations"] if row["supports"])
            reference = "invented.reference" if args.mode == "adversarial" else supported["id"]
            analysis = {"hypotheses": [{"kind": supported["supports"][0],
                "supporting_evidence": [reference], "confidence": "low"}],
                "uncertainty": ["causality_unconfirmed", "bounded_sample"],
                "recommended_investigation_steps": ["collect_additional_evidence"]}
            calls.append({"context_bytes": len(json.dumps(context).encode()),
                "context_sources": sorted({row["source"] for row in context["observations"]}),
                "context_reference_ids": [row["id"] for row in context["observations"]],
                "json_schema_requested": payload["response_format"]["type"] == "json_schema"})
            body = json.dumps({"choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(analysis)}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = None
    try:
        if args.mode == "disabled":
            settings = Settings(llm_provider="disabled", remediation_enabled=False)
        else:
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            settings = Settings(llm_provider="openai_compatible", remediation_enabled=False,
                llm_url=f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                llm_model="step73-simulated-completion", llm_api_key="synthetic-loopback-only")
        state = create_app(settings).app.state
        graph = state.investigation_workflow

        async def execute():
            updates, values = [], {}
            with tracing_context(enabled=False):
                async for update in graph.astream({"started_at": datetime.now(UTC)},
                        config={"callbacks": [], "recursion_limit": 5}, stream_mode="updates"):
                    for name, fields in update.items():
                        updates.append({"node": name, "state_fields_written": sorted(fields)})
                        values.update(fields)
            return updates, values

        updates, values = asyncio.run(execute())
        names = [row["node"] for row in updates]
        assert set(names[:2]) == {"detection", "evidence_collection"}
        assert names[2:] == ["report_assembly", "rca"] and len(names) == 4
        report, rca = values["report"], values["rca"]
        native_log_trace_matches = 0
        if settings.log_source_directory:
            source = Path(settings.log_source_directory) / settings.log_source_filename
            rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
            native_ids = {row.get("trace_id") for row in rows if row.get("trace_id")}
            native_log_trace_matches = len(native_ids & {trace.trace_id for trace in report.traces.traces})
        assert report.detection.state == "incident"
        assert rca.root_cause_confirmed is False
        if args.mode == "disabled":
            assert rca.reason == "disabled" and not calls
        elif args.mode == "mocked":
            assert rca.status == "hypotheses" and len(calls) == 1
            refs = {row.id for row in rca.evidence}
            assert all(ref in refs for h in rca.hypotheses for ref in h.supporting_evidence)
        else:
            assert rca.reason == "invalid_output" and len(calls) == 1
        print(json.dumps({"mode": args.mode, "langgraph_version": version("langgraph"),
            "graph_nodes": sorted(graph.get_graph().nodes),
            "graph_edges": [{"source": edge.source, "target": edge.target}
                            for edge in graph.get_graph().edges], "updates": updates,
            "detection_state": report.detection.state, "triggered_rules": report.detection.triggered_rules,
            "evidence_status": report.evidence_status, "trace_count": len(report.traces.traces),
            "log_status": report.logs.status, "log_events": len(report.logs.events),
            "native_log_trace_matches": native_log_trace_matches,
            "correlations": len(report.correlations), "rca_status": rca.status,
            "rca_reason": rca.reason, "root_cause_confirmed": False,
            "provider_calls": calls, "real_model_inference": False,
            "external_ai_requests": 0, "remediation_enabled": False}))
    finally:
        if server:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
