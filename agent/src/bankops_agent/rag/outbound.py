"""Fail-closed synthetic-only cloud export; corpus flags alone grant no trust."""
from functools import lru_cache
import json

from bankops_agent.rag.retrieval import load_index
from bankops_agent.rag.synthetic import permitted_observations


class OutboundBlocked(ValueError):
    pass


def project_observations(catalog):
    # No identifiers, timestamps, URLs, free text or operational numeric values.
    return [{"id": row.id, "source": row.source, "observation": row.observation,
             "supports": list(row.supports)} for row in catalog]


@lru_cache(maxsize=8)
def approved_index(chunk_words, overlap):
    return load_index(chunk_words=chunk_words, overlap=overlap)


def verify_outbound(settings, evidence):
    if (not settings.llm_external_opt_in or settings.evidence_mode != "synthetic_demo"
            or not settings.rag_enabled):
        raise OutboundBlocked("Explicit synthetic-only external inference opt-in required")
    if not isinstance(evidence, dict) or set(evidence) != {
            "incident_state", "evidence_status", "classification", "scenario", "observations", "retrieved_sources"}:
        raise OutboundBlocked("Unexpected outbound context")
    if (evidence["classification"] != "synthetic" or evidence["scenario"] != settings.synthetic_scenario
            or evidence["incident_state"] != "incident" or evidence["evidence_status"] not in ("complete", "partial")):
        raise OutboundBlocked("Synthetic context required")
    permitted = {row["id"]: row for row in permitted_observations(settings.synthetic_scenario)}
    rows = evidence["observations"]
    if not isinstance(rows, list) or not rows or len(rows) > len(permitted):
        raise OutboundBlocked("Unverified observations")
    if any(not isinstance(row, dict) for row in rows):
        raise OutboundBlocked("Invalid observation")
    if len({row.get("id") for row in rows}) != len(rows):
        raise OutboundBlocked("Duplicate observations")
    if any(row != permitted.get(row.get("id")) for row in rows):
        raise OutboundBlocked("Operational or unverified evidence cannot be exported")
    index = approved_index(settings.rag_chunk_words, settings.rag_chunk_overlap)
    sources = evidence["retrieved_sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= settings.rag_top_k:
        raise OutboundBlocked("Reviewed retrieved context required")
    seen = set()
    for row in sources:
        if not isinstance(row, dict):
            raise OutboundBlocked("Invalid source")
        identity = row.get("id")
        if identity in seen or identity not in index.approved:
            raise OutboundBlocked("Unreviewed or duplicate source")
        seen.add(identity)
        canonical = index.chunks[identity].model_dump(mode="json", exclude={"score"})
        if row != canonical:
            raise OutboundBlocked("Retrieved content was modified")
    # Serialize now as an additional finite-data/type check, before any network I/O.
    json.dumps(evidence, allow_nan=False)
