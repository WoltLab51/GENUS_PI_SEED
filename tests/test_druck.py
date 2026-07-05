"""Der Druck — die Richtung der Lebendigkeit, erster Schritt: Persistenz statt Entladung
(Ronny 2026-07-05, docs/GENUS_INTELLIGENZ.md §9). Der Druck einer ungestillten Lücke bleibt,
solange die Not besteht, und STEIGT, wenn nach dem Aussprechen weitere Nachfrage kommt —
statt sich beim Aussprechen (dem Proposal) zu entladen. Read-time, keine Handlung."""
from genus import companion, druck, experience, inquiries, verstehen


def _heisse_luecke(conn, kind="weltfrage", n=4):
    verstehen.seed_raster(conn)
    for _ in range(n):
        verstehen.record_reading(conn, kind, "model:deuter")


def test_ungestillte_luecke_drueckt_mit_ihrer_nachfrage(conn):
    _heisse_luecke(conn, "weltfrage", 3)
    d = druck.draengendste(conn)
    assert d["kind"] == "weltfrage" and d["nachfrage"] == 3
    assert d["ausgesprochen"] is False and d["zuwachs"] is None


def test_der_druck_persistiert_nach_dem_aussprechen_und_steigt(conn):
    # DER KERN: aussprechen entlädt den Druck NICHT -- weitere Nachfrage lässt ihn steigen
    _heisse_luecke(conn, "weltfrage", 4)
    experience.spontane_regung(conn)             # ausgesprochen bei Nachfrage 4
    for _ in range(3):                           # danach 3 weitere Lesungen
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    d = druck.draengendste(conn)
    assert d["kind"] == "weltfrage"
    assert d["nachfrage"] == 7                    # der Druck ist NICHT verschwunden
    assert d["ausgesprochen"] is True and d["ausgesprochen_bei"] == 4
    assert d["zuwachs"] == 3                      # er ist seither GEWACHSEN (Persistenz-Signal)


def test_eine_gestillte_luecke_drueckt_gar_nicht_mehr(conn):
    # „definition" hat einen Handler -> Not gestillt -> kein Druck, egal wie oft gelesen
    verstehen.seed_raster(conn)
    for _ in range(9):
        verstehen.record_reading(conn, "definition", "model:deuter")
    assert all(d["kind"] != "definition" for d in druck.luecken_druck(conn))


def test_der_druck_konkurriert_die_draengendste_zuerst(conn):
    verstehen.seed_raster(conn)
    for _ in range(6):
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    for _ in range(2):
        verstehen.record_reading(conn, "tun", "model:deuter")
    rang = [d["kind"] for d in druck.luecken_druck(conn)]
    assert rang[0] == "weltfrage"                # 6 drückt stärker als 2
    assert "tun" in rang


def test_ohne_gelebte_nachfrage_kein_druck(conn):
    verstehen.seed_raster(conn)
    assert druck.luecken_druck(conn) == [] and druck.satz(conn) == ""


def test_druck_satz_benennt_das_persistenz_signal_nativ(conn):
    _heisse_luecke(conn, "weltfrage", 4)
    experience.spontane_regung(conn)
    for _ in range(3):
        verstehen.record_reading(conn, "weltfrage", "model:deuter")
    s = druck.satz(conn)
    assert "weltfrage" in s and "gestiegen" in s and "3" in s


def test_druck_erzeugt_keine_events_bewegt_den_geist_nie_die_hand(conn):
    _heisse_luecke(conn, "weltfrage", 4)
    vorher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    druck.luecken_druck(conn)
    druck.draengendste(conn)
    druck.satz(conn)
    nachher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    assert nachher == vorher                      # read-time: kein Event, keine Handlung


def test_der_druck_taucht_in_was_beschaeftigt_dich_auf(conn):
    _heisse_luecke(conn, "weltfrage", 5)
    text = companion.narrate_inquiries(conn, companion.open_questions(conn))
    assert "weltfrage" in text and "dringendsten" in text
