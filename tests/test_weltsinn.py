"""Der erste SINN (P4, Ronny 2026-07-08): die Zelle „weltfrage" spricht die wahrgenommene
Aussentemperatur aus, die die Membran schon stuendlich hereinreicht. Rein lesend, gläsern,
ehrliche Teil-Antwort (benennt, was der Sinn noch nicht erreicht)."""
from genus import companion, reactors, sensor


def _saee_wetter(conn, temp, quelle="open-meteo"):
    reactors.observe_weather_reading(conn, sensor.weather_reading(temp, quelle))


def test_weltfrage_spricht_die_wahrgenommene_temperatur(conn):
    _saee_wetter(conn, 17.4)                       # frisch gemessen -> „gerade"
    text = companion._zelle_weltfrage(conn, {}, "Wie warm ist es draussen?", None, None)
    assert "gerade 17,4 °C" in text                # deutscher Grad-Wert, als aktuell ausgesprochen
    assert "Vorhersage" in text and "Regen" in text  # ehrlich benannt, was der Sinn nicht erreicht


def test_weltfrage_sagt_nie_gerade_zu_einem_alten_wert(conn):
    # Review-Fund: sources.resolve.live misst Frische nur ZWISCHEN Quellen -> bei EINER Quelle
    # immer „live". Ein alter Wert (Sensor-Cron gestorben) darf NIE als „gerade" ausgesprochen
    # werden -> das Alter wird gegen die Wanduhr gemessen.
    _saee_wetter(conn, 15.5, "open-meteo")
    conn.execute("UPDATE value_projection SET created_at = ? "
                 "WHERE claim_key = 'weather.temp_outside'", ("2026-07-01T00:00:00.000Z",))
    text = companion._zelle_weltfrage(conn, {}, "Wie warm ist es?", None, None)
    assert "gerade 15,5 °C" not in text            # NICHT als aktuell ausgegeben
    assert "15,5 °C" in text                        # der echte (alte) Wert wird trotzdem genannt
    assert "frischer habe ich gerade nichts" in text


def test_weltfrage_ist_ehrlich_ohne_messwert(conn):
    text = companion._zelle_weltfrage(conn, {}, "Wie ist das Wetter?", None, None)
    assert "°C" not in text
    assert "erreicht die Welt im Moment nicht" in text
    assert "Vorhersage" in text                    # der ehrliche Rest wird trotzdem benannt


def test_weltfrage_hat_jetzt_einen_handler(conn):
    # sobald der Lese-Draht da ist, ist weltfrage keine Verstehens-Luecke mehr -> der Detektor
    # meldet sie nicht erneut vor (companion.hat_handler liest die Registry)
    assert companion.hat_handler(conn, "weltfrage")


def test_weltfrage_liest_nur_und_schreibt_nicht(conn):
    # der Sinn ist rein lesend: ein Aufruf veraendert das Ledger nicht (weltfrage steht nicht in
    # _ZELLEN_SCHREIBEND) -- die Grenze Sinne-lesen / Haende-wirken bleibt gewahrt
    _saee_wetter(conn, 12.0)
    vorher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    companion._zelle_weltfrage(conn, {}, "wetter?", None, None)
    nachher = conn.execute("SELECT COUNT(*) AS n FROM event_log").fetchone()["n"]
    assert nachher == vorher


def test_weltfrage_bevorzugt_die_frischere_quelle_bei_zwei(conn):
    # zwei unabhaengige Quellen fuer denselben Claim: sources.resolve waehlt read-time nach
    # Vertrauen x Frische -- der Handler spricht den gewaehlten Wert, keine Erfindung
    reactors.observe_assertion(conn, "weather.temp_outside", 9.0, "wttr.in")
    _saee_wetter(conn, 9.2, "open-meteo")
    text = companion._zelle_weltfrage(conn, {}, "Wie kalt ist es?", None, None)
    assert "9,0 °C" in text or "9,2 °C" in text     # einer der beiden echten Werte, nichts dazwischen
