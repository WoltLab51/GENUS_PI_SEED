"""Provider-neutrale Modell-Membran fuer GENUS.

Das Modul lebt absichtlich in ``deploy/``: Netzwerk und fremde Modelle duerfen den
deterministischen Kern nie importieren.  Es normalisiert nur einen kleinen
Chat-Completions-Vertrag und liefert einen Beleg ueber Modell, Laufzeit und Token zurueck.
Providertext ist immer ein ENTWURF; fachliche Pruefung bleibt beim aufrufenden Organ.

Der erste Adapter ist GitHub Models. Weitere Provider bekommen eigene Adapter, statt dass
GENUS ihre nur oberflaechlich aehnlichen APIs mit einer einzigen Anbieterlogik verwechselt.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import ssl
import time
from typing import Callable, Mapping, Sequence
import urllib.error
import urllib.request


GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
GITHUB_API_VERSION = "2026-03-10"
DEFAULT_TOKEN_FILE = os.path.expanduser("~/.genus/github_models_token")
_ROLES = frozenset({"system", "developer", "user", "assistant"})
_PRIVACY = frozenset({"synthetic", "remote_minimal", "repository_source"})


class GatewayError(RuntimeError):
    """Ehrlicher, geheimnisfreier Fehler an der Modell-Membran."""


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise ValueError(f"unbekannte Nachrichtenrolle: {self.role}")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("eine Modellnachricht braucht Text")


@dataclass(frozen=True, slots=True)
class JsonSchema:
    name: str
    schema: Mapping[str, object]
    strict: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError("Schema-Name muss alphanumerisch sein (Unterstrich erlaubt)")
        if self.schema.get("type") not in {"object", "array"}:
            raise ValueError("Wurzelschema muss object oder array sein")

    def github_format(self) -> dict[str, object]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": self.name,
                "strict": self.strict,
                "schema": dict(self.schema),
            },
        }


@dataclass(frozen=True, slots=True)
class ModelRequest:
    role: str
    model: str
    messages: tuple[Message, ...]
    privacy: str = "synthetic"
    max_output_tokens: int = 200
    temperature: float = 0.0
    schema: JsonSchema | None = None

    def __post_init__(self) -> None:
        if not self.role.strip() or not self.model.strip():
            raise ValueError("Rolle und Modell muessen gesetzt sein")
        if not self.messages:
            raise ValueError("mindestens eine Modellnachricht ist erforderlich")
        if self.privacy not in _PRIVACY:
            raise ValueError(f"unbekannte Datenschutzklasse: {self.privacy}")
        if not 1 <= self.max_output_tokens <= 4096:
            raise ValueError("max_output_tokens ausserhalb 1..4096")
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("temperature ausserhalb 0..1")


@dataclass(frozen=True, slots=True)
class ModelReceipt:
    provider: str
    model: str
    request_id: str | None
    elapsed_ms: int
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ModelResult:
    content: str
    receipt: ModelReceipt


def read_secret(path: str | os.PathLike[str]) -> str:
    """Liest ein Secret aus einer eigenen Datei und prueft Unix-Rechte fail-closed."""
    secret_path = Path(path).expanduser()
    try:
        stat = secret_path.stat()
    except OSError as exc:
        raise GatewayError(f"Secret-Datei nicht lesbar: {secret_path}") from exc
    if os.name == "posix" and stat.st_mode & 0o077:
        raise GatewayError(f"Secret-Datei muss chmod 600 sein: {secret_path}")
    try:
        value = secret_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise GatewayError(f"Secret-Datei nicht lesbar: {secret_path}") from exc
    if not value:
        raise GatewayError(f"Secret-Datei ist leer: {secret_path}")
    return value


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _response_parts(body: object) -> tuple[str, str | None, int | None, int | None]:
    if not isinstance(body, dict):
        raise GatewayError("Provider-Antwort ist kein JSON-Objekt")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise GatewayError("Provider-Antwort enthaelt keine Auswahl")
    first = choices[0]
    message = first.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise GatewayError("Provider-Antwort enthaelt keinen Text")
    finish = first.get("finish_reason")
    finish = finish if isinstance(finish, str) else None
    usage = body.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = _int_or_none(usage.get("prompt_tokens", usage.get("input_tokens")))
    output_tokens = _int_or_none(usage.get("completion_tokens", usage.get("output_tokens")))
    return content.strip(), finish, input_tokens, output_tokens


OpenFn = Callable[..., object]


class GitHubModels:
    """GitHub-Models-Adapter mit expliziter Datenschutz- und Token-Grenze."""

    name = "github-models"

    def __init__(
        self,
        token: str,
        *,
        endpoint: str = GITHUB_MODELS_URL,
        allowed_privacy: frozenset[str] = frozenset({"synthetic"}),
        opener: OpenFn = urllib.request.urlopen,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not token.strip():
            raise ValueError("GitHub Models braucht ein Token")
        if not allowed_privacy or not allowed_privacy <= _PRIVACY:
            raise ValueError("ungueltige Provider-Datenschutzklassen")
        self._token = token.strip()
        self.endpoint = endpoint
        self.allowed_privacy = allowed_privacy
        self._opener = opener
        self._clock = clock
        self._ssl = ssl.create_default_context()

    def _payload(self, request: ModelRequest) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [asdict(message) for message in request.messages],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        if request.schema is not None:
            payload["response_format"] = request.schema.github_format()
        return payload

    def complete(self, request: ModelRequest, *, timeout: float = 30.0) -> ModelResult:
        if request.privacy not in self.allowed_privacy:
            raise GatewayError(
                f"Provider {self.name} erlaubt Datenschutzklasse {request.privacy!r} nicht"
            )
        if not 1.0 <= timeout <= 120.0:
            raise ValueError("timeout ausserhalb 1..120 Sekunden")
        raw = json.dumps(self._payload(request), ensure_ascii=False).encode("utf-8")
        http_request = urllib.request.Request(
            self.endpoint,
            data=raw,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "GENUS-PI/model-gateway",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )
        started = self._clock()
        try:
            with self._opener(http_request, timeout=timeout, context=self._ssl) as response:
                response_body = json.loads(response.read().decode("utf-8"))
                request_id = response.headers.get("x-github-request-id")
        except urllib.error.HTTPError as exc:
            if (request.privacy == "synthetic"
                    and os.environ.get("GENUS_MODEL_GATEWAY_DIAGNOSTICS") == "synthetic-only"):
                try:
                    detail = exc.read(500).decode("utf-8", errors="replace").replace("\n", " ")
                except OSError:
                    detail = ""
                raise GatewayError(f"GitHub Models HTTP {exc.code}: {detail}") from exc
            raise GatewayError(f"GitHub Models HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise GatewayError("GitHub Models nicht erreichbar") from exc
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise GatewayError("GitHub Models lieferte kein gueltiges JSON") from exc
        elapsed = max(0, round((self._clock() - started) * 1000))
        content, finish, input_tokens, output_tokens = _response_parts(response_body)
        body_id = response_body.get("id") if isinstance(response_body, dict) else None
        if request_id is None and isinstance(body_id, str):
            request_id = body_id
        return ModelResult(
            content=content,
            receipt=ModelReceipt(
                provider=self.name,
                model=request.model,
                request_id=request_id,
                elapsed_ms=elapsed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=finish,
            ),
        )


def github_from_token_file(
    path: str | os.PathLike[str] = DEFAULT_TOKEN_FILE,
    *,
    allow_remote_minimal: bool = False,
    allow_repository_source: bool = False,
) -> GitHubModels:
    privacy = {"synthetic"}
    if allow_remote_minimal:
        privacy.add("remote_minimal")
    if allow_repository_source:
        privacy.add("repository_source")
    return GitHubModels(read_secret(path), allowed_privacy=frozenset(privacy))
