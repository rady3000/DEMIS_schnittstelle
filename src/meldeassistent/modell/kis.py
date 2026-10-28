"""Internes Datenmodell für alles, was aus dem KIS kommt.

Der Rest der Anwendung (Regelwerk, Meldebogen, DEMIS-Mapper, Oberfläche) kennt NUR dieses Modell,
nicht FHIR, ISiK oder NEXUS. So lässt sich später ein HL7-v2-Adapter ergänzen, ohne den Rest
anzufassen.

Grundsatz "fehlt = unbekannt, nicht = nein": Was das KIS nicht liefert, bleibt ``None`` bzw.
``UNBEKANNT``. Der Meldebogen fragt dann die Ärztin/den Arzt, statt etwas zu unterstellen.
``KisFall.hinweise`` sammelt verständliche Hinweise auf Lücken in den KIS-Daten.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def vergleichswert(zeitpunkt: datetime) -> datetime:
    """Macht Zeitstempel mit und ohne Zeitzone vergleichbar (Zeitzonen werden auf UTC umgerechnet).

    Ohne Zeitzone gelesene Zeitpunkte gelten als gleiche Ortszeit wie die übrigen Daten des KIS.
    """
    if zeitpunkt.tzinfo is not None:
        return zeitpunkt.astimezone(timezone.utc).replace(tzinfo=None)
    return zeitpunkt


class _Basis(BaseModel):
    # unveränderlich: Ein aus dem KIS gelesener Fall wird nie stillschweigend verändert
    model_config = ConfigDict(frozen=True)


class Geschlecht(str, Enum):
    MAENNLICH = "maennlich"
    WEIBLICH = "weiblich"
    DIVERS = "divers"
    UNBESTIMMT = "unbestimmt"
    UNBEKANNT = "unbekannt"


class Verstorben(str, Enum):
    """JA/NEIN nur, wenn das KIS es ausdrücklich sagt. Fehlt die Angabe: UNBEKANNT."""

    JA = "ja"
    NEIN = "nein"
    UNBEKANNT = "unbekannt"


class Diagnosesicherheit(str, Enum):
    """Nach dem ICD-10-GM-Schlüssel der Diagnosesicherheit (G, V, A, Z)."""

    GESICHERT = "gesichert"
    VERDACHT = "verdacht"
    AUSGESCHLOSSEN = "ausgeschlossen"
    ZUSTAND_NACH = "zustand_nach"
    UNBEKANNT = "unbekannt"


class Adresse(_Basis):
    zeilen: list[str] = Field(default_factory=list, description="Adresszeilen wie im KIS, z. B. 'Musterstraße 12'")
    strasse: str | None = None
    hausnummer: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str | None = None


class Patient(_Basis):
    kis_patienten_id: str = Field(description="Technische ID im KIS (nur intern, nie in Logs)")
    patientennummer: str | None = Field(default=None, description="Organisationsinterne Patientennummer (MR)")
    vorname: str
    nachname: str
    geburtsdatum: date | None = None
    geschlecht: Geschlecht = Geschlecht.UNBEKANNT
    adresse: Adresse | None = None
    telefon: str | None = None
    email: str | None = None
    verstorben: Verstorben = Verstorben.UNBEKANNT
    verstorben_am: datetime | None = None

    @property
    def anzeigename(self) -> str:
        return f"{self.nachname}, {self.vorname}"


class Aufenthaltsabschnitt(_Basis):
    """Ein Abschnitt auf einer Station / in einer Fachabteilung (Abteilungs-/Versorgungsstellenkontakt)."""

    station: str | None = None
    fachabteilung_schluessel: str | None = Field(default=None, description="Fachabteilungsschlüssel, z. B. 3600 = Intensivmedizin")
    fachabteilung_name: str | None = None
    beginn: datetime | None = None
    ende: datetime | None = None

    @property
    def ist_intensivstation(self) -> bool:
        return self.fachabteilung_schluessel == "3600"


class Aufenthalt(_Basis):
    """Der stationäre Fall (Einrichtungskontakt) mit seinen Abschnitten."""

    kis_fall_id: str = Field(description="Technische ID des Einrichtungskontakts im KIS")
    besuchsnummer: str | None = None
    laufend: bool = Field(description="True, wenn der Aufenthalt noch nicht beendet ist")
    beginn: datetime | None = None
    ende: datetime | None = None
    entlassen_wegen_tod: bool = False
    abschnitte: list[Aufenthaltsabschnitt] = Field(default_factory=list)

    @property
    def aktuelle_station(self) -> str | None:
        """Station des zuletzt begonnenen Abschnitts (bei laufenden Fällen: wo der Patient jetzt liegt)."""
        mit_beginn = [a for a in self.abschnitte if a.beginn]
        if not mit_beginn:
            return self.abschnitte[-1].station if self.abschnitte else None
        return max(mit_beginn, key=lambda a: vergleichswert(a.beginn)).station

    @property
    def hatte_intensivstation(self) -> bool:
        return any(a.ist_intensivstation for a in self.abschnitte)


class Diagnose(_Basis):
    icd_code: str | None = Field(default=None, description="ICD-10-GM-Code; None bei Freitext-Diagnosen")
    freitext: str | None = None
    sicherheit: Diagnosesicherheit = Diagnosesicherheit.UNBEKANNT
    erkrankungsbeginn: date | None = None
    erfasst_am: date | None = None
    hinweis: str | None = None


class Laborbefund(_Basis):
    labornummer: str | None = None
    untersuchung: str | None = None
    ergebnis: str | None = None
    datum: datetime | None = None
    labor: str | None = None


class KisFall(_Basis):
    """Alles, was der Meldeassistent aus dem KIS für einen Fall braucht."""

    patient: Patient
    aufenthalt: Aufenthalt
    diagnosen: list[Diagnose] = Field(default_factory=list)
    laborbefunde: list[Laborbefund] = Field(default_factory=list)
    hinweise: list[str] = Field(default_factory=list, description="Lücken/Auffälligkeiten in den KIS-Daten, auf Deutsch")


class FallUebersicht(_Basis):
    """Eine Zeile der Arbeitsliste (leichtgewichtig, ohne Labor und Abschnitte im Detail)."""

    kis_fall_id: str
    patient_name: str
    geburtsdatum: date | None = None
    aufnahme: datetime | None = None
    laufend: bool
    station: str | None = None
    verstorben: Verstorben = Verstorben.UNBEKANNT
    diagnosen: list[Diagnose] = Field(default_factory=list)
