"""Der Druck — die Richtung der Lebendigkeit, erster Schritt: Persistenz statt Entladung
(Ronny 2026-07-05, docs/GENUS_INTELLIGENZ.md §9). Der Druck einer ungestillten Lücke bleibt,
solange die Not besteht, und STEIGT, wenn nach dem Aussprechen weitere Nachfrage kommt —
statt sich beim Aussprechen (dem Proposal) zu entladen. Read-time, keine Handlung."""
from genus import companion, druck, experience, inquiries, verstehen


def _heisse_luecke(conn, kind="meinung", n=4):
    verstehen.seed_raster(conn)
    for _ in range(n):
        verstehen.record_reading(conn, kind, "model:deuter")


def test_ungestillte_luecke_drueckt_mit_ihrer_nachfrage(conn):
    _heisse_luecke(conn, "meinung", 3)
    d = druck.draengendste(conn)
    assert d["was"] == "meinung" and d["nachfrage"] == 3
    assert d["ausgesprochen"] is False and d["zuwachs"] is None


def test_der_druck_persistiert_nach_dem_aussprechen_und_steigt(conn):
    # DER KERN: aussprechen entlädt den Druck NICHT -- weitere Nachfrage lässt ihn steigen
    _heisse_luecke(conn, "meinung", 4)
    experience.spontane_regung(conn)             # ausgesprochen bei Nachfrage 4
    for _ in range(3):                           # danach 3 weitere Lesungen
        verstehen.record_reading(conn, "meinung", "model:deuter")
    d = druck.draengendste(conn)
    assert d["was"] == "meinung"
    assert d["nachfrage"] == 7                    # der Druck ist NICHT verschwunden
    assert d["ausgesprochen"] is True and d["ausgesprochen_bei"] == 4
    assert d["zuwachs"] == 3                      # er ist seither GEWACHSEN (Persistenz-Signal)


def test_eine_gestillte_luecke_drueckt_gar_nicht_mehr(conn):
    # „definition" hat einen Handler -> Not gestillt -> kein Druck, egal wie oft gelesen
    verstehen.seed_raster(conn)
    for _ in range(9):
        verstehen.record_reading(conn, "definition", "model:deuter")
    assert all(d["was"] != "definition" for d in druck.luecken_druck(conn))


def test_der_druck_konkurriert_die_draengendste_zuerst(conn):
    verstehen.seed_raster(conn)
    for _ in range(6):
        verstehen.record_reading(conn, "meinung", "model:deuter")
    for _ in range(2):
        verstehen.record_reading(conn, "tun", "model:deuter")
    rang = [d["was"] for d in druck.luecken_druck(conn)]
    assert rang[0] == "meinung"                # 6 drückt stärker als 2
    assert "tun" in rang


def test_ohne_gelebte_nachfrage_kein_druck(conn):
    verstehen.seed_raster(conn)
    assert druck.luecken_druck(conn) == [] and druck.satz(conn) == ""


def test_druck_satz_benennt_das_persistenz_signal_nativ(conn):
    _heisse_luecke(conn, "meinung", 4)
    experience.spontane_regung(conn)
    for _ in range(3):
        verstehen.record_reading(conn, "meinung", "model:deuter")
    s = druck.satz(conn)
    assert "meinung" in s and "gestiegen" in s and "3" in s


def test_druck_erzeugt_keine_events_bewegt_den_geist_nie_die_hand(conn):
    _heisse_luecke(conn, "meinung", 4)
    vorher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    druck.luecken_druck(conn)
    druck.draengendste(conn)
    druck.satz(conn)
    nachher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    assert nachher == vorher                      # read-time: kein Event, keine Handlung


def test_der_druck_taucht_in_was_beschaeftigt_dich_auf(conn):
    _heisse_luecke(conn, "meinung", 5)
    text = companion.narrate_inquiries(conn, companion.open_questions(conn))
    assert "meinung" in text and "dringendsten" in text


# --- Quelle 2: offene Inquiries, nach Wiederkehr ----------------------------------------

def test_frage_druck_misst_die_wiederkehr(conn):
    for i in (1, 2, 3):   # dieselbe Überraschung 3x -> count 3
        inquiries.record_inquiry_created_event(
            conn, inquiry_id=i, inquiry_type="StabilityInquiry", claim_key="weather.trend",
            source_belief=None, source_event=1, question_key="stability.unexpected_flip",
            payload={"expected": "stable", "observed": "flipped"})
    inquiries.record_inquiry_created_event(
        conn, inquiry_id=9, inquiry_type="StabilityInquiry", claim_key="disk.trend",
        source_belief=None, source_event=1, question_key="stability.unexpected_flip",
        payload={"expected": "stable", "observed": "flipped"})
    d = druck.frage_druck(conn)
    assert d[0] == {"quelle": "frage", "was": "weather.trend", "staerke": 3,
                    "inquiry_type": "StabilityInquiry"}
    assert d[1]["was"] == "disk.trend" and d[1]["staerke"] == 1   # weniger Wiederkehr -> weniger Druck


def test_offene_fragen_werden_nach_druck_geordnet_erzaehlt(conn):
    for i in (1, 2):
        inquiries.record_inquiry_created_event(
            conn, inquiry_id=i, inquiry_type="StabilityInquiry", claim_key="weather.trend",
            source_belief=None, source_event=1, question_key="s",
            payload={"expected": "stable", "observed": "flipped"})
    inquiries.record_inquiry_created_event(
        conn, inquiry_id=3, inquiry_type="StabilityInquiry", claim_key="disk.trend",
        source_belief=None, source_event=1, question_key="s",
        payload={"expected": "stable", "observed": "flipped"})
    text = companion.narrate_inquiries(conn, companion.open_questions(conn))
    assert text.index("weather.trend") < text.index("disk.trend")   # 2-mal vor 1-mal


# --- Quelle 3: fehlende Operationen, nach Fan-in ----------------------------------------

def test_operations_druck_misst_den_fan_in(conn):
    from genus import ziele
    ziele.seed_ziele(conn)
    d = druck.operations_druck(conn)
    ids = [x["was"] for x in d]
    # generator-organ wird von mehreren Zielen gebraucht -> höchster Fan-in -> vorn
    assert d[0]["was"] == "generator-organ" and d[0]["staerke"] >= 3
    assert all(x["quelle"] == "operation" and x["staerke"] >= 1 for x in d)
    assert "abstrahieren" in ids   # eine Operations-Lücke aus der Intelligenz-Betrachtung


def test_eine_live_faehigkeit_drueckt_nicht(conn):
    from genus import ziele
    ziele.seed_ziele(conn)
    assert all(x["was"] != "vorschlags-loop" for x in druck.operations_druck(conn))  # status live


# --- die Landschaft: alle drei Quellen, jede in ihren eigenen Zähler ----------------------

def test_die_landschaft_traegt_alle_registrierten_quellen(conn):
    assert set(druck.landschaft(conn)) == {name for name, _ in druck.DRUCK_QUELLEN}
    assert set(druck.landschaft(conn)) == {"luecke", "frage", "operation"}


def test_satz_nennt_luecke_und_fehlende_faehigkeit(conn):
    from genus import ziele
    _heisse_luecke(conn, "meinung", 4)
    ziele.seed_ziele(conn)
    s = druck.satz(conn)
    assert "meinung" in s and "Fähigkeit" in s and "blockiert" in s
