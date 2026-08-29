from __future__ import annotations

import io
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.modules.catalogue_ingestion.capability_probe import (
    build_capability_probe_plan,
    persist_capability_probe_outcome,
    run_capability_probe,
)
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.preflight import _validate_capability_receipt


class FakeCredential:
    def get_token(self, scope: str) -> SimpleNamespace:
        assert scope == "https://cognitiveservices.azure.com/.default"
        return SimpleNamespace(token="secret-token-not-for-evidence")


class FakeResponse(io.BytesIO):
    def __init__(self, payload: dict[str, object]) -> None:
        super().__init__(json.dumps(payload).encode())
        self.status = 200
        self.headers = {"apim-request-id": "provider-request-12345678"}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class FakeOpener:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def open(self, request: object, timeout: int) -> FakeResponse:
        del request
        assert timeout == 30
        self.calls += 1
        return FakeResponse(self.payload)


def settings() -> Settings:
    return Settings(
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://scholarship-ai-863780.openai.azure.com/",
        catalogue_ai_model="catalogue-gpt5-mini",
        catalogue_ai_max_retries=0,
        catalogue_ai_input_cost_per_million=Decimal("0.25"),
        catalogue_ai_output_cost_per_million=Decimal("2.00"),
    )


def response_payload(
    *,
    finish_reason: str = "stop",
    refusal: str | None = None,
    content: str | None = None,
) -> dict[str, object]:
    valid_content = json.dumps(
        {
            "objective": "documents_core",
            "coverage_state": "complete",
            "claims": [],
            "unknown_objectives": [],
            "conflicts": [],
            "warnings": [],
        }
    )
    return {
        "id": "chatcmpl-response-12345678",
        "model": "gpt-5-mini-2025-08-07",
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {
                    "content": valid_content if content is None else content,
                    "refusal": refusal,
                },
            }
        ],
        "usage": {
            "prompt_tokens": 1_200,
            "completion_tokens": 400,
            "total_tokens": 1_600,
        },
    }


def run_with(payload: dict[str, object]):
    opener = FakeOpener(payload)
    outcome = run_capability_probe(
        settings(),
        credential=FakeCredential(),
        opener=opener,
        now=lambda: datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
        request_id_factory=lambda: uuid.UUID("11111111-1111-1111-1111-111111111111"),
    )
    assert opener.calls == 1
    return outcome


def test_probe_plan_uses_canonical_route_real_schema_and_sub_cent_cost_bound() -> None:
    plan = build_capability_probe_plan(settings())
    body = json.loads(plan.payload)

    assert plan.request_url.endswith("/openai/v1/chat/completions")
    assert plan.objective is ClaimObjective.DOCUMENTS_CORE
    assert body["model"] == "catalogue-gpt5-mini"
    assert body["reasoning_effort"] == "minimal"
    assert body["max_completion_tokens"] == 4_096
    assert body["response_format"]["json_schema"]["strict"] is True
    assert plan.byte_upper_bound_cost_usd <= Decimal("0.01")


@pytest.mark.parametrize(
    ("payload", "failure_category", "finish_reason", "refusal_present"),
    [
        (response_payload(finish_reason="length"), "length", "length", False),
        (response_payload(refusal="cannot comply"), "refusal", "stop", True),
        (
            {
                **response_payload(finish_reason="content_filter"),
                "prompt_filter_results": [
                    {
                        "content_filter_results": {"violence": {"filtered": True}}
                    }
                ],
            },
            "content_filter",
            "content_filter",
            False,
        ),
        (response_payload(content="not-json"), "parser_contract", "stop", False),
    ],
)
def test_failed_probe_retains_sanitized_metadata_and_usage(
    tmp_path,
    payload: dict[str, object],
    failure_category: str,
    finish_reason: str,
    refusal_present: bool,
) -> None:
    outcome = run_with(payload)
    evidence_path = tmp_path / "capability-evidence.json"
    receipt_path = tmp_path / "model-capability.json"
    persist_capability_probe_outcome(
        outcome,
        evidence_path=evidence_path,
        receipt_path=receipt_path,
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    serialized = evidence_path.read_text(encoding="utf-8")
    assert evidence["status"] == "failed"
    assert evidence["failure_category"] == failure_category
    assert evidence["request"]["count"] == 1
    assert evidence["request"]["provider_request_id"] == "provider-request-12345678"
    assert evidence["response"]["response_id"] == "chatcmpl-response-12345678"
    assert evidence["response"]["finish_reason"] == finish_reason
    assert evidence["response"]["refusal_present"] is refusal_present
    assert evidence["usage"] == {
        "input_tokens": 1_200,
        "output_tokens": 400,
        "total_tokens": 1_600,
        "estimated_cost_usd": "0.001100",
    }
    assert "secret-token-not-for-evidence" not in serialized
    assert "cannot comply" not in serialized
    assert "not-json" not in serialized
    assert not receipt_path.exists()


def test_success_persists_valid_v2_receipt(tmp_path) -> None:
    current_settings = settings()
    outcome = run_with(response_payload())
    evidence_path = tmp_path / "capability-evidence.json"
    receipt_path = tmp_path / "model-capability.json"
    persist_capability_probe_outcome(
        outcome,
        evidence_path=evidence_path,
        receipt_path=receipt_path,
    )

    assert outcome.evidence["status"] == "succeeded"
    assert outcome.receipt is not None
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validation = _validate_capability_receipt(
        receipt,
        current_settings,
        datetime(2026, 8, 26, tzinfo=UTC),
    )
    assert validation["status"] == "ready"

def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
    """Ensure persist_capability_probe_outcome writes a best-effort
local copy to `.catalogue-local` when present."""
    import os
    from pathlib import Path

    # Create a failing outcome (length) to get a sanitized evidence payload
    outcome = run_with(response_payload(finish_reason="length"))
    evidence_path = tmp_path / "capability-evidence.json"
    receipt_path = tmp_path / "model-capability.json"

    # Create a .catalogue-local directory under tmp_path and run persist while cwd is tmp_path
    local_dir = tmp_path / ".catalogue-local"
    local_dir.mkdir()

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        persist_capability_probe_outcome(
            outcome, evidence_path=evidence_path, receipt_path=receipt_path
        )
    finally:
        os.chdir(original_cwd)

    assert (local_dir / "capability-probe-evidence.json").exists()

