"""Rechenfähigkeit (genus.mathematik): exakte Ableitungen über sympy, nie geraten. Erste
Aufgabenart des Abitur-Ziels -- GENUS soll die Aufgabe SCHAFFEN, nicht nur den Begriff kennen."""
from genus import mathematik


def test_ableitung_of_a_polynomial_is_exact():
    r = mathematik.ableitung("x^3 - 3x")
    assert r["ok"] and r["ableitung"] == "3*x**2 - 3"


def test_ableitung_of_a_simple_linear_combination():
    r = mathematik.ableitung("3x^2 + 2x")
    assert r["ok"] and r["ableitung"] == "6*x + 2"


def test_ableitung_treats_e_as_eulers_number_not_a_variable():
    # live gefunden: ohne explizite Bindung liest sympy "e" als freies Symbol -- d/dx(e^x)
    # kaeme dann als "e**x*log(e)" statt der Eulerschen Identitaet e^x == (e^x)'
    r = mathematik.ableitung("e^x")
    assert r["ok"] and r["ableitung"] == "exp(x)"


def test_ableitung_of_a_trig_function():
    r = mathematik.ableitung("sin(x)")
    assert r["ok"] and r["ableitung"] == "cos(x)"


def test_zweite_ableitung_via_ordnung():
    r = mathematik.ableitung("x^3 - 3x", ordnung=2)
    assert r["ok"] and r["ableitung"] == "6*x"


def test_ableitung_respects_a_different_variable_name():
    r = mathematik.ableitung("2t^2 + 5", variable="t")
    assert r["ok"] and r["ableitung"] == "4*t"


def test_ableitung_of_a_constant_is_zero():
    r = mathematik.ableitung("7")
    assert r["ok"] and r["ableitung"] == "0"


def test_pi_is_recognized_as_the_constant():
    r = mathematik.ableitung("pi*x^2")
    assert r["ok"] and r["ableitung"] == "2*pi*x"


def test_unreadable_gibberish_is_rejected_not_guessed():
    # live gefunden: sympys implizite Multiplikation liest klaglos jeden Buchstaben-Wirrwarr
    # als Produkt einzelner Symbole (d*a*s*i*s*t*...) -- ein plausibel aussehendes FALSCHES
    # Ergebnis. Das muss ehrlich abgelehnt werden, bevor sympy überhaupt gefragt wird.
    r = mathematik.ableitung("das ist kein term")
    assert not r["ok"] and "kein bekanntes Symbol" in r["fehler"]


def test_a_second_undeclared_variable_is_rejected_not_silently_partial():
    # x*y mit variable="x": y ist weder die erfragte Variable noch ein bekannter Name --
    # GENUS lehnt ab, statt eine partielle Ableitung zu erfinden, die niemand erfragt hat
    r = mathematik.ableitung("x*y")
    assert not r["ok"] and "y" in r["fehler"]


def test_ableitung_result_is_json_serializable():
    import json
    assert json.dumps(mathematik.ableitung("x^2")) is not None


def test_extremstellen_of_a_cubic_finds_both_and_classifies_correctly():
    r = mathematik.extremstellen("x^3 - 3x")
    assert r["ok"]
    assert r["punkte"] == [
        {"x": "-1", "y": "2", "art": "Maximum"},
        {"x": "1", "y": "-2", "art": "Minimum"},
    ]


def test_extremstellen_of_a_parabola_has_one_minimum():
    r = mathematik.extremstellen("x^2")
    assert r["ok"] and r["punkte"] == [{"x": "0", "y": "0", "art": "Minimum"}]


def test_extremstellen_honestly_admits_when_the_second_derivative_test_is_inconclusive():
    # x^3 hat bei 0 einen Sattelpunkt, x^4 ein Minimum -- in BEIDEN Fällen ist f''(0)=0, der
    # Test selbst kann nicht entscheiden. GENUS darf hier NICHT raten, welcher Fall vorliegt.
    for term in ("x^3", "x^4"):
        r = mathematik.extremstellen(term)
        assert r["ok"] and r["punkte"][0]["art"].startswith("unklar")


def test_extremstellen_of_a_function_without_any_is_an_empty_list_not_an_error():
    r = mathematik.extremstellen("7")
    assert r["ok"] and r["punkte"] == []


def test_extremstellen_rejects_unreadable_input_same_as_ableitung():
    r = mathematik.extremstellen("das ist kein term")
    assert not r["ok"] and "kein bekanntes Symbol" in r["fehler"]
