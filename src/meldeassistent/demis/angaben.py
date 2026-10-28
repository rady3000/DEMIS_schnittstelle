"""Eingaben für die DEMIS-Meldung: Melder/Einrichtung (Konfiguration) und Meldeangaben (Arzt/KIS).

Das interne KIS-Modell (``meldeassistent.modell``) liefert Patient, Aufenthalt und Diagnose. Hier stehen
die Angaben, die zusätzlich nötig sind: wer meldet, und die klinischen Angaben der Ärztin/des Arztes.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Krankheiten, für die der Mapper implementiert ist (Kürzel laut DEMIS)
UNTERSTUETZTE_KUERZEL = ("CDFD", "MYTD", "MSVD")
Kuerzel = Literal["CDFD", "MYTD", "MSVD"]


class _Basis(BaseModel):
    model_config = ConfigDict(frozen=True)


class Anschrift(_Basis):
    strasse: str
    plz: str
    ort: str
    land: str = "DE"


class MeldendeEinrichtung(_Basis):
    """Die Klinik als Melder (NotifierFacility). Wird aus der Konfiguration gelesen."""

    name: str
    art: str = Field(default="hospital", description="Code aus der DEMIS-Wertemenge organizationType")
    anschrift: Anschrift
    telefon: str
    email: str | None = None
    bsnr: str | None = Field(default=None, description="Betriebsstättennummer, falls vorhanden")
    demis_teilnehmer_id: str | None = None


class Laboreinrichtung(_Basis):
    """Das Labor, das den Erregernachweis erbringt (Verweis im Fragebogen). Meldet selbst nach § 7."""

    name: str
    art: str = Field(default="hospitalLab", description="Code aus organizationType, z. B. hospitalLab")
    telefon: str | None = None
    anschrift: Anschrift | None = None


class Melder(_Basis):
    """Die meldende Ärztin / der meldende Arzt."""

    vorname: str
    nachname: str
    telefon: str


class MelderKonfig(_Basis):
    einrichtung: MeldendeEinrichtung
    hauslabor: Laboreinrichtung | None = None


class Impfung(_Basis):
    """Eine Impfung (Immunization). Impfstoff-Code aus der DEMIS-Wertemenge vaccine<Kürzel>."""

    impfstoff_code: str
    datum: str | None = Field(default=None, description="JJJJ, JJJJ-MM oder JJJJ-MM-TT")
    anmerkung: str | None = None


class Meldeangaben(_Basis):
    """Alles, was die Ärztin/der Arzt zusätzlich zu den KIS-Daten angibt (oder die Vorbelegung vorschlägt).

    ``allgemein`` und ``spezifisch`` sind Antworten im einfachen Format von ``fragebogen.py``:
    ``{linkId: Wert}``. Verweise (labSpecimenLab, hospitalizedEncounter, immunizationRef) werden vom
    Mapper selbst gesetzt und müssen hier nicht angegeben werden.
    """

    kuerzel: Kuerzel
    verdacht: bool = False
    allgemein: dict[str, Any] = Field(default_factory=dict)
    spezifisch: dict[str, Any] = Field(default_factory=dict)
    impfungen: list[Impfung] = Field(default_factory=list)
    symptome: list[str] = Field(default_factory=list, description="nur Masern: Codes aus evidenceMSVD")
    diagnosehinweis: str | None = Field(default=None, description="Freitext zur Diagnose; wird nur gesendet, wenn die Ärztin/der Arzt ihn schreibt")
    hospitalisierungsgrund: str | None = Field(default=None, description="becauseOfDisease | becauseOfOtherReason | forIsolation")
    erkrankungsbeginn: date | None = None
    diagnosedatum: date | None = None
    labor: Laboreinrichtung | None = None
    herkunft: dict[str, str] = Field(
        default_factory=dict,
        description="Woher eine Angabe stammt, für die farbige Kennzeichnung im Meldebogen: 'kis' | 'auto' (Vorschlag) | 'arzt'. Schlüssel z. B. 'allgemein.isDead'",
    )
