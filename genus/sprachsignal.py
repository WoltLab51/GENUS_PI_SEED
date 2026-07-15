"""Kleine deterministische Sprachsignale, die Modell-Deutungen im Kern gegenprüfen."""
import re


_HERKUNFT = re.compile(
    r"\b(?:warum|wieso|weshalb|woher|herkunft|ursprung|quelle|beleg\w*|herleit\w*)\b"
    r"|\bworan\s+liegt\b|\bwie\s+kommt\b",
    re.IGNORECASE | re.UNICODE,
)


def hat_herkunftssignal(text: str) -> bool:
    """Nur explizite Warum-/Quellen-Sprache darf auf eine vorige Antwort zurückgreifen."""
    return bool(_HERKUNFT.search(text))
