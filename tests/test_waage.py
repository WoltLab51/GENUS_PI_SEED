"""Die Waage (deploy/waage.py): das Modell wiegt, es schreibt nicht. Die Tests prüfen die
LOGIK deterministisch mit einem Fake-Modell, das den SCHNELLEN low-level-Weg nachstellt
(tokenize/reset/eval + gelesene Logits über die Naht ``_lies_logits``) und kontrollierte Logits
liefert -- so, dass der Log-Softmax des Kandidaten-Tokens genau den Zielwert ergibt. Ob die
Waage GUT wiegt, ist eine Modell-Frage und wird live am Pi gemessen (Blind-Proben, Scheibe 2)."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import waage  # noqa: E402


@pytest.fixture(autouse=True)
def _naht_auf_fake(monkeypatch):
    """``_lies_logits`` liest sonst roh aus llama.cpp -- im Test delegiert die Naht an das
    Fake-Modell, das die kontrollierte Logit-Zeile seiner aktuellen Kandidaten kennt."""
    monkeypatch.setattr(waage, "_lies_logits", lambda model: model.letzte_logits())


class _FakeModel:
    """``kontext`` -> ein BOS-Token, jeder Kandidat -> seine vorgegebenen Token-IDs.
    ``letzte_logits`` baut für den ZULETZT tokenisierten Kandidaten eine Logit-Zeile, deren
    Log-Softmax an jeder Kandidaten-ID exakt den Ziel-Logprob trifft (Füll-Token 0 trägt die
    Restmasse, damit logsumexp der Zeile 0 ist -> Log-Softmax == roher Logit)."""

    def __init__(self, cand_tokens, cand_L):
        self.cand_tokens = cand_tokens          # {kandidat: [token_id, ...]}
        self.cand_L = cand_L                    # {token_id: ziel_logprob}  (jeweils < 0)
        self.vocab = max(cand_L) + 5
        self._cur = None

    def tokenize(self, b, add_bos=True, special=True):
        s = b.decode("utf-8")
        treffer = None
        for k in self.cand_tokens:              # längster passender Suffix = der Kandidat
            if k and s.endswith(k) and (treffer is None or len(k) > len(treffer)):
                treffer = k
        if treffer is None:
            return [1]                          # reiner Kontext (BOS)
        self._cur = treffer
        return [1] + list(self.cand_tokens[treffer])

    def reset(self):
        pass

    def eval(self, toks):
        pass

    def letzte_logits(self):
        ids = self.cand_tokens[self._cur]
        zeile = [-60.0] * self.vocab
        for i in ids:
            zeile[i] = self.cand_L[i]
        rest = 1.0 - sum(math.exp(self.cand_L[i]) for i in ids)
        zeile[0] = math.log(rest)               # Füll-Token: logsumexp(zeile) == 0
        return zeile


def _ein_token(punkte, start=10):
    """Baut ein FakeModel, in dem jeder Kandidat GENAU ein Token mit seinem Ziel-Logprob ist."""
    cand_tokens, cand_L = {}, {}
    for j, (k, L) in enumerate(punkte.items()):
        tid = start + j
        cand_tokens[k] = [tid]
        cand_L[tid] = L
    return _FakeModel(cand_tokens, cand_L)


def test_waehle_nimmt_den_schwersten_kandidaten():
    ktx = "Ich habe zwei "
    m = _ein_token({"Hund": -3.0, "Hunde": -0.5})
    r = waage.waehle(ktx, ["Hund", "Hunde"], model=m)
    assert r["kandidat"] == "Hunde"                 # Plural passt zu „zwei"
    assert r["margin"] == 2.5                         # -0.5 - (-3.0)
    assert r["gewichte"] == {"Hund": -3.0, "Hunde": -0.5}


def test_kleiner_margin_ist_ehrliche_unsicherheit():
    ktx = "Das ist "
    m = _ein_token({"schoen": -1.10, "schlecht": -1.02})
    r = waage.waehle(ktx, ["schoen", "schlecht"], model=m)
    assert r["kandidat"] == "schlecht"
    assert abs(r["margin"] - 0.08) < 1e-6            # knapp -> unsicher


def test_wiege_gibt_rohe_gewichte_ohne_zu_waehlen():
    ktx = "x "
    m = _ein_token({"a": -2.0, "b": -1.0, "c": -5.0})
    werte = waage.wiege(ktx, ["a", "b", "c"], model=m)
    assert [round(w, 4) for w in werte] == [-2.0, -1.0, -5.0]


def test_pro_token_normalisierung_straft_laenge_nicht():
    # "kurz" = ein Token (-1.0); "sehrlang" = zwei Token (je -1.0) -> gemittelt gleich schwer
    m = _FakeModel({"kurz": [10], "sehrlang": [11, 12]}, {10: -1.0, 11: -1.0, 12: -1.0})
    werte = waage.wiege("Kontext ", ["kurz", "sehrlang"], model=m)
    assert [round(w, 4) for w in werte] == [-1.0, -1.0]   # Mittel pro Token, nicht Summe


def test_fehlt_das_modell_faellt_es_sicher_auf_none():
    # kein Modell injiziert + Pfad existiert nicht -> None (der Aufrufer nimmt seinen Rückfall)
    alt = waage.MODEL_PATH
    waage.MODEL_PATH = "/gibt/es/nicht.gguf"
    waage._model = None
    try:
        assert waage.wiege("x ", ["a", "b"]) is None
        assert waage.waehle("x ", ["a", "b"]) is None
    finally:
        waage.MODEL_PATH = alt


def test_unabgrenzbarer_kandidat_gibt_none_statt_zu_luegen():
    # leerer Kandidat -> keine Kandidaten-Token jenseits des Kontexts -> None statt Erfindung
    m = _ein_token({"a": -1.0})
    assert waage.wiege("abc", [""], model=m) is None
