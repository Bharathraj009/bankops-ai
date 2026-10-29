"""Exactly two synthetic Groq RCA scenarios; live calls require separate explicit opt-in."""

import argparse
import asyncio
import json
import logging
import os

import httpx2 as httpx

from bankops_agent.rca.provider import OpenAICompatibleProvider, ProviderFailure
from bankops_agent.verify_rca import configured_live_settings, isolated_settings, verify_case

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"
SCENARIOS = ("elevated_transfer_failure_rate", "high_api_latency")


class TwoRequestBudget:
    def __init__(self, provider):
        self.provider, self.requests = provider, 0
        self.lock = asyncio.Lock()

    async def analyze(self, evidence, schema):
        async with self.lock:
            if self.requests >= 2:
                raise ProviderFailure("unavailable")
            # Failed requests consume budget too. Never retry or refund a slot.
            self.requests += 1
        return await self.provider.analyze(evidence, schema)


def mocked_completion(request):
    evidence = json.loads(json.loads(request.content)["messages"][1]["content"])
    observation = next(row for row in evidence["observations"] if row["source"] == "rule")
    result = {"hypotheses": [{"kind": observation["supports"][0], "supporting_evidence": [observation["id"]],
                              "confidence": "low"}], "uncertainty": ["dependencies_not_observed"],
              "recommended_investigation_steps": ["compare_metric_windows", "collect_additional_evidence"]}
    return httpx.Response(200, json={"choices": [{"index": 0, "finish_reason": "stop",
        "message": {"role": "assistant", "content": json.dumps(result)}}]})


async def verification(*, live=False):
    if live:
        if os.getenv("BANKOPS_AGENT_GROQ_LIVE_VERIFY") != "1":
            return {"mode": "live", "status": "blocked", "reason": "explicit_opt_in_required", "inference_requests": 0}
        try:
            settings = configured_live_settings()
        except Exception:
            return {"mode": "live", "status": "blocked", "reason": "invalid_configuration", "inference_requests": 0}
        if (settings.llm_provider != "openai_compatible" or str(settings.llm_url) != ENDPOINT
                or settings.llm_model != MODEL or settings.llm_chat_include_store):
            return {"mode": "live", "status": "blocked", "reason": "groq_profile_required", "inference_requests": 0}
        provider = OpenAICompatibleProvider(settings)
    else:
        settings = isolated_settings(llm_provider="openai_compatible", llm_url=ENDPOINT, llm_model=MODEL,
            llm_api_key="synthetic-not-a-real-key", llm_chat_include_store=False)
        provider = OpenAICompatibleProvider(settings, transport=httpx.MockTransport(mocked_completion))
    budget = TwoRequestBudget(provider)
    cases = [await verify_case(scenario, settings, budget) for scenario in SCENARIOS]
    return {"mode": "live" if live else "mocked", "status": "passed" if all(case["passed"] for case in cases) else "failed",
            "cases": cases, "inference_requests": budget.requests}


def main(argv=None):
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, "Invalid verification arguments; use --help\n")
    parser = SafeParser(description="Verify two synthetic Groq RCA scenarios; offline by default")
    parser.add_argument("--live", action="store_true", help="Requires BANKOPS_AGENT_GROQ_LIVE_VERIFY=1; at most two requests")
    args = parser.parse_args(argv)
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        result = asyncio.run(verification(live=args.live))
    except (Exception, KeyboardInterrupt):
        result = {"status": "failed", "reason": "safe_execution_failure"}
    finally:
        logging.disable(previous_logging)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
