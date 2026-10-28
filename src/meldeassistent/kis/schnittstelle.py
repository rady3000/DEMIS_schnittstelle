"""Die Schnittstelle, die jeder KIS-Adapter erfüllen muss.

Der Rest der Anwendung spricht nur mit ``KisAdapter``. Ein späterer HL7-v2-Adapter (oder ein
Adapter für ein anderes KIS) implementiert dieselben Methoden und liefert dieselben Modelle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from meldeassistent.modell import FallUebersicht, KisFall


class KisFehler(Exception):
    """Basisklasse für alle KIS-Probleme. Meldungen sind verständlich und enthalten keine Gesundheitsdaten."""


class KisNichtErreichbar(KisFehler):
    """Das KIS antwortet nicht (Netzwerk, Zeitüberschreitung, Server aus)."""


class KisAntwortFehler(KisFehler):
    """Das KIS hat mit einem Fehlerstatus geantwortet (z. B. 401, 404, 500)."""

    def __init__(self, meldung: str, status: int | None = None):
        super().__init__(meldung)
        self.status = status


class KisDatenFehler(KisFehler):
    """Das KIS hat Daten geliefert, die wir nicht verstehen (falsche FHIR-Version, unerwartete Struktur)."""


class KisAdapter(ABC):
    @abstractmethod
    def pruefe_verbindung(self) -> str:
        """Prüft, ob das KIS erreichbar und kompatibel ist. Gibt eine kurze Statusmeldung zurück oder wirft KisFehler."""

    @abstractmethod
    def liste_faelle(self, seit: date | None = None, nur_laufende: bool = False) -> list[FallUebersicht]:
        """Arbeitsliste: stationäre Fälle mit Diagnosen.

        ``seit``: nur Fälle, die an oder nach diesem Datum noch liefen oder begonnen haben.
        ``nur_laufende``: nur Fälle, die noch nicht beendet sind.
        """

    @abstractmethod
    def lade_fall(self, kis_fall_id: str) -> KisFall:
        """Alle Daten eines Falls (Patient, Aufenthalt mit Abschnitten, Diagnosen, Labor)."""
