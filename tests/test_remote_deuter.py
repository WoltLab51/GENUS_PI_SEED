"""Live-Remote-Deuter: minimaler Datenschutz-, Kosten- und Strukturvertrag."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))

import deuter  # noqa: E402
import model_gateway  # noqa: E402
import remote_deuter  # noqa: E402


class _Provider:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.content = content or json.dumps({"segments": []})
        self.error = error
        self.requests = []

    def complete(self, request, *, timeout):
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        return model_gateway.ModelResult(
            self.content,
            model_gateway.ModelReceipt(
                provider="github-models", model=request.model, request_id="safe-id",
                elapsed_ms=125, input_tokens=40, output_tokens=12, finish_reason="stop",
            ),
        )


def _reader(tmp_path, provider=None, **changes):
    values = {
        "budget_file": tmp_path / "budget.json",
        "clock": lambda: 1_800_000_000.0,
    }
    values.update(changes)
    return remote_deuter.RemoteDeuter(provider or _Provider(), **values)


def test_remote_request_contains_only_static_prompt_and_current_bounded_message(tmp_path):
    text = "Ich teste dich grad, denn wir haben einen neuen Worker angeschlossen"
    provider = _Provider(json.dumps({
        "segments": [{"text": text, "absicht": "tatsache", "subject": "Worker",
                      "object": None}],
    }))
    reports = []
    result = _reader(tmp_path, provider, reporter=reports.append).interpret(
        text, absichten=deuter.DEFAULT_ABSICHTEN,
    )

    request, timeout = provider.requests[0]
    assert request.privacy == "remote_minimal"
    assert request.model == "openai/gpt-4.1-nano"
    assert request.max_output_tokens == 160 and timeout == 8.0
    assert [(message.role, message.content) for message in request.messages][1] == ("user", text)
    assert len(request.messages) == 2
    assert "vorher" not in request.messages[0].content.casefold()
    assert request.schema.schema["properties"]["segments"]["maxItems"] == 3
    assert result == [{"text": text, "absicht": "tatsache", "subject": "Worker",
                       "object": None}]
    assert reports and text not in reports[0] and "segments=1" in reports[0]


def test_remote_refuses_oversized_text_before_budget_or_network(tmp_path):
    provider = _Provider()
    reader = _reader(tmp_path, provider)
    with pytest.raises(model_gateway.GatewayError, match="zu lang"):
        reader.interpret("x" * (remote_deuter.MAX_TEXT_CHARS + 1))
    assert provider.requests == []
    assert not (tmp_path / "budget.json").exists()


def test_remote_minute_budget_is_hard_and_precedes_network(tmp_path):
    provider = _Provider()
    reader = _reader(tmp_path, provider, minute_limit=2)
    assert reader.interpret("eins") == []
    assert reader.interpret("zwei") == []
    with pytest.raises(model_gateway.GatewayError, match="Minutenbudget"):
        reader.interpret("drei")
    assert len(provider.requests) == 2


def test_remote_daily_budget_survives_a_new_reader_process_state(tmp_path):
    provider = _Provider()
    _reader(tmp_path, provider, daily_limit=1).interpret("eins")
    second = _reader(tmp_path, provider, daily_limit=1)
    with pytest.raises(model_gateway.GatewayError, match="Tagesbudget"):
        second.interpret("zwei")
    assert len(provider.requests) == 1
    assert json.loads((tmp_path / "budget.json").read_text())["requests"] == 1


def test_provider_failure_opens_a_short_circuit_without_echoing_text(tmp_path):
    provider = _Provider(error=model_gateway.GatewayError("GitHub Models HTTP 429"))
    reports = []
    reader = _reader(tmp_path, provider, reporter=reports.append)
    with pytest.raises(model_gateway.GatewayError, match="HTTP 429"):
        reader.interpret("mein privater Satz")
    with pytest.raises(model_gateway.GatewayError, match="kurz gesperrt"):
        reader.interpret("noch privater")
    assert len(provider.requests) == 1
    assert reports == ["remote Deuter unavailable (GatewayError)"]


def test_remote_consent_is_exact_and_fail_closed(tmp_path, monkeypatch):
    consent = tmp_path / "consent"
    token = tmp_path / "token"
    token.write_text("token", encoding="utf-8")
    token.chmod(0o600)
    monkeypatch.setenv("GENUS_REMOTE_DEUTER_CONSENT_FILE", str(consent))
    monkeypatch.setenv("GENUS_GITHUB_MODELS_TOKEN_FILE", str(token))
    monkeypatch.setenv("GENUS_REMOTE_DEUTER_BUDGET_FILE", str(tmp_path / "budget"))

    assert remote_deuter.from_environment() is None
    consent.write_text("irgendetwas anderes\n", encoding="utf-8")
    consent.chmod(0o600)
    assert remote_deuter.from_environment() is None
    consent.write_text(remote_deuter.CONSENT_VALUE + "\n", encoding="utf-8")
    consent.chmod(0o600)
    reader = remote_deuter.from_environment()
    assert reader is not None and reader.model == "openai/gpt-4.1-nano"
