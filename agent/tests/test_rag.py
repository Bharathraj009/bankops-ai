"""Offline ingestion, lexical retrieval and independent grounding checks."""
import asyncio
import json
from pathlib import Path

import pytest

from bankops_agent.config import Settings
from bankops_agent.investigation import investigate
from bankops_agent.rag.retrieval import Index, load_index
from bankops_agent.rca.analysis import RCAAnalyzer
from test_investigation import state


def document(**changes):
    return json.dumps({"id": "synthetic-test", "title": "Synthetic incident example",
        "category": "historical_incident", "data_classification": "synthetic",
        "supports": ["http_error_degradation"],
        "content": "Synthetic HTTP errors and failed requests crossed the error rate threshold. "
                   "Compare metric windows and retain uncertainty."} | changes).encode()


def test_ingest_chunks_overlap_stable_refs_and_no_implicit_cloud_approval():
    raw = document(content=" ".join("http error window" for _ in range(50)))
    first = Index([raw], chunk_words=20, overlap=5)
    second = Index([raw], chunk_words=20, overlap=5)
    assert len(first.chunks) > 1 and first.chunks == second.chunks
    chunks = list(first.chunks.values())
    assert chunks[0].content.split()[-5:] == chunks[1].content.split()[:5]
    assert not first.approved
    assert all(chunk.source == "corpus://synthetic/synthetic-test" for chunk in chunks)


def test_default_corpus_contains_both_source_types_and_reviewed_hashes():
    index = load_index()
    assert index.approved == set(index.chunks)
    assert {chunk.category for chunk in index.chunks.values()} == {"historical_incident", "troubleshooting"}
    for kind, relevant in [("service_unavailability", "service-outage"),
                           ("database_call_degradation", "database-latency"),
                           ("transfer_failure_degradation", "transfer-failures")]:
        result = index.retrieve({kind})
        assert result.status == "matched" and result.sources[0].document_id == relevant
        assert all(kind in row.supports for row in result.sources)
        assert result == index.retrieve({kind})
    assert index.retrieve(set()).status == "no_match"
    assert index.retrieve({"invented_root_cause"}).sources == ()


@pytest.mark.parametrize("changes", [
    {"data_classification": "production"}, {"category": "unknown"}, {"supports": ["confirmed_cause"]},
    {"id": "../../secret"}, {"extra_secret": "do-not-return"}, {"content": "x" * 17000},
])
def test_invalid_ingestion_rejected(changes):
    with pytest.raises(ValueError):
        Index([document(**changes)])


def test_duplicate_documents_and_json_fields_rejected():
    with pytest.raises(ValueError):
        Index([document(), document()])
    with pytest.raises(ValueError):
        Index([document()[:-1] + b',"id":"another-id"}'])


def test_local_ingestion_redacts_secrets_identifiers_and_paths(tmp_path):
    raw = document(content="Synthetic http errors. email=person@example.invalid; name=Example Person; "
        "password=do-not-export; account_id=123456789012; api_key=sk-sensitivevalue123; "
        "Bearer bearer-value; 12345678-1234-1234-1234-123456789012; 192.0.2.1; "
        "+1 555 555 1234; C:/Users/example/private; injected-key-value")
    (tmp_path / "incident.json").write_bytes(raw)
    index = load_index(str(tmp_path), secrets=("injected-key-value",))
    text = " ".join(chunk.content for chunk in index.chunks.values())
    for private in ("person@example", "Example Person", "do-not-export", "123456789012",
                    "sk-sensitive", "bearer-value", "192.0.2.1", "555", "C:/Users", "injected-key-value"):
        assert private not in text
    assert "[REDACTED]" in text and not index.approved


def test_corpus_bounds_relative_paths_and_reparse_sources(tmp_path):
    with pytest.raises(ValueError):
        load_index("relative/private")
    for i in range(33):
        (tmp_path / f"{i}.json").write_bytes(document(id=f"record-{i:02}"))
    with pytest.raises(ValueError):
        load_index(str(tmp_path))
    with pytest.raises(ValueError):
        Index([document()], chunk_words=20, overlap=20)


class GroundedProvider:
    def __init__(self, change=None):
        self.change, self.calls, self.context = change, 0, None

    async def analyze(self, evidence, schema):
        self.calls += 1
        self.context = evidence
        source = next(row for row in evidence["retrieved_sources"] if "http_error_degradation" in row["supports"])
        value = {"hypotheses": [{"kind": "http_error_degradation", "supporting_evidence": ["rule.high_http_error_rate"],
            "retrieved_sources": [source["id"]], "confidence": "low"}],
            "uncertainty": ["causality_unconfirmed"],
            "recommended_investigation_steps": ["compare_metric_windows"]}
        if self.change == "invented": value["hypotheses"][0]["retrieved_sources"] = ["doc.invented"]
        if self.change == "missing": del value["hypotheses"][0]["retrieved_sources"]
        if self.change == "unsupported": value["hypotheses"][0]["kind"] = "service_unavailability"
        if self.change == "confirmed": value["root_cause_confirmed"] = True
        if self.change == "command": value["recommended_investigation_steps"] = ["DELETE banking records"]
        if self.change == "duplicate": value["hypotheses"][0]["retrieved_sources"] *= 2
        return json.dumps(value).encode()


def analyze(provider=None, **changes):
    sources = state(api_error_rate=0.5)
    report = asyncio.run(investigate(sources))
    return asyncio.run(RCAAnalyzer(Settings(rag_enabled=True, **changes), provider).analyze(report))


def test_rag_context_and_both_current_and_retrieved_grounding():
    provider = GroundedProvider()
    result = analyze(provider)
    assert result.status == "hypotheses" and result.root_cause_confirmed is False
    ids = {row.id for row in result.retrieval.sources}
    assert set(result.hypotheses[0].retrieved_sources) <= ids
    assert result.hypotheses[0].supporting_evidence == ("rule.high_http_error_rate",)
    assert provider.context["retrieved_sources"] and provider.calls == 1


@pytest.mark.parametrize("change", ["invented", "missing", "unsupported", "confirmed", "command", "duplicate"])
def test_rag_rejects_invalid_citations_and_unsupported_claims(change):
    result = analyze(GroundedProvider(change))
    assert result.reason == "invalid_output" and not result.hypotheses


def test_disabled_inference_still_retrieves_deterministically():
    first, second = analyze(), analyze()
    assert first.reason == second.reason == "disabled"
    assert first.retrieval == second.retrieval and first.retrieval.status == "matched"
    assert not first.hypotheses


def test_broken_or_empty_corpus_fails_closed_without_provider_call(tmp_path):
    provider = GroundedProvider()
    result = analyze(provider, rag_corpus_directory=str(tmp_path))
    assert result.reason == "no_retrieval_match" and provider.calls == 0
    (tmp_path / "bad.json").write_text("not JSON")
    result = analyze(provider, rag_corpus_directory=str(tmp_path))
    assert result.reason == "retrieval_unavailable" and provider.calls == 0
