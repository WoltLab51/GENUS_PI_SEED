"""Die Besinnung — der innere Loop, dem der Druck sein Gefälle gibt (Ronny 2026-07-05,
docs/GENUS_INTELLIGENZ.md §9). Sie liest das Druck-Gefälle, tut den EINEN erlaubten
inwendigen Schritt (die drängendste unausgesprochene Lücke aussprechen, gegated) und kettet
— ein Gedanke zieht den nächsten. Bewegt den Geist, nie die Hand."""
from genus import besinnung, ziele, verstehen


def _luecken(conn, *paare):
    verstehen.seed_raster(conn)
    for kind, n in paare:
        for _ in range(n):
            verstehen.record_reading(conn, kind, "model:deuter")


def test_agenda_zeigt_die_draengendste_je_quelle_und_das_selbst_moegliche(conn):
    _luecken(conn, ("weltfrage", 4), ("tun", 2))
    ziele.seed_ziele(conn)
    a = besinnung.agenda(conn)
    assert a["luecke"]["was"] == "weltfrage"
    assert a["operation"]["was"] == "generator-organ"      # höchster Fan-in
    assert a["selbst_moeglich"]["was"] == "weltfrage"      # drängendste noch unausgesprochen


def test_besinne_spricht_die_draengendste_unausgesprochene_luecke_aus(conn):
    _luecken(conn, ("weltfrage", 4))
    s = besinnung.besinne(conn)
    assert s["getan"] == "ausgesprochen" and s["kind"] == "weltfrage"
    assert s["proposal_id"]
    # danach ist die Lücke ausgesprochen -> die Besinnung sieht sie nicht mehr als selbst-möglich
    assert besinnung.agenda(conn)["selbst_moeglich"] is None


def test_der_loop_kettet_das_gefaelle_hinab(conn):
    # zwei heiße Lücken: der Gedankengang spricht sie NACH Druck geordnet aus, eine pro Schritt
    _luecken(conn, ("weltfrage", 6), ("tun", 4))
    schritte = besinnung.lauf(conn)
    getan = [s["kind"] for s in schritte if s["getan"] == "ausgesprochen"]
    assert getan == ["weltfrage", "tun"]                   # 6 vor 4 — das Gefälle hinab
    assert schritte[-1]["weiter"] is False                 # dann ist nichts Neues mehr auszusprechen


def test_besinne_wartet_ehrlich_wenn_es_selbst_nichts_tun_kann(conn):
    # eine ausgesprochene, ungestillte Lücke + eine fehlende Fähigkeit -> GENUS wartet auf Ronny
    _luecken(conn, ("weltfrage", 4))
    besinnung.besinne(conn)                                # weltfrage jetzt ausgesprochen
    ziele.seed_ziele(conn)
    s = besinnung.besinne(conn)
    assert s["getan"] == "gewartet"
    assert s["worauf"] is not None                         # es benennt, worauf es wartet


def test_die_besinnung_bewegt_den_geist_nie_die_hand(conn):
    # rein lesende Agenda/narrate erzeugen KEINE Events; nur besinne() mit einem echten
    # Aussprechen schreibt (ein gegatetes Proposal) -- die Reflexion selbst nicht
    _luecken(conn, ("weltfrage", 4))
    vorher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    besinnung.agenda(conn)
    besinnung.narrate(conn)
    assert conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"] == vorher


def test_narrate_ist_ehrlich_ueber_die_decke(conn):
    _luecken(conn, ("weltfrage", 4))
    besinnung.besinne(conn)                                # weltfrage ausgesprochen
    ziele.seed_ziele(conn)
    text = besinnung.narrate(conn)
    assert "warte ich auf dich" in text                   # die ausgesprochene Lücke wartet auf Ronny
    assert "generator-organ" in text and "Freigabe" in text   # die fehlende Fähigkeit braucht ihn


def test_ruhe_wenn_nichts_drueckt(conn):
    verstehen.seed_raster(conn)
    assert "ruhig" in besinnung.narrate(conn)
    assert besinnung.besinne(conn)["getan"] == "gewartet"


def test_lauf_ist_beschraenkt_gegen_endlosigkeit(conn):
    _luecken(conn, ("weltfrage", 6), ("tun", 4))
    assert len(besinnung.lauf(conn, hoechstens=1)) == 1    # höchstens ein Schritt
