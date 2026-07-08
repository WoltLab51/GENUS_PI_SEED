"""Der erste SINN (P4, Ronny 2026-07-08): die Zelle „weltfrage" spricht den wahrgenommenen
Wetter-Bericht aus, den die Membran stuendlich hereinreicht. Rein lesend, gläsern, ehrliche
Teil-Antwort (jedes reiche Feld nur bei echtem Material; sonst geschwiegen, nie erfunden)."""
from genus import companion, reactors, sensor


def _saee_wetter(conn, temp, quelle="open-meteo"):
    reactors.observe_weather_reading(conn, sensor.weather_reading(temp, quelle))


def _saee_feld(conn, claim_key, wert, quelle="open-meteo"):
    reactors.observe_assertion(conn, claim_key, wert, quelle)


def test_weltfrage_spricht_die_wahrgenommene_temperatur(conn):
    _saee_wetter(conn, 17.4)                        # frisch gemessen -> „Gerade draussen"
    text = companion._zelle_weltfrage(conn, {}, "Wie warm ist es draussen?", None, None)
    assert "Gerade draussen" in text and "17,4 °C" in text
    assert "open-meteo" in text                      # die Quelle ist jetzt nennbar (Label-Fix)
    # nur Temperatur da -> ehrlich benannt, was noch fehlt
    assert "Vorhersage" in text and "Regen" in text


def test_weltfrage_komponiert_den_reichen_bericht(conn):
    # alles, was die Quelle hergibt: Zustand (WMO-Code), gefuehlt, Feuchte, Wind, Vorhersage, Regen
    _saee_wetter(conn, 18.0)
    _saee_feld(conn, "weather.code", 61)             # 61 = leichter Regen
    _saee_feld(conn, "weather.apparent", 16.0)
    _saee_feld(conn, "weather.humidity", 72)
    _saee_feld(conn, "weather.wind", 14)
    _saee_feld(conn, "weather.temp_max", 21.0)
    _saee_feld(conn, "weather.temp_min", 13.0)
    _saee_feld(conn, "weather.rain_prob", 80)
    text = companion._zelle_weltfrage(conn, {}, "Wie ist das Wetter?", None, None)
    assert "leichter Regen bei 18,0 °C" in text      # Zustand aus dem WMO-Code
    assert "gefuehlt 16,0 °C" in text
    assert "Luftfeuchte 72 %" in text and "Wind 14 km/h" in text
    assert "Heute 13,0 °C bis 21,0 °C" in text
    assert "Regenwahrscheinlichkeit 80 %" in text
    assert "von open-meteo" in text
    # mit Vorhersage ist die Rest-Luecke „andere Orte / weiter als heute", nicht „Vorhersage"
    assert "weiter als heute" in text


def test_weltfrage_verschweigt_fehlende_felder_statt_zu_erfinden(conn):
    # nur Temperatur + Zustand da; kein Wind/Feuchte/Vorhersage -> die fehlen im Satz, kein Platzhalter
    _saee_wetter(conn, 9.0)
    _saee_feld(conn, "weather.code", 0)              # 0 = klar
    text = companion._zelle_weltfrage(conn, {}, "Wetter?", None, None)
    assert "klar bei 9,0 °C" in text
    assert "Luftfeuchte" not in text and "Wind" not in text and "Heute" not in text


def test_weltfrage_sagt_nie_gerade_zu_einem_alten_wert(conn):
    # Review-Fund: sources.resolve.live misst Frische nur ZWISCHEN Quellen -> bei EINER Quelle
    # immer „live". Ein alter Wert darf NIE als frisch ausgegeben werden -> Wanduhr-Alter.
    _saee_wetter(conn, 15.5)
    _saee_feld(conn, "weather.humidity", 99)         # ein reiches Feld -> darf NICHT als aktuell erscheinen
    conn.execute("UPDATE value_projection SET created_at = ? ",
                 ("2026-07-01T00:00:00.000Z",))
    text = companion._zelle_weltfrage(conn, {}, "Wie warm ist es?", None, None)
    assert "Gerade draussen" not in text            # NICHT als aktuell ausgegeben
    assert "15,5 °C" in text and "frischer habe ich gerade nichts" in text
    assert "Luftfeuchte" not in text                 # altes Detailfeld wird nicht als aktuell gesprochen


def test_weltfrage_verschweigt_ein_altes_reiches_feld(conn):
    # Review-Fund: jedes Feld traegt seine EIGENE Frische. Temp frisch, aber die Vorhersage vom
    # letzten Fetch ausgelassen (alt) -> die alte Vorhersage darf NICHT als heute erscheinen.
    _saee_wetter(conn, 18.0)                          # Temp frisch
    _saee_feld(conn, "weather.temp_max", 21.0)
    _saee_feld(conn, "weather.temp_min", 13.0)
    conn.execute("UPDATE value_projection SET created_at = ? WHERE claim_key LIKE 'weather.temp_m%'",
                 ("2026-07-01T00:00:00.000Z",))
    text = companion._zelle_weltfrage(conn, {}, "Wetter?", None, None)
    assert "Gerade draussen" in text and "18,0 °C" in text   # Temp frisch -> reicher Pfad
    assert "Heute" not in text and "21,0 °C" not in text       # alte Vorhersage wird verschwiegen


def test_weltfrage_crasht_nicht_bei_kaputtem_code(conn):
    # Review-Fund: ein weather.code als inf/nan darf die Antwort nicht zum Absturz bringen
    # (float() liesse es durch, int() kaeme) -> das Feld wird ehrlich verschwiegen, kein Crash.
    _saee_wetter(conn, 10.0)
    reactors.observe_assertion(conn, "weather.code", float("inf"), "open-meteo")
    text = companion._zelle_weltfrage(conn, {}, "Wetter?", None, None)
    assert "10,0 °C" in text                          # Antwort steht, kein Absturz


def test_weltfrage_ist_ehrlich_ohne_messwert(conn):
    text = companion._zelle_weltfrage(conn, {}, "Wie ist das Wetter?", None, None)
    assert "°C" not in text
    assert "erreicht die Welt im Moment nicht" in text


def test_weltfrage_hat_jetzt_einen_handler(conn):
    # sobald der Lese-Draht da ist, ist weltfrage keine Verstehens-Luecke mehr (hat_handler True)
    assert companion.hat_handler(conn, "weltfrage")


def test_weltfrage_liest_nur_und_schreibt_nicht(conn):
    # der Sinn ist rein lesend: ein Aufruf veraendert das Ledger nicht (Sinne lesen, Haende wirken)
    _saee_wetter(conn, 12.0)
    _saee_feld(conn, "weather.code", 3)
    vorher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    companion._zelle_weltfrage(conn, {}, "wetter?", None, None)
    nachher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    assert nachher == vorher


def test_weltfrage_bevorzugt_die_frischere_quelle_bei_zwei(conn):
    # zwei unabhaengige Quellen fuer denselben Claim: sources.resolve waehlt read-time nach
    # Vertrauen x Frische -- der Handler spricht den gewaehlten Wert, keine Erfindung dazwischen
    reactors.observe_assertion(conn, "weather.temp_outside", 9.0, "wttr.in")
    _saee_wetter(conn, 9.2, "open-meteo")
    text = companion._zelle_weltfrage(conn, {}, "Wie kalt ist es?", None, None)
    assert "9,0 °C" in text or "9,2 °C" in text
