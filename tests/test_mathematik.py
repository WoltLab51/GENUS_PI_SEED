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
