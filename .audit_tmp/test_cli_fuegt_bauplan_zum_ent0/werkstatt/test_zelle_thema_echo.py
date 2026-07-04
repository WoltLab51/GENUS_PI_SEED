"""Sandbox-Tests für den Entwurf „thema-echo“ -- laufen NUR in der Werkstatt
(deploy/werkstatt_probefahrt.sh), nie im lebenden Prozess."""
import inspect

import pytest

from zelle_thema_echo import zelle_thema_echo


def test_vertrag_signatur():
    # der uniforme Zellen-Vertrag (wie werkzeug.pruefen ihn prüfen wird)
    parameter = list(inspect.signature(zelle_thema_echo).parameters)
    assert parameter == ["conn", "guess", "question", "last_question",
                         "last_answer", "stimme"]


def test_faehigkeit():
    # TODO (Generator oder Mensch): der eigentliche Fähigkeits-Test.
    pytest.skip("Entwurf: Fähigkeit noch nicht gebaut")
