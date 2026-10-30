"""Validated configuration from the agent's own environment namespace."""

from typing import Literal

from pydantic import Field, HttpUrl, IPvAnyAddress, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_NAME = "bankops-reliability-agent"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BANKOPS_AGENT_", extra="ignore")

    environment: Literal["dev", "test", "production"] = "dev"
    api_token_sha256: SecretStr | None = Field(default=None, repr=False)
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "::1", "testserver"]

    @field_validator("api_token_sha256")
    @classmethod
    def valid_api_digest(cls, value):
        import re
        if value is not None and not re.fullmatch(r"[0-9a-f]{64}", value.get_secret_value()):
            raise ValueError("API credential digest must be SHA-256")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def valid_hosts(cls, value):
        import re
        if not value or any(not re.fullmatch(r"[a-zA-Z0-9.:-]{1,253}", host) for host in value):
            raise ValueError("Explicit host names are required")
        return [host.lower() for host in value]
    host: IPvAnyAddress = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    prometheus_url: HttpUrl = Field(default="http://localhost:9090", repr=False)
    prometheus_timeout_seconds: float = Field(default=5.0, gt=0, le=30, allow_inf_nan=False)
    incident_http_error_ratio: float = Field(default=0.05, gt=0, le=1, allow_inf_nan=False)
    incident_p95_seconds: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    incident_transfer_failure_rate: float = Field(default=0.05, gt=0, allow_inf_nan=False)
    incident_min_api_request_rate: float = Field(default=0.1, gt=0, allow_inf_nan=False)
    incident_min_transfer_request_rate: float = Field(default=0.1, gt=0, allow_inf_nan=False)
    incident_max_evidence_age_seconds: float = Field(default=60, ge=1, le=300, allow_inf_nan=False)
    jaeger_url: HttpUrl = Field(default="http://localhost:16686", repr=False)
    jaeger_timeout_seconds: float = Field(default=5, gt=0, le=30, allow_inf_nan=False)
    jaeger_window_seconds: int = Field(default=300, ge=1, le=3600)
    jaeger_max_traces: int = Field(default=10, ge=1, le=50)
    jaeger_max_spans_per_trace: int = Field(default=100, ge=1, le=500)
    jaeger_max_total_spans: int = Field(default=500, ge=1, le=2000)
    jaeger_slow_span_seconds: float = Field(default=1, gt=0, le=3600, allow_inf_nan=False)
    log_source_directory: str | None = Field(default=None, repr=False)
    log_source_filename: str = Field(default="banking.jsonl", repr=False)
    log_window_seconds: int = Field(default=300, ge=1, le=3600)
    log_max_events: int = Field(default=100, ge=1, le=500)
    log_max_bytes: int = Field(default=1048576, ge=1024, le=4194304)
    rag_enabled: bool = False
    log_include_info: bool = False
    rag_corpus_directory: str | None = Field(default=None, repr=False)
    rag_top_k: int = Field(default=4, ge=1, le=6)
    rag_chunk_words: int = Field(default=80, ge=20, le=160)
    rag_chunk_overlap: int = Field(default=12, ge=0, le=40)
    evidence_mode: Literal["operational", "synthetic_demo"] = "operational"
    synthetic_scenario: Literal["http_errors", "latency", "service_down"] = "http_errors"
    llm_external_opt_in: bool = False
    llm_provider: Literal["disabled", "json_http", "openai_compatible", "openai_cloud"] = "disabled"
    llm_url: HttpUrl | None = Field(default=None, repr=False)
    llm_api_key: SecretStr | None = Field(default=None, repr=False)
    llm_model: str = Field(default="rca", pattern=r"^[A-Za-z0-9_.:/-]{1,100}$")
    llm_timeout_seconds: float = Field(default=5, gt=0, le=30, allow_inf_nan=False)
    llm_max_input_bytes: int = Field(default=32768, ge=1024, le=65536)
    llm_max_output_bytes: int = Field(default=16384, ge=256, le=32768)
    llm_max_output_tokens: int = Field(default=512, ge=128, le=2048)
    llm_chat_include_store: bool = True
    approval_db_path: str | None = Field(default=None, repr=False)
    approval_proposer_token_sha256: SecretStr | None = Field(default=None, repr=False)
    approval_reviewer_token_sha256: SecretStr | None = Field(default=None, repr=False)
    remediation_enabled: bool = False
    airflow_enabled: bool = False
    airflow_ca_file: str | None = Field(default=None, repr=False, max_length=2048)
    airflow_url: HttpUrl = Field(default="http://localhost:18081", repr=False)
    airflow_api_token: SecretStr | None = Field(default=None, repr=False)
    airflow_timeout_seconds: float = Field(default=5, gt=0, le=30, allow_inf_nan=False)
    airflow_window_seconds: int = Field(default=172800, ge=3600, le=604800)
    airflow_max_runs: int = Field(default=5, ge=1, le=10)
    remediation_timeout_seconds: float = Field(default=15, gt=0, le=60, allow_inf_nan=False)

    @model_validator(mode="after")
    def airflow_configuration(self):
        url = self.airflow_url
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Airflow URL must not contain credentials or query parameters")
        if url.scheme != "https" and not (self.environment != "production" and url.host in ("localhost", "127.0.0.1", "[::1]")):
            if self.airflow_enabled:
                raise ValueError("Airflow requires HTTPS outside local development")
        if self.airflow_enabled:
            token = self.airflow_api_token.get_secret_value() if self.airflow_api_token else ""
            if not 16 <= len(token) <= 4096 or any(not 33 <= ord(c) <= 126 for c in token):
                raise ValueError("Airflow requires an environment-injected bearer token")
        return self

    @model_validator(mode="after")
    def approval_configuration(self):
        if self.approval_db_path is not None:
            import re
            from pathlib import Path
            path = Path(self.approval_db_path)
            if not path.is_absolute() or str(path).startswith(("\\\\", "//")) or path.suffix != ".sqlite3":
                raise ValueError("Approval storage requires an absolute local sqlite3 file")
            hashes = [value.get_secret_value() if value else "" for value in (
                self.approval_proposer_token_sha256, self.approval_reviewer_token_sha256)]
            if not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes) or hashes[0] == hashes[1]:
                raise ValueError("Distinct proposer and reviewer credential hashes are required")
            if self.api_token_sha256 and self.api_token_sha256.get_secret_value() in hashes:
                raise ValueError("Deployment credentials must be distinct from approval credentials")
        return self

    @model_validator(mode="after")
    def configured_llm(self):
        if self.rag_chunk_overlap >= self.rag_chunk_words:
            raise ValueError("Chunk overlap must be smaller than chunk size")
        if self.evidence_mode == "synthetic_demo" and (self.remediation_enabled or self.airflow_enabled):
            raise ValueError("Synthetic demonstration cannot enable remediation or Airflow access")
        if self.llm_provider == "openai_cloud":
            endpoint = "https://api.openai.com/v1/chat/completions"
            if self.llm_url is not None and str(self.llm_url) != endpoint:
                raise ValueError("Cloud provider requires its fixed supported endpoint")
            self.llm_url = HttpUrl(endpoint)
            if self.llm_model == "rca":
                raise ValueError("Select an explicit cloud model")
        if self.llm_provider != "disabled" and self.llm_url is None:
            raise ValueError("LLM URL is required for the configured provider")
        if self.llm_provider in ("openai_compatible", "openai_cloud"):
            key = self.llm_api_key.get_secret_value() if self.llm_api_key else ""
            if not key or any(ord(char) <= 32 or ord(char) >= 127 for char in key):
                raise ValueError("A valid environment-injected bearer key is required")
        if self.llm_url is not None:
            if self.llm_url.username or self.llm_url.password or self.llm_url.query or self.llm_url.fragment:
                raise ValueError("LLM URL cannot contain credentials, query or fragment")
            if self.llm_url.scheme != "https" and not (
                self.environment != "production" and self.llm_url.host in ("localhost", "127.0.0.1", "[::1]")
            ):
                raise ValueError("LLM URL requires HTTPS outside local development")
        return self

    @field_validator("log_source_filename")
    @classmethod
    def safe_log_filename(cls, value: str) -> str:
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}", value):
            raise ValueError("Log source must be a simple filename")
        return value

    @field_validator("prometheus_url", "jaeger_url")
    @classmethod
    def safe_prometheus_url(cls, value: HttpUrl) -> HttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("Evidence URL must not contain credentials, query or fragment")
        return value
