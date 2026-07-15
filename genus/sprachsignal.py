"""Kleine deterministische Sprachsignale, die Modell-Deutungen im Kern gegenprüfen."""
import re


_HERKUNFT = re.compile(
    r"\b(?:warum|wieso|weshalb|woher|herkunft|ursprung|quelle|beleg\w*|herleit\w*)\b"
    r"|\bworan\s+liegt\b|\bwie\s+kommt\b",
    re.IGNORECASE | re.UNICODE,
)

_WIEDERHOLUNG = re.compile(
    r"\bnoch\s*mal\b|\bnochmal\b|\bnoch\s+einmal\b|\bwiederhol\w*\b|"
    r"\bsag\w*\s+(?:es|das)?\s*noch\s+einmal\b",
    re.IGNORECASE | re.UNICODE,
)


def hat_herkunftssignal(text: str) -> bool:
    """Nur explizite Warum-/Quellen-Sprache darf auf eine vorige Antwort zurückgreifen."""
    return bool(_HERKUNFT.search(text))


def hat_wiederholungssignal(text: str) -> bool:
    """Eine Modell-Lesart „wiederholen“ braucht ein ausdrückliches Wiederholungssignal."""
    return bool(_WIEDERHOLUNG.search(text))


def absicht_geerdet(kind: str, text: str) -> bool:
    """Enge semantische Sicherungen für besonders kontextmächtige Modell-Lesarten."""
    if not kind:
        return False
    if kind == "warum-herkunft":
        return hat_herkunftssignal(text)
    if kind == "wiederholen":
        return hat_wiederholungssignal(text)
    return True
