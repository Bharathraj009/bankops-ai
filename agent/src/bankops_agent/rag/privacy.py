"""Defense in depth redaction, never a proof of synthetic provenance."""
import re
import unicodedata

PATTERNS = (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]+|AKIA[A-Z0-9]{16})\b",
    r"(?i)\bBearer\s+[^\s,;]+",
    r"(?i)\b(?:password|api[_ -]?key|secret|token|account[_ -]?(?:id|number)|customer[_ -]?(?:id|name)|email|name)\s*[:=]\s*[^\n;,]+",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b",
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    r"\b\d[\d ()+-]{7,}\d\b",
    r"https?://\S+|[A-Za-z]:[\\/][^\s]+|/home/[^\s]+|/Users/[^\s]+",
    r"\b[A-Za-z0-9_+/=-]{32,}\b",
)


def redact(text: str, secrets=()) -> str:
    value = unicodedata.normalize("NFKC", text)
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    for pattern in PATTERNS:
        value = re.sub(pattern, "[REDACTED]", value)
    return value
