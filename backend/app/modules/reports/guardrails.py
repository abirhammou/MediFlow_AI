"""Garde-fou déterministe : aucun fait médical absent des notes.

Première barrière, volontairement simple : toute valeur numérique du compte rendu
(température, tension, dosage, durée, date...) doit exister dans les notes.
Limite connue : un nombre écrit en lettres dans les notes (« deux jours ») et en chiffres
dans le compte rendu (« 2 jours ») sera signalé. Le médecin tranche à la finalisation.
"""

import re
from decimal import Decimal, InvalidOperation

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _normalize(value: str) -> str:
    try:
        return format(Decimal(value.replace(",", ".")).normalize(), "f")
    except InvalidOperation:
        return value


def _numbers(text: str) -> set[str]:
    return {_normalize(match) for match in _NUMBER.findall(text)}


def check_content(raw_notes: str, content: str) -> list[str]:
    """Retourne la liste des avertissements (vide si tout est cohérent avec les notes)."""
    unknown = sorted(_numbers(content) - _numbers(raw_notes), key=lambda v: (len(v), v))
    return [f"La valeur « {value} » n'apparaît pas dans les notes." for value in unknown]
