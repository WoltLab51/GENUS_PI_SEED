"""Entwurf: Gesprächszelle „weltfrage“ — erzeugt von GENUS' Werkstatt (Stufe 2).

Dieser Entwurf läuft NIE automatisch: er lebt außerhalb des Kerns, wird in der
Werkstatt geprüft (Verbots-Scan + Sandbox-Probefahrt) und wird erst durch einen
menschlichen Git-Merge Teil der Hülle.
"""


def zelle_weltfrage(conn, guess, question, last_question, last_answer, stimme=None):
    # Der Zellen-Vertrag: liest nur aus dem Graphen (conn), erfindet nie Fakten,
    # gibt einen deutschen Antwortsatz zurück -- oder None (ehrliches Passen).
    # TODO (Generator oder Mensch): die eigentliche Fähigkeit.
    return None

import requests
import subprocess
