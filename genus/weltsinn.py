"""Der WELT-SINN (P4): Wetter, Nachrichten und die eigene Uhr -- rein lesende, gläserne
Berichte, die die Membran stuendlich hereinreicht. KEIN Gespräch, KEINE Dispatch-Logik: das
sind die drei Welt-Sinne selbst (wahrnehmen, nie handeln). Die Zelle „weltfrage" in
:mod:`genus.companion` ruft sie; hier lebt nur das Wahrnehmen.

Herausgelöst aus ``companion.py`` (2026-07-09, Modularisierung Schritt ②): der Sinn ist
eigenständig -- er liest Ledger (Wetter) bzw. Membran-Puffer (News) bzw. die Pi-Uhr, formt
nichts um und schreibt nichts (Sinne lesen, Hände wirken). Nachrichten-Schlagzeilen sind
FREMDER, ungeprüffter Text: wortgetreu angezeigt, nie interpretiert -- GENUS handelt nie auf
eine Schlagzeile hin (beobachteter Inhalt = Daten, nie Befehl).
"""

_TREND_DE = {
    "rising": "Die Temperatur steigt gerade.",
    "falling": "Die Temperatur faellt gerade.",
    "stable": "Sie ist gerade recht konstant.",
}
_WETTER_FRISCH_STUNDEN = 2.0   # ~ zwei stuendliche Ticks; darueber ist der Wert nicht mehr „gerade"


def _formatiere_grad(wert) -> str:
    """Die Sensor-Zahl als deutscher Grad-Wert (Komma), auf eine Nachkommastelle -- lieber
    ehrlich rund als falsche Praezision."""
    zahl = float(wert)
    return f"{zahl:.1f}".replace(".", ",") + " °C"


def _wetter_alter_stunden(conn, claim_key, quelle):
    """Stunden zwischen JETZT (Wanduhr) und der neuesten Messung von ``claim_key`` aus der
    gewaehlten Quelle -- gegen die Wanduhr, NICHT relativ zur eigenen Reihe wie
    ``sources.resolve``'s ``live`` (das misst Frische nur zwischen Quellen und ist bei EINER
    Quelle immer 1.0). Nur ein echter Wanduhr-Vergleich laesst einen tage-alten Wert als „nicht
    mehr gerade" auffallen. Rein read-time (Mundstueck, nichts gespeichert -> Replay unberuehrt,
    wie die Motor-Erzaehlung). ``None``, wenn kein Zeitstempel lesbar ist."""
    from datetime import datetime, timezone

    from genus import sources

    stempel = [r["created_at"] for r in sources.assertions(conn, claim_key)
               if r["source"] == quelle and r.get("created_at")]
    if not stempel:
        return None
    try:
        ts = datetime.fromisoformat(max(stempel).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0


# WMO-Wetter-Codes (open-meteo) -> deutscher Zustand. Die Quelle liefert die Zahl; die
# Uebersetzung ist eine deterministische Nachschlage-Tabelle (kein Urteil, keine Erfindung).
_WMO_DE = {
    0: "klar", 1: "ueberwiegend klar", 2: "teils bewoelkt", 3: "bewoelkt",
    45: "neblig", 48: "gefrierender Nebel",
    51: "leichter Nieselregen", 53: "Nieselregen", 55: "dichter Nieselregen",
    56: "gefrierender Nieselregen", 57: "gefrierender Nieselregen",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen",
    66: "gefrierender Regen", 67: "gefrierender Regen",
    71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall", 77: "Schneegriesel",
    80: "leichte Regenschauer", 81: "Regenschauer", 82: "heftige Regenschauer",
    85: "Schneeschauer", 86: "starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "schweres Gewitter mit Hagel",
}


def _frischer_wert(conn, claim_key):
    """Ein zahlenwertiges Wetter-Feld aus dem Ledger -- aber NUR, wenn seine EIGENE neueste
    Messung frisch ist (absolutes Wanduhr-Alter <= :data:`_WETTER_FRISCH_STUNDEN`). Ein altes
    Feld (der letzte Fetch hat es ausgelassen, oder eine Zweitquelle hielt nur die Temperatur
    frisch) wird verschwiegen statt als aktuell ausgegeben -- jedes Feld traegt seine eigene
    Frische, nicht die der Temperatur. ``None`` auch bei keinem Wert, nicht-Zahl oder nan/inf
    (``int()``/``round()`` wuerden sonst krachen). Rein lesend."""
    import math

    from genus import sources

    res = sources.resolve(conn, claim_key)
    v = res.get("value")
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    alter = _wetter_alter_stunden(conn, claim_key, res.get("chosen_source"))
    if alter is None or alter > _WETTER_FRISCH_STUNDEN:
        return None
    return f


# --- der WELT-Sinn: Wetter ODER Nachrichten (P4) -----------------------------------------
#
# Der Deuter fasst beides als „weltfrage" (Etikett: „Wetter, Nachrichten, aktuelle Ereignisse").
# Hier wird unterschieden: Nachrichten-Schluesselwoerter -> News-Sinn, sonst -> Wetter-Sinn.
# Beide rein lesend, gläsern. Nachrichten-Schlagzeilen sind FREMDER, ungeprueffter Text: sie
# werden WORTGETREU angezeigt und nie interpretiert -- „weltfrage" ist wortlautfest, also formt
# die Stimme sie nie um, und GENUS handelt nie auf eine Schlagzeile hin (beobachteter Inhalt =
# Daten, nie Befehl). Der News-Puffer lebt an der MEMBRAN (deploy/observe_news.sh schreibt ihn,
# Ledger != Memory -- ephemerer Fremdtext gehoert nicht ins Ereignis-Ledger); der Kern LIEST ihn
# nur (kein HTTP im Kern).
_NEWS_SCHLUESSEL = ("neues", "neuigkeit", "nachricht", "news", "schlagzeile")
# Wetter-Woerter haben Vorrang: „das aktuelle WETTER" ist keine News-Frage. (Frueher fingen
# „aktuell"/„passiert" als News-Schluessel jede Wetterfrage ab -- Review-Fund, entfernt.)
_WETTER_SCHLUESSEL = ("wetter", "temperatur", "grad", "regen", "regnet", "warm", "kalt",
                      "sonne", "sonnig", "schnee", "wind", "sturm", "gewitter", "frost",
                      "bewoelkt", "bewölkt", "wolke")
_NEWS_MAX = 5
_NEWS_FRISCH_STUNDEN = 6.0
_NEWS_ANTWORT_MARKER = "Schlagzeilen ("   # GENUS' EIGENER Kopf einer News-Antwort mit Fremdtext


def _ist_news_frage(text) -> bool:
    t = (text or "").casefold()
    if any(w in t for w in _WETTER_SCHLUESSEL):   # eine Wetter-Frage bleibt Wetter
        return False
    return any(s in t for s in _NEWS_SCHLUESSEL)


def _lies_news_puffer():
    """Der Membran-News-Puffer (JSON) als Dict -- rein lesend, robust gegen fehlend/kaputt."""
    import json
    import os

    pfad = os.environ.get("GENUS_NEWS_PUFFER",
                          os.path.join(os.path.expanduser("~"), ".genus", "news_puffer.json"))
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _puffer_alter_stunden(ts):
    """Stunden seit dem Puffer-Zeitstempel (Wanduhr) -- ``None``, wenn nicht lesbar."""
    from datetime import datetime, timezone

    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def _news_bericht(conn):
    """Die aktuellen Schlagzeilen aus dem Membran-Puffer -- WORTGETREU (Fremdtext, nie
    interpretiert), mit Frische + Quelle, ehrlich, wenn nichts (Frisches) da ist."""
    puffer = _lies_news_puffer() or {}
    roh = puffer.get("schlagzeilen")
    zeilen = ([z.get("titel") for z in roh if isinstance(z, dict) and z.get("titel")]
              if isinstance(roh, list) else [])   # robust: schlagzeilen kein/kaputte Liste -> leer
    if not zeilen:
        return ("Nach Nachrichten kann ich schon greifen, aber gerade habe ich keine "
                "Schlagzeilen — mein Nachrichten-Sinn erreicht die Welt im Moment nicht.")
    quelle = puffer.get("quelle") or "meiner Nachrichtenquelle"
    alter = _puffer_alter_stunden(puffer.get("ts"))
    if alter is not None and alter > _NEWS_FRISCH_STUNDEN:
        wann = (f"von vor rund {round(alter / 24)} Tagen" if alter >= 24
                else f"von vor rund {round(alter)} Stunden")
        kopf = f"Meine letzten Schlagzeilen ({wann}, laut {quelle}) — frischere habe ich gerade nicht:"
    else:
        kopf = f"Die aktuellen Schlagzeilen (laut {quelle}):"
    liste = "\n".join(f"• {titel}" for titel in zeilen[:_NEWS_MAX])
    return f"{kopf}\n{liste}"


# Der billigste Sinn: die eigene Uhr. GENUS liest die Pi-Uhr (read-time, kein Netz noetig) und
# weiss aus dem bestehenden Uhr-Check (operation, system.clock), ob es einen NTP-Vorbehalt
# anhaengen muss -- ein selbst-bezueglicher Sinn (die eigene Zeit + das Vertrauen darin).
# Bewusst EINDEUTIGE Wendungen: „welche zeit" (Teilstring von „Zeitung") und das breite
# „welcher tag" sind RAUS (Review-Fund) -- und eine Zeit-Frage weicht ohnehin Wetter/News-
# Woertern, damit „Welcher Wochentag wird der waermste?" nicht die Uhr zieht.
_ZEIT_SCHLUESSEL = ("wie spät", "wie spaet", "spät ist", "spaet ist", "uhrzeit",
                    "wie viel uhr", "wieviel uhr", "welche uhrzeit", "welches datum",
                    "welcher wochentag", "welchen wochentag", "der wievielte")
_WOCHENTAG_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _ist_zeit_frage(text) -> bool:
    t = (text or "").casefold()
    if any(w in t for w in _WETTER_SCHLUESSEL) or any(s in t for s in _NEWS_SCHLUESSEL):
        return False   # eine Wetter-/News-Frage bleibt Wetter/News, auch mit Zeit-Wort drin
    return any(s in t for s in _ZEIT_SCHLUESSEL)


def _uhrzeit_bericht(conn):
    """Die aktuelle Uhrzeit + Datum aus der Pi-eigenen Uhr -- mit ehrlichem NTP-Vorbehalt, wenn
    der Uhr-Check (system.clock) die Uhr als nicht synchronisiert kennt. Rein lesend."""
    from datetime import datetime

    from genus import projection

    jetzt = datetime.now()
    satz = (f"Es ist gerade {jetzt.strftime('%H:%M')} Uhr — {_WOCHENTAG_DE[jetzt.weekday()]}, "
            f"der {jetzt.strftime('%d.%m.%Y')}.")
    clock = projection.active_belief(conn, "system.clock")
    if clock is not None and clock["claim_value"] == "unsynchronized":
        satz += " (Meine Uhr ist gerade nicht mit der Netzzeit synchron — also ohne Gewähr.)"
    return satz


def wetter_kurz(conn):
    """Eine kurze Wetter-Zeile fuer den Morgen-Gruss (Zustand + Temperatur) -- nur bei FRISCHEM
    Wert; ``None`` sonst (dann schweigt der Morgen zum Wetter, statt Altes zu behaupten)."""
    from genus import sources

    temp_res = sources.resolve(conn, "weather.temp_outside")
    wert = temp_res.get("value")
    if wert is None:
        return None
    alter = _wetter_alter_stunden(conn, "weather.temp_outside", temp_res.get("chosen_source"))
    if alter is None or alter > _WETTER_FRISCH_STUNDEN:
        return None
    code = _frischer_wert(conn, "weather.code")
    zustand = _WMO_DE.get(int(code)) if code is not None else None
    return f"{zustand}, {_formatiere_grad(wert)}" if zustand else _formatiere_grad(wert)


def news_top(conn):
    """Die oberste AKTUELLE Schlagzeile (wortgetreu) fuer den Morgen-Gruss -- ``None``, wenn
    keine (frischen) da sind. Fremdtext: der Morgen-Gruss wird deterministisch und WORTGETREU
    gesendet (kein Modell), also bleibt die Schlagzeile unangetastet wie im Chat."""
    puffer = _lies_news_puffer() or {}
    alter = _puffer_alter_stunden(puffer.get("ts"))
    if alter is None or alter > _NEWS_FRISCH_STUNDEN:   # kein Alter bekannt = nicht als frisch zeigen
        return None
    roh = puffer.get("schlagzeilen")
    if not isinstance(roh, list):
        return None
    for z in roh:
        if isinstance(z, dict) and z.get("titel"):
            return z["titel"]
    return None


def _wetter_bericht(conn):
    """Spricht den wahrgenommenen Wetter-Bericht aus -- rein lesend. Ehrliche Teil-Antwort:
    jedes reiche Feld (Zustand, gefuehlt, Feuchte, Wind, Vorhersage, Regen) wird nur genannt,
    wenn es wirklich UND frisch im Ledger liegt; fehlt/veraltet es, wird geschwiegen, nie
    erfunden."""
    from genus import projection, sources

    temp_res = sources.resolve(conn, "weather.temp_outside")
    wert = temp_res.get("value")
    if wert is None:
        return ("Von der Welt draussen fuehle ich das Wetter — aber gerade habe ich keinen "
                "Wert: mein Wetter-Sinn erreicht die Welt im Moment nicht. Frag gern spaeter "
                "noch einmal.")
    quelle = temp_res.get("chosen_source")
    alter = _wetter_alter_stunden(conn, "weather.temp_outside", quelle)
    if not (alter is not None and alter <= _WETTER_FRISCH_STUNDEN):
        # nicht frisch: nur der letzte Temperatur-Wert, ehrlich als alt benannt -- keine alten
        # Detailfelder als aktuell ausgeben
        if alter is None:
            return (f"Mein letzter Wetter-Wert war {_formatiere_grad(wert)}, aber wie frisch er "
                    f"ist, weiss ich gerade nicht. Mehr sage ich dir mit einem frischen Wert.")
        wann = (f"vor rund {round(alter / 24)} Tagen" if alter >= 24
                else f"vor rund {round(alter)} Stunden")
        return (f"Mein letzter Wetter-Wert ({wann}) war {_formatiere_grad(wert)} — frischer habe "
                f"ich gerade nichts. Sobald mein Sinn wieder etwas empfaengt, sage ich dir mehr.")

    # frisch -> der reiche Bericht, jede Zutat nur bei echtem UND frischem Material (jedes Feld
    # traegt seine eigene Frische -- ein altes Feld wird verschwiegen, nie als aktuell gesprochen)
    code = _frischer_wert(conn, "weather.code")
    zustand = _WMO_DE.get(int(code)) if code is not None else None
    gefuehlt = _frischer_wert(conn, "weather.apparent")
    feuchte = _frischer_wert(conn, "weather.humidity")
    wind = _frischer_wert(conn, "weather.wind")
    tmax = _frischer_wert(conn, "weather.temp_max")
    tmin = _frischer_wert(conn, "weather.temp_min")
    regen = _frischer_wert(conn, "weather.rain_prob")

    kern = f"{zustand} bei {_formatiere_grad(wert)}" if zustand else _formatiere_grad(wert)
    if gefuehlt is not None and abs(gefuehlt - float(wert)) >= 1.0:
        kern += f" (gefuehlt {_formatiere_grad(gefuehlt)})"
    satz = f"Gerade draussen: {kern}."
    trend_row = projection.active_belief(conn, "weather.trend")
    trend = _TREND_DE.get(trend_row["claim_value"]) if trend_row else None
    if trend:
        satz += " " + trend
    detail = []
    if feuchte is not None:
        detail.append(f"Luftfeuchte {round(feuchte)} %")
    if wind is not None:
        detail.append(f"Wind {round(wind)} km/h")
    if detail:
        satz += " " + ", ".join(detail) + "."
    if tmin is not None and tmax is not None:
        satz += f" Heute {_formatiere_grad(tmin)} bis {_formatiere_grad(tmax)}"
        satz += (f", Regenwahrscheinlichkeit {round(regen)} %." if regen is not None else ".")
    elif regen is not None:
        satz += f" Regenwahrscheinlichkeit heute {round(regen)} %."
    if quelle and quelle != "weather.api":   # ein echter Provider-Name, kein internes Alt-Label
        satz += f" Diese Werte kommen von {quelle}."
    if temp_res.get("contradiction"):
        satz += " Meine Wetterquellen sind sich bei der Temperatur uneinig, also ohne Gewaehr."
    if tmax is not None:
        satz += " Fuer andere Orte oder weiter als heute reicht mein Wetter-Sinn noch nicht."
    else:
        satz += (" Vorhersage, Regen oder andere Orte kann ich noch nicht — dafuer fehlt meinem "
                 "Wetter-Sinn noch Material.")
    return satz
