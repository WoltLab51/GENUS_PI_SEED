"""Remote Modelle bleiben eine getestete, synthetisch geschlossene deploy-Membran."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))

import model_bakeoff  # noqa: E402
import model_gateway  # noqa: E402
import stimme  # noqa: E402


class _Response:
    def __init__(self, body: dict, headers=None):
        self.body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.body).encode("utf-8")


def _request(**changes):
    values = {
        "role": "deuter",
        "model": "openai/gpt-test",
        "privacy": "synthetic",
        "messages": (model_gateway.Message("user", "synthetische Frage"),),
        "max_output_tokens": 123,
        "temperature": 0.0,
    }
    values.update(changes)
    return model_gateway.ModelRequest(**values)


def test_github_models_sends_the_versioned_bounded_contract_without_leaking_token():
    calls = []

    def opener(request, **kwargs):
        calls.append((request, kwargs))
        return _Response(
            {
                "id": "response-7",
                "choices": [{"message": {"content": "  Antwort  "}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            },
            {"x-github-request-id": "github-7"},
        )

    ticks = iter((10.0, 10.125))
    provider = model_gateway.GitHubModels("super-secret", opener=opener, clock=lambda: next(ticks))
    result = provider.complete(_request(), timeout=12)

    sent, kwargs = calls[0]
    body = json.loads(sent.data.decode("utf-8"))
    assert sent.full_url == model_gateway.GITHUB_MODELS_URL
    assert sent.get_header("Authorization") == "Bearer super-secret"
    assert sent.get_header("X-github-api-version") == model_gateway.GITHUB_API_VERSION
    assert body == {
        "model": "openai/gpt-test",
        "messages": [{"role": "user", "content": "synthetische Frage"}],
        "max_tokens": 123,
        "temperature": 0.0,
        "stream": False,
    }
    assert kwargs["timeout"] == 12
    assert result.content == "Antwort"
    assert result.receipt.request_id == "github-7"
    assert result.receipt.elapsed_ms == 125
    assert result.receipt.input_tokens == 11
    assert result.receipt.output_tokens == 4
    assert "super-secret" not in repr(result)


def test_github_models_carries_a_strict_json_schema():
    captured = []

    def opener(request, **_):
        captured.append(json.loads(request.data.decode("utf-8")))
        return _Response({"choices": [{"message": {"content": "[]"}}]})

    schema = model_gateway.JsonSchema(
        "deuter_segmente",
        {"type": "array", "items": {"type": "object"}},
    )
    model_gateway.GitHubModels("x", opener=opener).complete(_request(schema=schema))
    response_format = captured[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "deuter_segmente"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == schema.schema


def test_remote_minimal_is_fail_closed_until_a_provider_is_explicitly_allowed():
    provider = model_gateway.GitHubModels("x", opener=lambda *_a, **_k: pytest.fail("network"))
    with pytest.raises(model_gateway.GatewayError, match="remote_minimal"):
        provider.complete(_request(privacy="remote_minimal"))


def test_provider_errors_are_honest_and_never_contain_the_secret():
    def opener(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://models.github.ai", 429, "rate", {}, None)

    provider = model_gateway.GitHubModels("do-not-leak", opener=opener)
    with pytest.raises(model_gateway.GatewayError, match="HTTP 429") as caught:
        provider.complete(_request())
    assert "do-not-leak" not in str(caught.value)


def test_read_secret_rejects_missing_and_empty_files(tmp_path):
    with pytest.raises(model_gateway.GatewayError, match="nicht lesbar"):
        model_gateway.read_secret(tmp_path / "missing")
    empty = tmp_path / "empty"
    empty.write_text("  ", encoding="utf-8")
    empty.chmod(0o600)
    with pytest.raises(model_gateway.GatewayError, match="leer"):
        model_gateway.read_secret(empty)


def test_stimme_public_check_is_the_same_fail_safe_line_for_remote_candidates():
    original = "Unter »Hund« versteht GENUS: Haustier, dessen Vorfahre der Wolf ist."
    good = "GENUS versteht unter »Hund« ein Haustier, dessen Vorfahre der Wolf ist."
    assert stimme.pruefe(original, good) == good
    assert stimme.pruefe(original, "GENUS versteht darunter ein Tier.") is None
    assert stimme.pruefe(original, original) is None


def test_stimme_rejects_provider_additions_even_when_every_old_anchor_survives():
    relation = "Ja — »Hund« zählt zu »Haustier«."
    extra_claims = (
        "Ja, das ist korrekt. Ein »Hund« ist ein »Haustier«. Hunde werden als Begleiter, "
        "Wachhunde oder als Teil der Familie gehalten."
    )
    short_new_content = "Ja — »Hund« zählt zur Kategorie »Haustier«."
    assert stimme.pruefe(relation, extra_claims) is None
    assert stimme.pruefe(relation, short_new_content) is None


def test_stimme_check_report_explains_rejections_without_echoing_content():
    original = "Ja — »Hund« zählt zu »Haustier«."
    candidate = "Ja — »Hund« zählt zur Kategorie »Haustier«."
    accepted, reason = stimme.pruefbericht(original, candidate)
    assert accepted is None
    assert reason == "neues_inhaltswort"
    assert "Kategorie" not in reason
    assert stimme.pruefbericht(original, original) == (None, "unveraendert")


class _FakeProvider:
    name = "fake-provider"

    def __init__(self):
        self.requests = []

    def complete(self, request, *, timeout):
        self.requests.append((request, timeout))
        original = request.messages[-1].content
        candidate = original + "!"
        return model_gateway.ModelResult(
            candidate,
            model_gateway.ModelReceipt(
                provider=self.name,
                model=request.model,
                request_id="fake-1",
                elapsed_ms=1,
                input_tokens=10,
                output_tokens=2,
                finish_reason="stop",
            ),
        )


def _args(**changes):
    values = {
        "model": ["vendor/a", "vendor/a"],
        "token_file": "never-read",
        "max_cases": 1,
        "max_requests": 2,
        "min_request_interval": 4.1,
        "timeout": 9.0,
    }
    values.update(changes)
    return argparse.Namespace(**values)


def test_bakeoff_deduplicates_models_and_sends_only_synthetic_answers(monkeypatch, capsys):
    monkeypatch.setattr(model_bakeoff, "_synthetic_answers", lambda _n: [("01", 0, "Hallo")])
    provider = _FakeProvider()
    assert model_bakeoff.run(_args(), provider=provider) == 0
    request, timeout = provider.requests[0]
    assert len(provider.requests) == 1
    assert request.privacy == "synthetic"
    assert request.role == "stimme"
    assert request.model == "vendor/a"
    assert timeout == 9.0
    row = json.loads(capsys.readouterr().out)
    assert row["accepted"] is True
    assert row["candidate"] == "Hallo!"
    assert row["raw_candidate"] == "Hallo!"
    assert row["validation"] == "akzeptiert"
    assert row["receipt"]["provider"] == "fake-provider"


def test_bakeoff_refuses_to_cross_its_request_budget(monkeypatch):
    monkeypatch.setattr(
        model_bakeoff,
        "_synthetic_answers",
        lambda _n: [("01", 0, "A"), ("02", 0, "B")],
    )
    with pytest.raises(ValueError, match="braeuchte 4 Aufrufe"):
        model_bakeoff.run(_args(model=["vendor/a", "vendor/b"], max_requests=3),
                          provider=_FakeProvider())


def test_bakeoff_spaces_requests_to_stay_below_the_free_minute_limit(monkeypatch):
    monkeypatch.setattr(
        model_bakeoff,
        "_synthetic_answers",
        lambda _n: [("01", 0, "A"), ("02", 0, "B")],
    )
    now = [10.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    provider = _FakeProvider()
    assert model_bakeoff.run(
        _args(max_requests=2),
        provider=provider,
        clock=lambda: now[0],
        sleeper=sleep,
    ) == 0
    assert len(provider.requests) == 2
    assert sleeps == [pytest.approx(4.1)]


@pytest.mark.parametrize("role", ["tool", "owner", ""])
def test_gateway_rejects_unknown_message_roles(role):
    with pytest.raises(ValueError, match="Nachrichtenrolle"):
        model_gateway.Message(role, "Text")
