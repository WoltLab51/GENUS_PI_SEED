"""Gesprächszelle „thema-echo“ — gefügt aus einem morphologischen Bauplan
(genus/bauplan.py): Wächter, Beschaffung und Formulierung sind geprüfte
Bestandteile; das Modell hat nur den Plan vorgeschlagen, nie den Code.
"""

def zelle_thema_echo(conn, guess, question, last_question, last_answer, stimme=None):
    subject = (guess or {}).get("subject")
    if not isinstance(subject, str) or not subject:
        return None
    return '„{subject}“ ist mir als Thema bekannt.'.format(subject=subject)
