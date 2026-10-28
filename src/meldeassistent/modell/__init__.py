"""Internes Datenmodell (unabhängig von KIS, FHIR und DEMIS)."""

from .kis import (
    Adresse,
    Aufenthalt,
    Aufenthaltsabschnitt,
    Diagnose,
    Diagnosesicherheit,
    FallUebersicht,
    Geschlecht,
    KisFall,
    Laborbefund,
    Patient,
    Verstorben,
)

__all__ = [
    "Adresse",
    "Aufenthalt",
    "Aufenthaltsabschnitt",
    "Diagnose",
    "Diagnosesicherheit",
    "FallUebersicht",
    "Geschlecht",
    "KisFall",
    "Laborbefund",
    "Patient",
    "Verstorben",
]
