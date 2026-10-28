"""Konfiguration aus Umgebungsvariablen.

Harte Regeln 2 und 4: Standard ist immer das lokale Schein-KIS. Zugangsdaten (Token) stehen nie im
Code, sondern nur in Umgebungsvariablen oder einer Secret-Datei außerhalb des Repositories.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

STANDARD_KIS_URL = "http://localhost:8080/fhir"


class KisKonfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    basis_url: str = STANDARD_KIS_URL
    token: str | None = Field(default=None, repr=False)  # repr=False: Token taucht nie in Logs/Fehlern auf
    timeout_sekunden: float = 30

    @classmethod
    def aus_umgebung(cls, umgebung: dict[str, str] | None = None) -> "KisKonfig":
        env = os.environ if umgebung is None else umgebung
        return cls(
            basis_url=env.get("KIS_FHIR_BASIS_URL", STANDARD_KIS_URL),
            token=env.get("KIS_FHIR_TOKEN") or None,
            timeout_sekunden=float(env.get("KIS_FHIR_TIMEOUT", "30")),
        )


def erzeuge_kis_adapter(konfig: KisKonfig | None = None):
    """Erzeugt den KIS-Adapter. Spätere Adapter (HL7 v2) werden hier über eine Einstellung ausgewählt."""
    from meldeassistent.kis.isik_fhir import IsikFhirAdapter

    konfig = konfig or KisKonfig.aus_umgebung()
    return IsikFhirAdapter(konfig.basis_url, token=konfig.token, timeout=konfig.timeout_sekunden)
