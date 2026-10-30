"""Bounded JSON ingestion, overlapping chunks, inverted index and BM25 ranking."""
from collections import Counter, defaultdict
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
import re
import stat

from bankops_agent.rag.models import Document, RetrievalResult, RetrievedSource
from bankops_agent.rag.privacy import redact

# Populated from the reviewed, versioned synthetic corpus. Unreviewed files can
# be searched locally but cannot become cloud-exportable by setting a JSON flag.
APPROVED = {'database-latency': '041253343640932ed33cdc642a52e538e692759d7a96a447997ad0c37c1ffbbe', 'http-errors': '5f6686dad366762e951143c4aa6fa3648461edd16d64c36118d5d452febbdb18', 'investigation-guide': '2d9f002efbc00882f3642d5b2ed9a15dba365ef9672d0fe4a6cf828f25930a65', 'service-outage': '4e6ee9bd0a4470a3487cfe3452c54f5522e5b2f1997c8bf4b25d549a1a3d2055', 'transfer-failures': '5c013d37223b225576f6a62cb743483302b48789df4e8491c14394d096c9c07b'}
APPROVED["reconciliation"] = "4c433b2cbde0e2a2bfc278140679d391f8b42f42cb6d24bd548b85604594e6c9"
QUERIES = {
    "reconciliation_evidence_gap": "reconciliation insufficient data source unavailable incompatible schema read only",
    "reconciliation_integrity_failure": "reconciliation financial integrity violations ledger balances",
    "reconciliation_workflow_failure": "reconciliation task workflow failure scheduler evidence",
    "http_error_degradation": "http errors error rate request failures rejected requests",
    "latency_degradation": "latency slow response p95 database timeout",
    "transfer_failure_degradation": "transfer failure rejected idempotency conflict rollback",
    "service_unavailability": "service unavailable availability outage health process down",
    "database_call_degradation": "database slow call connection pool timeout latency",
}


def tokens(text):
    return re.findall(r"[a-z][a-z0-9]+", text.lower().replace("_", " "))


def safe_path(path):
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Unsafe corpus path")


def unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate document field")
        value[key] = item
    return value


class Index:
    def __init__(self, documents, *, chunk_words=80, overlap=12, secrets=()):
        if not 20 <= chunk_words <= 160 or not 0 <= overlap < chunk_words:
            raise ValueError("Invalid chunk bounds")
        self.chunks, self.approved, seen = {}, set(), set()
        for raw in documents:
            if len(raw) > 16000:
                raise ValueError("Document exceeds byte limit")
            data = json.loads(raw, object_pairs_hook=unique_fields)
            document = Document.model_validate(data)
            if document.id in seen:
                raise ValueError("Duplicate document ID")
            seen.add(document.id)
            if len(seen) > 32:
                raise ValueError("Corpus exceeds document limit")
            digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            clean_title = redact(document.title, secrets)
            words = redact(document.content, secrets).split()
            for number, start in enumerate(range(0, len(words), chunk_words - overlap)):
                content = " ".join(words[start:start + chunk_words])
                identity = f"doc.{document.id}.{digest[:12]}.c{number:03}"
                self.chunks[identity] = RetrievedSource(id=identity, document_id=document.id,
                    title=clean_title, source="corpus://synthetic/" + document.id,
                    category=document.category, content=content, sha256=digest,
                    supports=document.supports, score=0)
                if APPROVED.get(document.id) == digest and clean_title == document.title and redact(document.content) == document.content:
                    self.approved.add(identity)
                    self.chunks[identity] = self.chunks[identity].model_copy(update={"reviewed": True})
                if len(self.chunks) > 1024:
                    raise ValueError("Corpus exceeds chunk limit")
                if start + chunk_words >= len(words):
                    break
        self.terms, self.postings = {}, defaultdict(set)
        for identity, chunk in self.chunks.items():
            terms = Counter(tokens(chunk.title + " " + chunk.content))
            self.terms[identity] = terms
            for term in terms:
                self.postings[term].add(identity)
        self.average = sum(sum(row.values()) for row in self.terms.values()) / max(1, len(self.terms))

    def retrieve(self, kinds, *, limit=4):
        if not 1 <= limit <= 6:
            raise ValueError("Invalid retrieval limit")
        kinds = set(kinds) & QUERIES.keys()
        query = set(tokens(" ".join(QUERIES[kind] for kind in sorted(kinds))))
        candidates = set().union(*(self.postings.get(term, set()) for term in query)) if query else set()
        scored = []
        for identity in sorted(candidates):
            chunk, terms = self.chunks[identity], self.terms[identity]
            if not kinds.intersection(chunk.supports):
                continue
            score, length = 0.0, sum(terms.values())
            for term in sorted(query):
                frequency = terms[term]
                if frequency:
                    idf = math.log(1 + (len(self.chunks) - len(self.postings[term]) + 0.5) / (len(self.postings[term]) + 0.5))
                    score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / self.average))
            if score > 0:
                scored.append(chunk.model_copy(update={"score": round(score, 8)}))
        scored.sort(key=lambda chunk: (-chunk.score, chunk.id))
        return RetrievalResult(status="matched" if scored else "no_match", sources=tuple(scored[:limit]))


def load_index(directory=None, *, chunk_words=80, overlap=12, secrets=()):
    if directory is None:
        source = files("bankops_agent.rag").joinpath("corpus")
        documents = [path.read_bytes() for path in sorted(source.iterdir(), key=lambda p: p.name) if path.name.endswith(".json")]
    else:
        root = Path(directory)
        if not root.is_absolute() or str(root).startswith(("//", "\\\\")):
            raise ValueError("Corpus requires a trusted local absolute directory")
        safe_path(root)
        paths = sorted(root.glob("*.json"))
        if len(paths) > 32:
            raise ValueError("Corpus exceeds document limit")
        documents = []
        for path in paths:
            safe_path(path)
            if not path.is_file() or path.stat().st_size > 16000:
                raise ValueError("Unsafe corpus file")
            documents.append(path.read_bytes())
    return Index(documents, chunk_words=chunk_words, overlap=overlap, secrets=secrets)
