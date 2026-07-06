"""Der MOTOR-STATUS (Ronny 2026-07-06, P2.1: „was im Motor ist wie weit? ich will genau
schauen, wie GENUS denkt und wie rund das ist"). Die qualitative Denk-Motor-Zustandskarte,
jetzt als LEBENDIGES, deterministisches Instrument aus dem eigenen Ledger: pro Denkweise misst
GENUS (a) ob jede Selbst-Kalibrierung GELERNT oder noch auf SAAT steht (mit der Population
dahinter) und (b) wie oft die Denkweise wirklich FEUERT -- eine zählbare Spur im Ledger
hinterlässt.

Read-time, gläsern, schreibt NICHTS -- ein Report darf den Ledger nie verändern (dieselbe
Disziplin wie ``genus knowledge`` / ``genus atlas-facts``). Die ehrliche Pointe der
Zustandskarte bleibt ausdrücklich sichtbar: die MEISTEN Denkweisen sehen und urteilen
read-time, ohne je eine Spur zu hinterlassen (inference-Heißpfad, Subsumtion, Modus Ponens,
der reine Antwort-Pfad …). Sie werden als „unvermessen" BENANNT -- nie mit einer erfundenen
Zahl geschönt. Genau das ist der Befund: GENUS sieht reich, handelt selten.

``zustand(conn)`` liefert die reinen Zahlen (strukturiert, testbar), ``narrate(conn)`` rendert
sie als ``[MOT]``-Zeilen (Glass-Box, deterministisch, im Ton von ``genus knowledge``).
"""
from __future__ import annotations

MOT = "[MOT]"


def _count(conn, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def _gruppen(conn, sql: str, params: tuple = ()) -> dict[str, int]:
    """Eine ``GROUP BY``-Zählung als {Wert: Anzahl} -- None-Schlüssel zu '(leer)' entschärft."""
    return {(r[0] if r[0] is not None else "(leer)"): int(r[1])
            for r in conn.execute(sql, params).fetchall()}


def _kalib_zustand(wert, seed, ist_float: bool = False, abgeleitet: bool | None = None) -> dict:
    """Die drei ehrlichen Kalibrierungs-Lagen (wie ``genus knowledge``, cli.py:587-599):
    ``saat`` = kein trennendes Muster (nie kalibriert); ``bestaetigt`` = gelernt, gleich der Saat
    (durch die Daten validiert); ``gelernt`` = aus der natürlichen Lücke abgeleitet, weicht ab.

    Zwei Signale für „saat", je nach Denkweise: ``wert is None`` (kein Schnappschuss -- so melden
    es Transitivität/Symmetrie/Inverse) ODER ``abgeleitet is False`` (der Wert wurde berechnet,
    fiel aber mangels Population auf die Saat zurück -- so meldet es das Geschlecht/die
    Reboot-Schwelle, deren Kalibrierung IMMER einen Wert liefert). Ohne dieses zweite Signal
    läse ein Gleich-der-Saat-Rückfall fälschlich als „durch die Daten bestätigt"."""
    if abgeleitet is False or wert is None:
        return {"lage": "saat", "wert": seed, "seed": seed}
    gleich = abs(wert - seed) < 1e-9 if ist_float else wert == seed
    return {"lage": "bestaetigt" if gleich else "gelernt", "wert": wert, "seed": seed}


def zustand(conn) -> dict:
    """Read-time-Zustand des Denk-Motors: je Denkweise die Kalibrierungs-Lage (gelernt/Saat) und
    die zählbaren Feuer-Spuren. Deterministisch; schreibt nichts (nur SELECTs + Lese-Helfer)."""
    from genus import (experience, gender_rule, governance, hypothese, inference,
                       operation, sources, verstehen)

    k = sources.characterize_knowledge(conn)

    # --- SCHLIESSEN (die geteilte Inferenz) ---------------------------------------------------
    inv_stored = inference.stored_inverses(conn)
    inverse = {
        "lage": ("saat" if inv_stored is None
                 else "bestaetigt" if inv_stored == inference.INVERSE_PREDICATES
                 else "gelernt"),
        "paare": inv_stored if inv_stored is not None else inference.INVERSE_PREDICATES,
        "seed": inference.INVERSE_PREDICATES,
    }
    rule_kalib_erfahrungen = _count(
        conn, "SELECT COUNT(*) FROM experience_log WHERE experience_type = ?",
        (experience.RULE_CALIBRATION_TYPE,))
    # Recharakterisierungen sind NACH experience_key zu trennen (Review-Fund): das eine
    # experience_recharacterized-Event trägt BeliefStability- UND Kalibrierungs-Neubewertungen;
    # ungetrennt läse die SCHLIESSEN-Zeile eine stabil↔volatil-Kippung als Kalibrierungs-Feuer.
    kalib_recharakterisierungen = _count(
        conn, "SELECT COUNT(*) FROM event_log WHERE event_type = 'experience_recharacterized' "
        "AND json_extract(payload, '$.experience_key') LIKE 'rule_calibration:%'")

    # --- GESCHLECHT (Suffix-Regel) ------------------------------------------------------------
    gender = gender_rule.reliability_cut_report(conn)   # {cut, population, derived}

    # --- ERHOLUNG (die einzige Stelle, an der GENUS an der Maschine handelt) -------------------
    reboot = governance.reboot_threshold_report(conn)   # {threshold, episodes, derived}
    reboot_feuer = _count(
        conn,
        "SELECT COUNT(*) FROM event_log WHERE event_type = ? "
        "AND json_extract(payload, '$.action') = ?",
        (operation.RECOVERY_ATTEMPT_EVENT, operation.ACTION_REBOOT))
    erholungs_versuche = _count(
        conn, "SELECT COUNT(*) FROM event_log WHERE event_type = ?",
        (operation.RECOVERY_ATTEMPT_EVENT,))

    # --- VERSTEHEN (Zwicky-Dispatch, die reichste Feuer-Spur) ---------------------------------
    blaetter = [b for b, _ in verstehen.RASTER_SEED]
    belegung_je_quelle: dict[str, int] = {}
    fehlgriffe_gesamt = 0
    belegte = 0
    for b in blaetter:
        bel = verstehen.belegung(conn, b)
        if bel["gesamt"] > 0:
            belegte += 1
        for q, n in bel["je_quelle"].items():
            belegung_je_quelle[q] = belegung_je_quelle.get(q, 0) + n
        fehlgriffe_gesamt += verstehen.fehlgriffe(conn, b)["gesamt"]
    verwechslungs_muster = len(verstehen.verwechslungen(conn))

    # --- VERMUTEN (Hypothese) -----------------------------------------------------------------
    stehende_vermutungen = _count(
        conn, "SELECT COUNT(*) FROM relation_projection WHERE source = ?",
        (hypothese.MODEL_QUELLE,))

    # --- GLAUBEN-STABILITÄT -------------------------------------------------------------------
    belief_stability = _count(
        conn, "SELECT COUNT(*) FROM experience_log WHERE experience_type = ?",
        (experience.BELIEF_STABILITY_TYPE,))
    stabilitaet_recharakterisierungen = _count(
        conn, "SELECT COUNT(*) FROM event_log WHERE event_type = 'experience_recharacterized' "
        "AND json_extract(payload, '$.experience_key') LIKE 'belief_stability:%'")
    verstehens_luecken = _count(
        conn, "SELECT COUNT(*) FROM experience_log WHERE experience_type = ?",
        (experience.VERSTEHENS_LUECKE_TYPE,))

    # --- MOTOR-AUSSTOSS (Proposal -> Regel) ---------------------------------------------------
    proposals = _gruppen(conn, "SELECT state, COUNT(*) FROM proposal_log GROUP BY state")
    inquiries = _gruppen(conn, "SELECT state, COUNT(*) FROM inquiry_log GROUP BY state")
    regeln = _gruppen(conn, "SELECT status, COUNT(*) FROM rule_projection GROUP BY status")

    return {
        "schliessen": {
            "transitivitaet": _kalib_zustand(k["transitivity_threshold"], k["transitivity_seed"]),
            "symmetrie": _kalib_zustand(k["symmetry_rate"], k["symmetry_seed"], ist_float=True),
            "inverse": inverse,
            "kalibrierung_feuerte": rule_kalib_erfahrungen,
            "recharakterisierungen": kalib_recharakterisierungen,
        },
        "geschlecht": {
            **_kalib_zustand(gender["cut"], gender_rule.MIN_RELIABILITY, ist_float=True,
                             abgeleitet=gender["derived"]),
            "population": gender["population"],
        },
        "erholung": {
            "schwelle": reboot, "seed": governance.RECOVERY_REBOOT_MIN_FAILURES,
            "min_episoden": governance.MIN_RECOVERY_EPISODES,
            "reboot_ausgeloest": reboot_feuer, "erholungs_versuche": erholungs_versuche,
        },
        "verstehen": {
            "belegung_je_quelle": belegung_je_quelle,
            "belegte_blaetter": belegte, "blaetter_gesamt": len(blaetter),
            "fehlgriffe": fehlgriffe_gesamt, "verwechslungs_muster": verwechslungs_muster,
            "verwechslungs_seed": verstehen.VERWECHSLUNG_SEED,
        },
        "vermuten": {"stehende_vermutungen": stehende_vermutungen},
        "glauben_stabilitaet": {
            "belief_stability": belief_stability, "verstehens_luecken": verstehens_luecken,
            "recharakterisierungen": stabilitaet_recharakterisierungen,
        },
        "ausstoss": {"proposals": proposals, "inquiries": inquiries, "regeln": regeln},
    }


# Denkweisen, die read-time SEHEN und URTEILEN, ohne je eine Spur im Ledger zu hinterlassen --
# ihre „Feuer-Rate" ist strukturell NICHT zählbar (jeder Aufruf ist ein Neu-Rechnen auf dem
# Graphen, kein Event). Sie werden ehrlich benannt, nie mit einer Ersatz-Zahl geschönt: genau
# das ist der Befund der Zustandskarte (GENUS sieht reich, handelt selten).
_UNVERMESSEN = (
    "Schließen im Betrieb (inference.infer / is_transitive / is_symmetric / inverse_of) — "
    "jede Kette ist ein Read-time-Rescan; nur die periodische Kalibrierung oben ist zählbar",
    "Subsumtion (recht) — read-time gerechnet, der Sachverhalt ist flüchtig (kein Fall im Ledger)",
    "Modus Ponens (deduktion — schliesse / leite_ab / beweise) — reine Regelgraph-Traversierung",
    "Companion nicht-gesprächlicher Pfad (die reine CLI-»ask«-Route + der Wort-Lookup) — er "
    "zeichnet bewusst nichts auf; die gesprächlichen Pfade (Muster- UND Deuter-Dispatch) "
    "hinterlassen dagegen eine Spur — genau die Belegung oben (Quelle »muster« bzw. »model:deuter«)",
    "Geschlechts-Vorhersage (gender_rule.predict_gender) — read-time, kein Event",
    "Quellen-Vertrauen (sources.source_trust, Kadenz, Toleranzband) — je Abfrage neu aus dem "
    "Ereignisstrom gerechnet, ohne gespeicherte Historie",
)


def _kalib_text(z: dict, einheit: str = "") -> str:
    w, s = z["wert"], z["seed"]
    if z["lage"] == "saat":
        return f"{w}{einheit} — Saat, noch nicht selbst-kalibriert (»genus scan« läuft)"
    if z["lage"] == "bestaetigt":
        return f"{w}{einheit} — selbst-kalibriert, gleich der Saat (durch die Daten bestätigt)"
    return f"{w}{einheit} — selbst-kalibriert aus der natürlichen Lücke (Saat war {s}{einheit})"


def _paare_text(paare: dict) -> str:
    return ", ".join(f"{a}↔{b}" for a, b in sorted(paare.items())) if paare else "(keine)"


def _gruppen_text(g: dict) -> str:
    return ", ".join(f"{k}: {v}" for k, v in sorted(g.items())) if g else "keine"


def narrate(conn) -> list[str]:
    """Rendert :func:`zustand` als ``[MOT]``-Zeilen -- gläsern, deterministisch, read-time.
    Benennt die unvermessenen Denkweisen ausdrücklich, statt eine Zahl zu erfinden."""
    z = zustand(conn)
    s, g, e = z["schliessen"], z["geschlecht"], z["erholung"]
    v, vm = z["verstehen"], z["vermuten"]
    gl, au = z["glauben_stabilitaet"], z["ausstoss"]
    L: list[str] = [
        f"{MOT} === DENK-MOTOR: Selbstvermessung (read-time, schreibt nichts) ===",
        f"{MOT}",
        f"{MOT} SCHLIESSEN — die geteilte Inferenz (Transitivität / Symmetrie / Inverse):",
        f"{MOT}   Transitivitäts-Schwelle: {_kalib_text(s['transitivitaet'])}",
        f"{MOT}   Symmetrie-Rate: {_kalib_text(s['symmetrie'])}",
    ]
    inv = s["inverse"]
    inv_lage = ("Saat, noch nicht selbst-kalibriert" if inv["lage"] == "saat"
                else "gleich der Saat (bestätigt)" if inv["lage"] == "bestaetigt"
                else f"selbst-erkannt (Saat war {_paare_text(inv['seed'])})")
    L += [
        f"{MOT}   Inverse-Paare: {_paare_text(inv['paare'])} — {inv_lage}",
        f"{MOT}   Kalibrierung feuerte: {s['kalibrierung_feuerte']} RuleCalibration-Erfahrung(en), "
        f"{s['recharakterisierungen']} Kalibrierungs-Recharakterisierung(en)",
        f"{MOT}   (die Schlüsse selbst sind read-time — keine Spur je Inferenz, nicht zählbar)",
        f"{MOT}",
        f"{MOT} GESCHLECHT — die Suffix-Regel:",
        f"{MOT}   Verlässlichkeits-Schnitt: {_kalib_text(g)} "
        f"(Population: {g['population']} tragfähige Suffixe)",
        f"{MOT}",
        f"{MOT} ERHOLUNG — die EINZIGE Stelle, an der GENUS an der Maschine handelt:",
    ]
    rb = e["schwelle"]
    if rb["derived"]:
        rb_text = (f"{rb['threshold']} — selbst-kalibriert aus {rb['episodes']} "
                   f"Erholungs-Episode(n) (Saat war {e['seed']})")
    elif rb["episodes"] < e["min_episoden"]:
        # zu wenige abgeschlossene Episoden, um überhaupt ein Muster zu zeigen
        rb_text = (f"{rb['threshold']} — Saat (erst {rb['episodes']} von ≥{e['min_episoden']} "
                   f"nötigen Erholungs-Episoden)")
    else:
        # GENUG Episoden, aber ohne trennende Lücke (alle ähnlich lang) -- NICHT „zu wenige"
        # (Live-Fund: 10 Episoden, alle gleich lang -> ehrlich „kein Muster", nicht „braucht mehr")
        rb_text = (f"{rb['threshold']} — Saat ({rb['episodes']} Episoden, aber ohne trennende "
                   f"Lücke — alle ähnlich lang, noch kein Muster)")
    L += [
        f"{MOT}   Reboot-Schwelle: {rb_text}",
        f"{MOT}   Reboot wirklich ausgelöst: {e['reboot_ausgeloest']} mal "
        f"(von {e['erholungs_versuche']} Erholungs-Versuch(en) gesamt)",
        f"{MOT}",
        f"{MOT} VERSTEHEN — der Zwicky-Dispatch (die reichste Feuer-Spur):",
    ]
    bq = v["belegung_je_quelle"]
    belegung_text = _gruppen_text(bq) if bq else "noch nie gefeuert"
    L += [
        f"{MOT}   Belegung je Herkunft: {belegung_text}",
        f"{MOT}   Abdeckung: {v['belegte_blaetter']} von {v['blaetter_gesamt']} "
        f"Feinblättern haben je gefeuert",
        f"{MOT}   Fehlgriffe gesamt: {v['fehlgriffe']} "
        f"(QM-Signal: hoch = Deuter-Problem, nicht Kern-Problem)",
        f"{MOT}   Verwechslungs-Muster: {v['verwechslungs_muster']} "
        f"(Schwelle-Saat {v['verwechslungs_seed']})",
        f"{MOT}",
        f"{MOT} VERMUTEN — die Hypothese (Geschwister-Analogie, gedeckelt emittiert):",
        f"{MOT}   Stehende Vermutungen (model:hypothese, Trust ≤ 0.25): "
        f"{vm['stehende_vermutungen']}",
        f"{MOT}   (vermute / teste sind read-time — nur die offene Emission hinterlässt eine Spur)",
        f"{MOT}",
        f"{MOT} GLAUBEN-STABILITÄT — der Erfahrungs-Detektor über die eigene Kognition:",
        f"{MOT}   BeliefStability-Erfahrungen: {gl['belief_stability']} "
        f"(davon {gl['recharakterisierungen']} stabil↔volatil neu bewertet)",
        f"{MOT}   VerstehensLücke-Erfahrungen: {gl['verstehens_luecken']}",
        f"{MOT}",
        f"{MOT} MOTOR-AUSSTOSS — Proposal → Regel (das nachgelagerte Handeln):",
        f"{MOT}   Proposals: {_gruppen_text(au['proposals'])}",
        f"{MOT}   Inquiries (offene Fragen): {_gruppen_text(au['inquiries'])}",
        f"{MOT}   Gereifte Regeln: {_gruppen_text(au['regeln'])}",
        f"{MOT}",
        f"{MOT} READ-TIME, UNVERMESSEN — sehen/urteilen ohne Spur (die ehrliche Decke):",
    ]
    L += [f"{MOT}   • {u}" for u in _UNVERMESSEN]
    return L
