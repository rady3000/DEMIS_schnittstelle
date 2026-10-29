"""Audit-Log (Harte Regel 5): nur Vorgangs-ID, Zeit, Benutzer, Meldeweg, Status.

Keine Namen, Diagnosen, KIS-IDs oder Meldeinhalte. Jede Zeile ist ein JSON-Objekt. Unzulässige
Felder werden abgelehnt, damit nie versehentlich Gesundheitsdaten im Log landen.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

ERLAUBT = {"zeit", "vorgang", "benutzer", "meldeweg", "status", "dauer_s"}


class Audit:
    def __init__(self, pfad: Path | None):
        self.pfad = pfad
        self._sperre = threading.Lock()
        if pfad:
            pfad.parent.mkdir(parents=True, exist_ok=True)

    def schreibe(self, vorgang: str, benutzer: str, meldeweg: str, status: str, jetzt: datetime, dauer_s: int | None = None) -> dict:
        eintrag = {"zeit": jetzt.isoformat(timespec="seconds"), "vorgang": vorgang, "benutzer": benutzer, "meldeweg": meldeweg, "status": status}
        if dauer_s is not None:
            eintrag["dauer_s"] = dauer_s
        assert set(eintrag) <= ERLAUBT
        if self.pfad:
            with self._sperre, self.pfad.open("a", encoding="utf-8") as datei:
                datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
        return eintrag

    def lies(self) -> list[dict]:
        if not self.pfad or not self.pfad.exists():
            return []
        return [json.loads(z) for z in self.pfad.read_text(encoding="utf-8").splitlines() if z.strip()]
