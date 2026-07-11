"""Die Waage (deploy/waage.py): das Modell wiegt, es schreibt nicht. Die Tests prüfen die
LOGIK deterministisch mit einem Fake-Modell (kontrollierte Logprobs); ob die Waage GUT wiegt,
ist eine Modell-Frage und wird live am Pi gemessen (Blind-Proben, Scheibe 2)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import waage  # noqa: E402


class _FakeModel:
    """Gibt für ``kontext + kandidat`` einen kontrollierten mittleren Logprob zurück -- ein
    Kandidaten-Token an der Kontext-Grenze mit dem Punktwert aus ``punkte``."""

    def __init__(self, kontext, punkte):
        self.kontext = kontext
        self.punkte = punkte

    def create_completion(self, prompt, **kw):
        kandidat = prompt[len(self.kontext):]
        s = self.punkte[kandidat]
        return {"choices": [{"logprobs": {
            "token_logprobs": [None, s],           # Kontext-Token (None) + ein Kandidaten-Token
            "text_offset": [0, len(self.kontext)],
        }}]}


def test_waehle_nimmt_den_schwersten_kandidaten():
    ktx = "Ich habe zwei "
    m = _FakeModel(ktx, {"Hund": -3.0, "Hunde": -0.5})
    r = waage.waehle(ktx, ["Hund", "Hunde"], model=m)
    assert r["kandidat"] == "Hunde"                 # Plural passt zu „zwei"
    assert r["margin"] == 2.5                        # -0.5 - (-3.0)
    assert r["gewichte"] == {"Hund": -3.0, "Hunde": -0.5}


def test_kleiner_margin_ist_ehrliche_unsicherheit():
    ktx = "Das ist "
    m = _FakeModel(ktx, {"schön": -1.10, "schoen": -1.02})
    r = waage.waehle(ktx, ["schön", "schoen"], model=m)
    assert r["kandidat"] == "schoen"
    assert abs(r["margin"] - 0.08) < 1e-9            # knapp -> unsicher


def test_wiege_gibt_rohe_gewichte_ohne_zu_waehlen():
    ktx = "x "
    m = _FakeModel(ktx, {"a": -2.0, "b": -1.0, "c": -5.0})
    assert waage.wiege(ktx, ["a", "b", "c"], model=m) == [-2.0, -1.0, -5.0]


def test_pro_token_normalisierung_straft_laenge_nicht():
    # zwei Kandidaten-Token, aber gemittelt -> vergleichbar mit einem Ein-Token-Kandidaten
    ktx = "Kontext "
    class M:
        def create_completion(self, prompt, **kw):
            kand = prompt[len(ktx):]
            if kand == "kurz":
                tl, off = [None, -1.0], [0, len(ktx)]
            else:  # "sehrlang" -> zwei Token, gleiche mittlere Güte
                tl, off = [None, -1.0, -1.0], [0, len(ktx), len(ktx) + 4]
            return {"choices": [{"logprobs": {"token_logprobs": tl, "text_offset": off}}]}
    r = waage.wiege(ktx, ["kurz", "sehrlang"], model=M())
    assert r == [-1.0, -1.0]                          # Mittel pro Token, nicht Summe


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
    ktx = "abc"
    class M:  # liefert keine Kandidaten-Token jenseits der Grenze
        def create_completion(self, prompt, **kw):
            return {"choices": [{"logprobs": {"token_logprobs": [None], "text_offset": [0]}}]}
    assert waage.wiege(ktx, [""], model=M()) is None
