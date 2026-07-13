"""Hermetische, menschenlesbare Alltagsprobe fuer GENUS-Antworten.

Die Probe ist absichtlich weder Belohnungsfunktion noch LLM-Richter. Harte
Vertraege pruefen Treue, Ehrlichkeit, Richtung, Anschluss und Datenschutz auf
synthetischen In-Memory-Daten. Ton und Nutzen bleiben eine menschliche Abnahme;
ihre Freigabe ist an Fall- und Antwort-Hashes gebunden und wird bei jeder
Aenderung automatisch veraltet.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from genus import antwort, companion, reactors, verstehen
from genus.db import init_schema


SCHEMA = "genus-alltagsprobe-v1"
SUITE_VERSION = "2026-07-13.1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEWS = ROOT / "docs" / "reviews" / "ALLTAGSPROBE_V1.json"

DIMENSION_LABELS = {
    "treue": "Fakten- und Richtungstreue",
    "ehrlichkeit": "Nichtwissen und Unsicherheit",
    "provenienz": "Herkunft und Nachvollziehbarkeit",
    "transparenz": "Modelltransparenz",
    "dialog": "Dialoganschluss",
    "komposition": "Mehrteilige Antworten",
    "alltagsform": "Bekannte Alltagsreibungen",
    "datenschutz": "Datensparsamkeit",
}

GATE_KINDS = frozenset({
    "outcome",
    "readings",
    "text_contains",
    "text_excludes",
    "text_order",
    "text_count",
    "anchor",
    "key_present",
    "key_absent",
    "draft_resolution",
    "draft_claim",
    "draft_no_claims",
    "draft_sources_include",
    "draft_reading_source",
})
REVIEW_VALUES = frozenset({"traegt", "holprig", "unbrauchbar"})


@dataclass(frozen=True, slots=True)
class Relation:
    subject: str
    predicate: str
    object: str
    source: str


@dataclass(frozen=True, slots=True)
class Turn:
    question: str
    readings: tuple[dict[str, object], ...] | None = None


@dataclass(frozen=True, slots=True)
class Gate:
    dimension: str
    kind: str
    expected: object
    description: str
    turn: int = -1

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSION_LABELS:
            raise ValueError(f"Unbekannte Qualitaetsdimension: {self.dimension}")
        if self.kind not in GATE_KINDS:
            raise ValueError(f"Unbekannter Gate-Typ: {self.kind}")
        if not self.description.strip():
            raise ValueError("Ein Gate braucht eine lesbare Beschreibung.")


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    title: str
    purpose: str
    relations: tuple[Relation, ...]
    turns: tuple[Turn, ...]
    gates: tuple[Gate, ...]
    human_prompt: str


@dataclass(frozen=True, slots=True)
class Review:
    case_id: str
    case_fingerprint: str
    response_sha256: str
    ton: str
    nutzen: str
    reviewer: str
    reviewed_at: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class TurnResult:
    question: str
    text: str
    outcome: str
    readings: tuple[str, ...]
    anchor: str
    followup: str | None
    original_keys: tuple[str, ...]
    normalized_fields: tuple[str, ...]
    drafts: tuple[dict[str, object], ...]
    frames: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class GateResult:
    dimension: str
    kind: str
    description: str
    expected: object
    actual: object
    passed: bool
    turn: int


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    id: str
    title: str
    purpose: str
    turns: tuple[TurnResult, ...]
    gates: tuple[GateResult, ...]
    hard_ok: bool
    case_fingerprint: str
    response_sha256: str
    human_status: str
    human_prompt: str
    review: Review | None


@dataclass(frozen=True, slots=True)
class SuiteResult:
    schema: str
    suite_version: str
    cases: tuple[ScenarioResult, ...]
    dimensions: dict[str, dict[str, int]]
    hard_ok: bool
    human_statuses: dict[str, int]
    content_sha256: str


def _r(subject: str, predicate: str, object_: str, source: str) -> Relation:
    return Relation(subject, predicate, object_, source)


def _g(
    dimension: str,
    kind: str,
    expected: object,
    description: str,
    turn: int = -1,
) -> Gate:
    return Gate(dimension, kind, expected, description, turn)


HUND_NETZ = (
    _r("Hund@de", "expresses", "Q144", "wikidata"),
    _r("Haustier@de", "expresses", "Q1001", "wikidata"),
    _r("Säugetier@de", "expresses", "Q1002", "wikidata"),
    _r("Reptil@de", "expresses", "Q1003", "wikidata"),
    _r("Q144", "is_a", "Q1001", "wikidata"),
    _r("Q1001", "is_a", "Q1002", "wikidata"),
)
HUND_WISSEN = HUND_NETZ + (
    _r("Hund@de", "primary_gloss", "ein Haustier, dessen Vorfahre der Wolf ist", "dbnary"),
)


ALLTAGSFAELLE: tuple[Scenario, ...] = (
    Scenario(
        "01-gruss-ohne-technikrest",
        "Ein natürlicher Gruß",
        "Eine soziale Geste soll warm beantwortet werden, ohne technischen Nachspann.",
        (),
        (Turn("Moin, schön dich zu sehen!", ({
            "text": "Moin, schön dich zu sehen!", "absicht": "gruss",
        },)),),
        (
            _g("alltagsform", "text_contains", "Hallo", "Der Gruß wird sozial beantwortet."),
            _g("alltagsform", "text_excludes", ("Sprachmodell", "kann ich noch nicht"),
               "Kein Technikrest und keine falsche Fähigkeitslücke."),
            _g("transparenz", "readings", ("gruss",), "Die strukturelle Lesart bleibt sichtbar."),
            _g("ehrlichkeit", "outcome", "answered", "Der Zug ist als beantwortet eingeordnet."),
        ),
        "Klingt dieser Einstieg wie ein warmer, unaufdringlicher GENUS-Gruß?",
    ),
    Scenario(
        "02-definition-hund",
        "Belegte Alltagsdefinition",
        "Eine bekannte Bedeutung und ihr Elternbegriff müssen vollständig erhalten bleiben.",
        HUND_WISSEN,
        (Turn("Was ist ein Hund?"),),
        (
            _g("treue", "draft_claim", ("Hund", "defined_as", "ein Haustier, dessen Vorfahre der Wolf ist"),
               "Die Bedeutung ist ein strukturierter Claim."),
            _g("treue", "draft_claim", ("Hund", "is_a", "Haustier"),
               "Der belegte Elternbegriff bleibt erhalten."),
            _g("provenienz", "draft_sources_include", ("dbnary", "wikidata"),
               "Bedeutung und Hierarchie tragen ihre Quellen."),
            _g("treue", "text_contains", ("Hund", "Haustier", "Wolf"),
               "Die Antwort spricht alle tragenden Begriffe aus."),
            _g("alltagsform", "text_excludes", ("Q144", "Q1001", "genus concept", "genus why"),
               "Interne IDs und CLI-Anweisungen bleiben aus dem Dialog."),
            _g("ehrlichkeit", "outcome", "answered", "Die Definition ist beantwortet."),
        ),
        "Erklärt GENUS den Begriff direkt, klar und ohne Lexikon- oder CLI-Gefühl?",
    ),
    Scenario(
        "03-definition-schwach",
        "Schwach belegte Bedeutung",
        "Eine Modellbrücke darf ihre geringe Sicherheit auch in kurzer Form nie verstecken.",
        (_r("Blub@de", "primary_gloss", "ein kaum belegter Testbegriff", "model:embedder"),),
        (Turn("Was ist Blub?"),),
        (
            _g("treue", "draft_claim", ("Blub", "defined_as", "ein kaum belegter Testbegriff"),
               "Der schwache Claim bleibt strukturell greifbar."),
            _g("ehrlichkeit", "text_contains", ("vorsichtig", "schwach belegt"),
               "Unsicherheit wird unmissverständlich ausgesprochen."),
            _g("ehrlichkeit", "outcome", "answered", "Unsichere Antwort ist nicht mit Nichtverstehen vermischt."),
        ),
        "Ist die Unsicherheit klar, ohne dass die Antwort defensiv oder mechanisch klingt?",
    ),
    Scenario(
        "04-definition-korroboriert",
        "Unabhängig bestätigte Bedeutung",
        "Zwei unabhängige Quellen sollen als Korroboration und nicht als Doppelzählung erscheinen.",
        (
            _r("Blub@de", "primary_gloss", "ein gemeinsam belegter Testbegriff", "dbnary"),
            _r("Blub@de", "primary_gloss", "ein gemeinsam belegter Testbegriff", "wikidata-lexemes"),
        ),
        (Turn("Was ist Blub?"),),
        (
            _g("provenienz", "draft_sources_include", ("dbnary", "wikidata-lexemes"),
               "Beide unabhängigen Quellen stehen am Claim."),
            _g("provenienz", "text_contains", "mehrfach unabhängig belegt",
               "Die Korroboration wird verständlich benannt."),
            _g("ehrlichkeit", "outcome", "answered", "Die Bedeutung ist beantwortet."),
        ),
        "Wirkt der Vertrauenshinweis hilfreich oder unterbricht er den natürlichen Fluss?",
    ),
    Scenario(
        "05-beziehung-direkt",
        "Direkte gerichtete Beziehung",
        "Subjekt, Objekt und Richtung dürfen in einer natürlichen Kurzantwort nie kippen.",
        HUND_NETZ,
        (Turn("Ist ein Hund ein Haustier?"),),
        (
            _g("treue", "draft_claim", ("Hund", "is_a", "Haustier"),
               "Die gerichtete Kante ist ein Claim."),
            _g("treue", "text_contains", "»Hund« zählt zu »Haustier«",
               "Der unveränderliche Richtungskern steht in der Antwort."),
            _g("treue", "text_order", ("Hund", "Haustier"), "Subjekt steht vor Objekt."),
            _g("alltagsform", "text_excludes", ("Wissensnetz", "nicht bloß behauptet", "Mehr Herkunft"),
               "Die direkte Antwort trägt keinen ungefragten Auditvortrag."),
            _g("ehrlichkeit", "outcome", "answered", "Die bekannte Verbindung ist beantwortet."),
        ),
        "Ist die Antwort so direkt, wie du sie in einem echten Gespräch erwartest?",
    ),
    Scenario(
        "06-beziehung-transitiv",
        "Mehrstufige Herleitung",
        "Eine transitive Antwort muss den belegten Zwischenweg bewahren.",
        HUND_NETZ,
        (Turn("Ist ein Hund ein Säugetier?"),),
        (
            _g("treue", "draft_claim", ("Hund", "is_a", "Säugetier"),
               "Die abgeleitete Zielbeziehung bleibt explizit."),
            _g("treue", "text_contains", ("Hund", "Haustier", "Säugetier", "→"),
               "Die vollständige Kette erscheint sichtbar in der Antwort."),
            _g("provenienz", "draft_sources_include", ("wikidata",),
               "Die Herleitung trägt ihre Quelle."),
            _g("alltagsform", "text_excludes", ("Q144", "Q1001", "Q1002", "Wissensnetz"),
               "Der Gesprächspfad zeigt Begriffe statt interner IDs oder Auditjargon."),
            _g("ehrlichkeit", "outcome", "answered", "Die herleitbare Beziehung ist beantwortet."),
        ),
        "Ist der sichtbare Weg hilfreich, oder sollte GENUS ihn erst auf Nachfrage zeigen?",
    ),
    Scenario(
        "07-beziehung-offen",
        "Offene Welt statt falsches Nein",
        "Eine fehlende Kante ist Nichtwissen und niemals ein negativer Fakt.",
        HUND_NETZ,
        (Turn("Ist ein Hund ein Reptil?"),),
        (
            _g("ehrlichkeit", "draft_resolution", "understood_unknown",
               "Der Draft unterscheidet Nichtwissen von einer Antwort."),
            _g("ehrlichkeit", "draft_no_claims", True,
               "Aus einem fehlenden Pfad entsteht kein negativer Claim."),
            _g("ehrlichkeit", "text_contains", "unbekannt, nicht widerlegt",
               "Die offene Welt wird in Alltagssprache erklärt."),
            _g("treue", "text_excludes", ("zählt nicht", "Nein."),
               "Die Antwort behauptet keine Widerlegung."),
            _g("ehrlichkeit", "outcome", "understood_unknown", "Das Outcome bleibt ehrlich offen."),
        ),
        "Ist diese Enthaltung klar genug, ohne ausweichend zu wirken?",
    ),
    Scenario(
        "08-deuter-leer",
        "Ehrliches Nichtverstehen",
        "Ein gelaufener Deuter ohne Lesart darf nicht in einen gierigen Wortfund ausweichen.",
        HUND_WISSEN,
        (Turn("Okay prima, frobniziere das mal.", ()),),
        (
            _g("ehrlichkeit", "outcome", "fallback", "Der leere Deuter-Lauf endet im Fallback."),
            _g("ehrlichkeit", "text_contains", ("nicht sicher verstanden", "worum es geht", "was du von mir brauchst"),
               "GENUS benennt das Nichtverstehen und fragt nach Ziel und Kontext."),
            _g("treue", "text_excludes", ("Hund", "Haustier", "prima bedeutet"),
               "Es wird kein zufällig bekanntes Wort erklärt."),
        ),
        "Hilft die Rückfrage beim Weitermachen, oder bleibt sie zu flach?",
    ),
    Scenario(
        "09-pflichtslot-fehlt",
        "Unvollständige Beziehung",
        "Eine erkannte Beziehung ohne Ziel darf keine Kante erfinden.",
        HUND_NETZ,
        (Turn("Ist Hund?", ({"absicht": "beziehung", "subject": "Hund", "object": None},)),),
        (
            _g("ehrlichkeit", "outcome", "invalid_slots", "Der fehlende Pflichtslot bleibt sichtbar."),
            _g("transparenz", "readings", ("beziehung",), "Die erkannte Absicht geht nicht verloren."),
            _g("dialog", "text_contains", ("mir fehlt", "Ziel", "Wozu"),
               "Die Rückfrage benennt konkret den fehlenden Teil."),
            _g("treue", "text_excludes", ("zählt zu", "ist ein Haustier"),
               "GENUS vervollständigt die Beziehung nicht aus eigenem Antrieb."),
        ),
        "Führt die Antwort konkret genug zu einer besseren Frage zurück?",
    ),
    Scenario(
        "10-freie-definition",
        "Freie Formulierung, graphgeprüft",
        "Eine Modell-Lesart darf nur zu graphbelegtem Inhalt führen und wird genau einmal offengelegt.",
        HUND_WISSEN,
        (Turn("Sag mal, was steckt eigentlich hinter wuffwuff?", ({
            "absicht": "definition", "subject": "Hund", "object": None,
        },)),),
        (
            _g("treue", "draft_claim", ("Hund", "defined_as", "ein Haustier, dessen Vorfahre der Wolf ist"),
               "Die freie Formulierung landet beim belegten Claim."),
            _g("transparenz", "draft_reading_source", "model:deuter",
               "Der Draft kennt die Herkunft der Lesart."),
            _g("transparenz", "text_count", ("Frage vom Sprachmodell gedeutet", 1),
               "Modellhilfe wird genau einmal, nicht geräuschvoll mehrfach offengelegt."),
            _g("ehrlichkeit", "outcome", "answered", "Die belegte Definition ist beantwortet."),
        ),
        "Wirkt die Offenlegung passend dosiert, während die Antwort selbst natürlich bleibt?",
    ),
    Scenario(
        "11-empfehlung-noch-nicht",
        "Verstandene, noch nicht beherrschte Bitte",
        "Eine bekannte Absicht ohne Werkzeug wird benannt, nicht als Inhalt halluziniert.",
        (),
        (Turn("Welches Haustier würde zu mir passen?", ({
            "absicht": "empfehlungsfrage", "subject": "Haustier", "object": None,
        },)),),
        (
            _g("ehrlichkeit", "outcome", "understood_unknown",
               "Verstanden und noch nicht beherrscht bleibt eine eigene Kategorie."),
            _g("ehrlichkeit", "text_contains", ("Empfehlung", "noch nicht"),
               "GENUS benennt Absicht und Grenze."),
            _g("treue", "text_excludes", ("empfehle dir", "am besten einen"),
               "Es wird keine Empfehlung erfunden."),
        ),
        "Ist die Grenze brauchbar formuliert und bietet sie einen sinnvollen nächsten Schritt?",
    ),
    Scenario(
        "12-warum-rueckbezug",
        "Warum bleibt am Thema",
        "Eine knappe Warum-Frage muss die vorige Beziehung mit Quelle und Vertrauen nachzeichnen.",
        HUND_NETZ,
        (Turn("Ist ein Hund ein Haustier?"), Turn("warum?")),
        (
            _g("dialog", "anchor", "Ist ein Hund ein Haustier?",
               "Die Folgefrage bleibt am ursprünglichen Sachthema."),
            _g("provenienz", "text_contains", ("Herleitung", "wikidata", "Vertrauen"),
               "Die Belegspur wird auf Nachfrage sichtbar."),
            _g("ehrlichkeit", "outcome", "answered", "Die Herkunftsfrage wird beantwortet."),
        ),
        "Ist die Herleitung lesbar genug, um Vertrauen zu schaffen statt nur Technik zu zeigen?",
    ),
    Scenario(
        "13-anschluss-ja",
        "Ein angebotenes Thema wird eingelöst",
        "Ein knappes Ja beantwortet exakt das verifizierte Angebot und startet keine Endlosschleife.",
        (
            _r("Vulkan@de", "expresses", "Q_vulkan", "wikidata"),
            _r("Vulkan@de", "primary_gloss", "eine Öffnung in der Erdkruste", "dbnary"),
            _r("Q_vulkan", "causes", "Q_ausbruch", "wikidata"),
            _r("Ausbruch@de", "expresses", "Q_ausbruch", "wikidata"),
            _r("Ausbruch@de", "primary_gloss", "eine Entladung von Magma", "dbnary"),
        ),
        (Turn("Was ist ein Vulkan?"), Turn("ja")),
        (
            _g("dialog", "key_present", "anschluss", "Der erste Zug trägt sein echtes Angebot.", 0),
            _g("dialog", "text_contains", "Wenn du magst", "Das Angebot ist im ersten Zug sichtbar.", 0),
            _g("dialog", "anchor", "Was ist Ausbruch?", "Das Ja wird auf das angebotene Thema aufgelöst."),
            _g("treue", "text_contains", ("Ausbruch", "Entladung von Magma"),
               "Die Einlösung nutzt nur die belegte Bedeutung."),
            _g("dialog", "key_absent", "anschluss", "Die Einlösung erzeugt keinen neuen Sog."),
        ),
        "Fühlt sich Angebot plus Einlösung wie ein zusammenhängendes Gespräch an?",
    ),
    Scenario(
        "14-von-vorhin",
        "Rückbezug über eine Floskel hinweg",
        "Ein Sachthema darf nach einem Gruß nicht aus dem kleinen Dialograhmen fallen.",
        (
            _r("Fahrrad@de", "expresses", "Q_fahrrad", "wikidata"),
            _r("Fahrrad@de", "primary_gloss", "ein Zweirad zum Fahren", "dbnary"),
        ),
        (
            Turn("Was ist ein Fahrrad?"),
            Turn("Moin!", ({"text": "Moin!", "absicht": "gruss"},)),
            Turn("Was war das nochmal von vorhin?"),
        ),
        (
            _g("dialog", "anchor", "Was ist ein Fahrrad?", "Der Rückbezug findet das Sachthema wieder."),
            _g("dialog", "text_contains", ("Zweirad", "frühere Frage", "Was ist ein Fahrrad?"),
               "Antwort und sichtbarer Rückbezug passen zusammen."),
            _g("treue", "text_excludes", "Moin bedeutet", "Die Floskel wird nicht zum Sachthema gemacht."),
        ),
        "Ist der Rückbezug hilfreich, ohne den Dialog mit Metatext zu überladen?",
    ),
    Scenario(
        "15-mehrsegment",
        "Gruß, Frage und Dank in einer Nachricht",
        "Mehrere Sprechhandlungen müssen gemeinsam aufgelöst und ruhig komponiert werden.",
        HUND_WISSEN,
        (Turn("Hallo! Was ist ein Hund? Danke dir.", (
            {"text": "Hallo!", "absicht": "gruss"},
            {"text": "Was ist ein Hund?", "absicht": "definition", "subject": "Hund"},
            {"text": "Danke dir.", "absicht": "dank"},
        )),),
        (
            _g("komposition", "readings", ("gruss", "definition", "dank"),
               "Alle drei Lesarten bleiben erhalten."),
            _g("komposition", "text_contains", ("Hallo", "Wolf", "Gern geschehen"),
               "Jede Sprechhandlung trägt eine sichtbare Teilwirkung."),
            _g("alltagsform", "text_excludes", "Was beschäftigt dich gerade?",
               "Der Gruß stellt keine Gegenfrage, wenn die Nachricht schon ein Anliegen enthält."),
            _g("transparenz", "text_count", ("Frage vom Sprachmodell gedeutet", 1),
               "Der gemeinsame Modellhinweis erscheint höchstens einmal."),
            _g("ehrlichkeit", "outcome", "answered", "Die gesamte Nachricht ist beantwortet."),
        ),
        "Liest sich die zusammengesetzte Antwort wie ein Zug statt wie drei Textbausteine?",
    ),
    Scenario(
        "16-mehrsegment-mit-luecke",
        "Gruß plus unvollständige Frage",
        "Eine freundliche Teilantwort darf die ungelöste Sachfrage nicht als Erfolg verdecken.",
        (),
        (Turn("Hallo, ist Hund?", (
            {"text": "Hallo", "absicht": "gruss"},
            {"text": "ist Hund?", "absicht": "beziehung", "subject": "Hund", "object": None},
        )),),
        (
            _g("komposition", "text_contains", "Hallo", "Der lösbare soziale Teil bleibt erhalten."),
            _g("dialog", "text_contains", ("mir fehlt", "Ziel", "Wozu"),
               "Der offene Sachteil erhält eine konkrete Klärungsfrage."),
            _g("ehrlichkeit", "outcome", "invalid_slots", "Die Sachlücke bestimmt konservativ das Gesamtoutcome."),
            _g("treue", "text_excludes", "zählt zu", "Die fehlende Beziehung wird nicht ergänzt."),
        ),
        "Macht GENUS deutlich genug, welcher Teil noch offen ist?",
    ),
    Scenario(
        "17-enge-korrektur",
        "Eine Lesart wird gezielt korrigiert",
        "Die Korrektur bezieht sich auf die letzte strukturelle Lesart, nicht auf gespeicherten Rohtext.",
        HUND_NETZ,
        (
            Turn("Gehört so ein Wuff eigentlich zu Haustieren?", ({
                "absicht": "beziehung", "subject": "Hund", "object": "Haustier",
            },)),
            Turn("falsch verstanden: definition"),
        ),
        (
            _g("dialog", "text_contains", ("Korrektur", "beziehung", "definition", "festgehalten"),
               "Fehlgriff und gemeinte Lesart werden nachvollziehbar bestätigt."),
            _g("dialog", "anchor", "Gehört so ein Wuff eigentlich zu Haustieren?",
               "Die Korrektur bleibt am korrigierten Zug verankert."),
            _g("ehrlichkeit", "outcome", "answered", "Die enge Korrektur wurde angenommen."),
        ),
        "Fühlt sich die Korrekturbestätigung klar und nicht übertechnisch an?",
    ),
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def scenario_fingerprint(scenario: Scenario) -> str:
    return _sha256(asdict(scenario))


def _draft_snapshot(draft: antwort.AnswerDraft) -> dict[str, object]:
    return {
        "kind": draft.kind,
        "resolution": draft.resolution,
        "focus": list(draft.focus) if draft.focus else None,
        "anchors": list(draft.anchors),
        "verbatim_core": draft.verbatim_core,
        "reading_source": draft.reading_source,
        "claims": [
            {
                "subject": claim.subject,
                "predicate": claim.predicate,
                "object": claim.object,
                "confidence": claim.confidence,
                "derived": claim.derived,
                "sources": sorted({evidence.source for evidence in claim.evidence}),
            }
            for claim in draft.claims
        ],
    }


def _frame_snapshot(frame: antwort.DialogueFrame) -> dict[str, object]:
    return asdict(frame)


def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    verstehen.seed_raster(conn)
    return conn


def _normalise_result(
    question: str,
    result: dict,
    captured: list[tuple[antwort.AnswerDraft, antwort.DialogueFrame]],
) -> TurnResult:
    missing = tuple(field for field in ("outcome", "gelesen") if field not in result)
    outcome = str(result.get("outcome") or "answered")
    readings = tuple(str(value) for value in (result.get("gelesen") or ()))
    return TurnResult(
        question=question,
        text=str(result.get("text") or ""),
        outcome=outcome,
        readings=readings,
        anchor=str(result.get("question") or question),
        followup=str(result["anschluss"]) if result.get("anschluss") else None,
        original_keys=tuple(sorted(result)),
        normalized_fields=missing,
        drafts=tuple(_draft_snapshot(draft) for draft, _ in captured),
        frames=tuple(_frame_snapshot(frame) for _, frame in captured),
    )


def _turn_at(turns: tuple[TurnResult, ...], index: int) -> TurnResult:
    try:
        return turns[index]
    except IndexError as exc:
        raise ValueError(f"Gate verweist auf fehlenden Zug {index}.") from exc


def _claims(turn: TurnResult) -> list[tuple[str, str, str]]:
    return [
        (str(claim["subject"]), str(claim["predicate"]), str(claim["object"]))
        for draft in turn.drafts
        for claim in draft["claims"]  # type: ignore[index]
    ]


def _sources(turn: TurnResult) -> set[str]:
    return {
        str(source)
        for draft in turn.drafts
        for claim in draft["claims"]  # type: ignore[index]
        for source in claim["sources"]
    }


def _evaluate_gate(gate: Gate, turns: tuple[TurnResult, ...]) -> GateResult:
    turn = _turn_at(turns, gate.turn)
    expected = gate.expected
    if gate.kind == "outcome":
        actual, passed = turn.outcome, turn.outcome == expected
    elif gate.kind == "readings":
        actual, passed = turn.readings, turn.readings == tuple(expected)  # type: ignore[arg-type]
    elif gate.kind == "text_contains":
        needles = (expected,) if isinstance(expected, str) else tuple(expected)  # type: ignore[arg-type]
        actual = tuple(needle for needle in needles if str(needle) in turn.text)
        passed = len(actual) == len(needles)
    elif gate.kind == "text_excludes":
        needles = (expected,) if isinstance(expected, str) else tuple(expected)  # type: ignore[arg-type]
        actual = tuple(needle for needle in needles if str(needle) in turn.text)
        passed = not actual
    elif gate.kind == "text_order":
        needles = tuple(str(value) for value in expected)  # type: ignore[arg-type]
        positions = tuple(turn.text.find(value) for value in needles)
        actual = positions
        passed = all(position >= 0 for position in positions) and list(positions) == sorted(positions)
    elif gate.kind == "text_count":
        needle, count = expected  # type: ignore[misc]
        actual = turn.text.count(str(needle))
        passed = actual == count
    elif gate.kind == "anchor":
        actual, passed = turn.anchor, turn.anchor == expected
    elif gate.kind == "key_present":
        actual = str(expected) in turn.original_keys
        passed = actual
    elif gate.kind == "key_absent":
        actual = str(expected) not in turn.original_keys
        passed = actual
    elif gate.kind == "draft_resolution":
        actual = tuple(draft["resolution"] for draft in turn.drafts)
        passed = expected in actual
    elif gate.kind == "draft_claim":
        actual = _claims(turn)
        passed = tuple(expected) in actual  # type: ignore[arg-type]
    elif gate.kind == "draft_no_claims":
        actual = bool(turn.drafts) and not _claims(turn)
        passed = actual is bool(expected)
    elif gate.kind == "draft_sources_include":
        actual = tuple(sorted(_sources(turn)))
        passed = set(expected).issubset(actual)  # type: ignore[arg-type]
    elif gate.kind == "draft_reading_source":
        actual = tuple(draft["reading_source"] for draft in turn.drafts)
        passed = expected in actual
    else:  # pragma: no cover - Gate validates this before execution
        raise ValueError(gate.kind)
    return GateResult(
        dimension=gate.dimension,
        kind=gate.kind,
        description=gate.description,
        expected=expected,
        actual=actual,
        passed=bool(passed),
        turn=gate.turn,
    )


def validate_suite(cases: tuple[Scenario, ...] = ALLTAGSFAELLE) -> None:
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Alltagsfall-IDs muessen eindeutig sein.")
    if not cases:
        raise ValueError("Die Alltagsprobe darf nicht leer sein.")
    covered = {gate.dimension for case in cases for gate in case.gates} | {"datenschutz"}
    missing = set(DIMENSION_LABELS) - covered
    if missing:
        raise ValueError("Dimensionen ohne Fall: " + ", ".join(sorted(missing)))
    for case in cases:
        if not case.id.strip() or not case.title.strip() or not case.turns or not case.gates:
            raise ValueError(f"Unvollstaendiger Alltagsfall: {case.id!r}")
        if not case.human_prompt.strip():
            raise ValueError(f"Alltagsfall ohne menschliche Prueffrage: {case.id}")
        for turn in case.turns:
            if not turn.question.strip():
                raise ValueError(f"Leerer Dialogzug in {case.id}")


def load_reviews(path: str | Path | None = None) -> dict[str, Review]:
    review_path = Path(path) if path is not None else DEFAULT_REVIEWS
    if not review_path.exists():
        return {}
    raw = json.loads(review_path.read_text(encoding="utf-8"))
    if set(raw) != {"schema", "reviews"} or raw["schema"] != SCHEMA:
        raise ValueError("Freigabedatei braucht exakt schema und reviews fuer genus-alltagsprobe-v1.")
    if not isinstance(raw["reviews"], list):
        raise ValueError("reviews muss eine Liste sein.")
    expected_keys = {
        "case_id", "case_fingerprint", "response_sha256", "ton", "nutzen",
        "reviewer", "reviewed_at", "note",
    }
    reviews: dict[str, Review] = {}
    for item in raw["reviews"]:
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise ValueError("Jede Freigabe braucht exakt die dokumentierten acht Felder.")
        review = Review(**item)
        if review.ton not in REVIEW_VALUES or review.nutzen not in REVIEW_VALUES:
            raise ValueError("ton und nutzen muessen traegt, holprig oder unbrauchbar sein.")
        if not review.case_id or not review.reviewer or not review.reviewed_at:
            raise ValueError("Freigaben brauchen Fall, Reviewer und Zeitpunkt.")
        if review.case_id in reviews:
            raise ValueError(f"Doppelte Freigabe fuer {review.case_id}")
        reviews[review.case_id] = review
    return reviews


def _human_status(review: Review | None, fingerprint: str, response_hash: str) -> str:
    if review is None:
        return "review_pending"
    if review.case_fingerprint != fingerprint or review.response_sha256 != response_hash:
        return "review_stale"
    if review.ton == "traegt" and review.nutzen == "traegt":
        return "accepted"
    return "needs_work"


def run_scenario(scenario: Scenario, review: Review | None = None) -> ScenarioResult:
    conn = _fresh_conn()
    try:
        for relation in scenario.relations:
            reactors.observe_relation(
                conn, relation.subject, relation.predicate, relation.object, relation.source,
            )
        baseline = conn.execute("SELECT COALESCE(MAX(id), 0) AS id FROM event_log").fetchone()["id"]
        turns: list[TurnResult] = []
        for index, turn in enumerate(scenario.turns):
            captured: list[tuple[antwort.AnswerDraft, antwort.DialogueFrame]] = []

            def renderer(
                draft: antwort.AnswerDraft,
                frame: antwort.DialogueFrame,
            ) -> antwort.AnswerText:
                captured.append((draft, frame))
                return antwort.rendere(draft, frame)

            fixed_readings = turn.readings

            def deuter(_question: str):
                if fixed_readings is None:
                    return None
                return [dict(reading) for reading in fixed_readings]

            previous = turns[-1] if turns else None
            history = [
                {"question": result.anchor, "answer": result.text}
                for result in turns
            ]
            raw_result = companion.respond_with_deuter(
                conn,
                turn.question,
                last_question=previous.anchor if previous else None,
                last_answer=previous.text if previous else None,
                verlauf=history,
                letzte_lesarten=list(previous.readings) if previous else None,
                letzter_anschluss=previous.followup if previous else None,
                deuter=deuter,
                renderer=renderer,
                previous_response_id=index if index else None,
            )
            turns.append(_normalise_result(turn.question, raw_result, captured))

        turn_results = tuple(turns)
        gates = [_evaluate_gate(gate, turn_results) for gate in scenario.gates]
        payloads = [
            row["payload"]
            for row in conn.execute(
                "SELECT payload FROM event_log WHERE id > ? ORDER BY id", (baseline,),
            ).fetchall()
        ]
        leaked = tuple(
            turn.question
            for turn in scenario.turns
            if any(turn.question in payload for payload in payloads)
        )
        gates.append(GateResult(
            dimension="datenschutz",
            kind="ledger_without_dialogue_text",
            description="Kein synthetischer Dialogrohtext gelangt ins Ledger.",
            expected=(),
            actual=leaked,
            passed=not leaked,
            turn=-1,
        ))
        fingerprint = scenario_fingerprint(scenario)
        response_hash = _sha256([result.text for result in turn_results])
        status = _human_status(review, fingerprint, response_hash)
        return ScenarioResult(
            id=scenario.id,
            title=scenario.title,
            purpose=scenario.purpose,
            turns=turn_results,
            gates=tuple(gates),
            hard_ok=all(gate.passed for gate in gates),
            case_fingerprint=fingerprint,
            response_sha256=response_hash,
            human_status=status,
            human_prompt=scenario.human_prompt,
            review=review,
        )
    finally:
        conn.close()


def run_suite(
    cases: tuple[Scenario, ...] = ALLTAGSFAELLE,
    reviews: dict[str, Review] | None = None,
) -> SuiteResult:
    validate_suite(cases)
    effective_reviews = load_reviews() if reviews is None else reviews
    unknown = set(effective_reviews) - {case.id for case in cases}
    if unknown:
        raise ValueError("Freigaben fuer unbekannte Faelle: " + ", ".join(sorted(unknown)))
    results = tuple(
        run_scenario(case, effective_reviews.get(case.id))
        for case in sorted(cases, key=lambda item: item.id)
    )
    dimensions: dict[str, dict[str, int]] = {}
    for dimension in DIMENSION_LABELS:
        selected = [gate for case in results for gate in case.gates if gate.dimension == dimension]
        dimensions[dimension] = {
            "passed": sum(gate.passed for gate in selected),
            "failed": sum(not gate.passed for gate in selected),
            "total": len(selected),
        }
    human_statuses = {
        status: sum(case.human_status == status for case in results)
        for status in ("accepted", "needs_work", "review_stale", "review_pending")
    }
    digest_material = [
        {
            "id": case.id,
            "response": case.response_sha256,
            "gates": [(gate.dimension, gate.kind, gate.passed) for gate in case.gates],
            "human_status": case.human_status,
        }
        for case in results
    ]
    return SuiteResult(
        schema=SCHEMA,
        suite_version=SUITE_VERSION,
        cases=results,
        dimensions=dimensions,
        hard_ok=all(case.hard_ok for case in results),
        human_statuses=human_statuses,
        content_sha256=_sha256(digest_material),
    )


def report_dict(report: SuiteResult) -> dict[str, object]:
    return asdict(report)


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def render_markdown(report: SuiteResult) -> str:
    gate_total = sum(value["total"] for value in report.dimensions.values())
    gate_passed = sum(value["passed"] for value in report.dimensions.values())
    lines = [
        "# GENUS Alltagsprobe · Antwortqualität v1",
        "",
        "> **Status:** generierte, hermetische Abnahmefläche · menschliche Wertung bleibt bindend",
        ">",
        f"> **Suite:** `{report.suite_version}` · **Inhalt:** `{report.content_sha256[:16]}`",
        ">",
        "> **Datengrenze:** ausschließlich synthetische In-Memory-Fälle; kein Pi-Ledger, kein Chat-Export, kein Modell als Richter",
        "",
        "## Ergebnis zuerst",
        "",
        f"Die harten Verträge stehen bei **{gate_passed}/{gate_total}**. "
        f"Menschlich akzeptiert sind **{report.human_statuses['accepted']}/{len(report.cases)}** Fälle; "
        f"**{report.human_statuses['review_pending']}** warten auf die erste Bewertung und "
        f"**{report.human_statuses['review_stale']}** sind nach einer Änderung veraltet.",
        "",
        "Das ist bewusst **keine Gesamtnote**. Grün beweist Treue, Ehrlichkeit, Richtung, "
        "Anschluss und Datensparsamkeit. Ob eine Antwort nativ, tief und nützlich wirkt, "
        "entscheidet Ronny an genau dem hier gezeigten Wortlaut.",
        "",
        "## Harte Dimensionen",
        "",
        "| Dimension | bestanden | fehlgeschlagen | Verträge |",
        "|---|---:|---:|---:|",
    ]
    for key, values in report.dimensions.items():
        lines.append(
            f"| {DIMENSION_LABELS[key]} | {values['passed']} | {values['failed']} | {values['total']} |"
        )
    lines.extend([
        "",
        "## Fallübersicht",
        "",
        "| Fall | harte Verträge | menschlich | Antwort-Hash |",
        "|---|---:|---|---|",
    ])
    for case in report.cases:
        passed = sum(gate.passed for gate in case.gates)
        lines.append(
            f"| `{case.id}` · {_md(case.title)} | {passed}/{len(case.gates)} | "
            f"`{case.human_status}` | `{case.response_sha256[:12]}` |"
        )
    lines.extend([
        "",
        "## So wird menschlich abgenommen",
        "",
        "Für jeden Fall werden **Ton** und **Nutzen** getrennt als `traegt`, `holprig` oder "
        "`unbrauchbar` bewertet. Die Freigabe in `docs/reviews/ALLTAGSPROBE_V1.json` traegt "
        "Fall- und Antwort-Hash. Ändert sich Fixture oder Wortlaut, wird sie automatisch "
        "`review_stale`; alte Zustimmung kann also keine neue Antwort absegnen.",
        "",
        "## Die Fälle",
        "",
    ])
    for case in report.cases:
        lines.extend([
            f"### {case.id} · {case.title}",
            "",
            case.purpose,
            "",
        ])
        for index, turn in enumerate(case.turns, 1):
            lines.extend([
                f"**Zug {index} · Frage**",
                "",
                f"> {_md(turn.question)}",
                "",
                f"**Zug {index} · GENUS**",
                "",
                "```text",
                turn.text,
                "```",
                "",
                f"Struktur: `outcome={turn.outcome}` · `readings={list(turn.readings)}` · "
                f"`anchor={turn.anchor}`",
                "",
            ])
            if turn.normalized_fields:
                lines.extend([
                    "Hinweis: Dieser Legacy-Zweig lieferte "
                    + ", ".join(f"`{field}`" for field in turn.normalized_fields)
                    + " noch nicht explizit; die Probe normalisiert ihn sichtbar.",
                    "",
                ])
        lines.extend([
            "**Automatische Verträge**",
            "",
        ])
        for gate in case.gates:
            symbol = "✅" if gate.passed else "❌"
            lines.append(f"- {symbol} **{DIMENSION_LABELS[gate.dimension]}:** {gate.description}")
        lines.extend([
            "",
            f"**Menschliche Prüffrage:** {case.human_prompt}",
            "",
            f"Status: `{case.human_status}` · Fall `{case.case_fingerprint[:12]}` · "
            f"Antwort `{case.response_sha256[:12]}`",
            "",
            "<details>",
            "<summary>Bewertungsvorlage mit vollständigen Hashes</summary>",
            "",
            "```json",
            json.dumps({
                "case_id": case.id,
                "case_fingerprint": case.case_fingerprint,
                "response_sha256": case.response_sha256,
                "ton": "traegt",
                "nutzen": "traegt",
                "reviewer": "ronny",
                "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
                "note": "",
            }, ensure_ascii=False, indent=2),
            "```",
            "",
            "</details>",
            "",
        ])
        if case.review is not None:
            lines.extend([
                f"Wertung von `{case.review.reviewer}`: Ton `{case.review.ton}`, "
                f"Nutzen `{case.review.nutzen}`. {_md(case.review.note)}",
                "",
            ])
    lines.extend([
        "---",
        "",
        "- Erzeugen: `genus alltagsprobe --markdown`",
        "- Automatisches Gate: `genus alltagsprobe --contracts-only`",
        "- Lesbare Einzelansicht: `genus alltagsprobe --details`",
        "",
    ])
    return "\n".join(lines)


def write_markdown_report(report: SuiteResult, path: str | Path) -> Path:
    """Schreibt den deterministischen Reviewbericht; der Aufrufer wählt das Ziel explizit."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return target
