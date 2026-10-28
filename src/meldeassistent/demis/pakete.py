"""Katalog der DEMIS-Pakete: Fragebögen, Wertemengen und Codesysteme.

Liest direkt aus den heruntergeladenen Paketen (``tools/einrichten.py``). So stammen alle
Antwortmöglichkeiten, Anzeigetexte und Fragen aus der offiziellen Quelle und werden nicht im Code
nachgebaut (Harte Regel 3).
"""

from __future__ import annotations

import json
import tarfile
from dataclasses import dataclass
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[3]
PAKETORDNER = PROJEKT / ".fhir" / "pakete"
PAKETE = ("rki.demis.common-3.0.0.tgz", "rki.demis.disease-3.0.0.tgz")


class PaketeFehlen(RuntimeError):
    """Die DEMIS-Pakete wurden noch nicht geladen."""


@dataclass(frozen=True)
class Konzept:
    system: str
    code: str
    display: str | None = None


@dataclass(frozen=True)
class Wertemenge:
    """Zulässige Antworten. ``konzepte`` ist None, wenn sie nicht aufzählbar sind (z. B. alle ISO-Länder)."""

    url: str
    system_standard: str | None
    konzepte: tuple[Konzept, ...] | None

    def finde(self, code: str) -> Konzept | None:
        if self.konzepte is None:
            return None
        return next((k for k in self.konzepte if k.code == code), None)


def _ohne_version(kanonisch: str) -> str:
    return kanonisch.split("|", 1)[0]


class DemisPakete:
    def __init__(self, ordner: Path = PAKETORDNER):
        self.ressourcen: dict[tuple[str, str], dict] = {}
        self.fragebogen_nach_name: dict[str, dict] = {}
        for name in PAKETE:
            pfad = ordner / name
            if not pfad.exists():
                raise PaketeFehlen(f"{pfad} fehlt. Bitte 'python tools/einrichten.py' ausführen.")
            with tarfile.open(pfad) as archiv:
                for mitglied in archiv.getmembers():
                    if not mitglied.name.endswith(".json") or not mitglied.isfile():
                        continue
                    inhalt = json.load(archiv.extractfile(mitglied))
                    typ, url = inhalt.get("resourceType"), inhalt.get("url")
                    if typ and url:
                        self.ressourcen[(typ, _ohne_version(url))] = inhalt
                    if typ == "Questionnaire":
                        # Fragebögen liegen im Paket als Beispieldateien: Questionnaire-DiseaseQuestionsCDFD.json
                        self.fragebogen_nach_name[url.rsplit("/", 1)[-1].removeprefix("DiseaseQuestions")] = inhalt
        self._wertemengen: dict[str, Wertemenge] = {}

    # --- Fragebögen --------------------------------------------------------------------------
    def fragebogen(self, name: str) -> dict:
        """``name``: 'Common' oder ein Krankheitskürzel wie 'CDFD'."""
        try:
            return self.fragebogen_nach_name[name]
        except KeyError:
            raise KeyError(f"Kein Fragebogen '{name}' im DEMIS-Paket") from None

    def fragebogen_url(self, name: str) -> str:
        return self.fragebogen(name)["url"]

    # --- Codesysteme und Wertemengen -----------------------------------------------------------
    def _codesystem(self, url: str) -> dict | None:
        return self.ressourcen.get(("CodeSystem", _ohne_version(url)))

    def _codesystem_konzepte(self, cs: dict) -> list[Konzept]:
        """Alle Konzepte eines Codesystems, auch die verschachtelten (z. B. 'hospital' unter 'medFacility')."""
        ergebnis: list[Konzept] = []

        def gehe(liste: list[dict]) -> None:
            for c in liste:
                ergebnis.append(Konzept(cs["url"], c["code"], c.get("display")))
                gehe(c.get("concept", []))

        gehe(cs.get("concept", []))
        return ergebnis

    def wertemenge(self, url: str) -> Wertemenge:
        url = _ohne_version(url)
        if url in self._wertemengen:
            return self._wertemengen[url]
        vs = self.ressourcen.get(("ValueSet", url))
        if vs is None:
            ergebnis = Wertemenge(url, None, None)
        else:
            konzepte: list[Konzept] | None = []
            erstes_system = None
            for inc in vs.get("compose", {}).get("include", []):
                system = inc.get("system")
                erstes_system = erstes_system or system
                if "concept" in inc:
                    cs = self._codesystem(system) if system else None
                    anzeigen = {k.code: k.display for k in self._codesystem_konzepte(cs)} if cs else {}
                    for c in inc["concept"]:
                        konzepte.append(Konzept(system, c["code"], c.get("display") or anzeigen.get(c["code"])))
                elif "valueSet" in inc:
                    for sub in inc["valueSet"]:
                        teil = self.wertemenge(sub)
                        erstes_system = erstes_system or teil.system_standard
                        if teil.konzepte is None:
                            konzepte = None
                            break
                        konzepte.extend(teil.konzepte)
                elif system and "filter" not in inc:
                    cs = self._codesystem(system)  # ganzes Codesystem; nur aufzählbar, wenn es im Paket liegt
                    if cs and cs.get("concept"):
                        konzepte.extend(self._codesystem_konzepte(cs))
                    else:
                        konzepte = None
                else:
                    konzepte = None
                if konzepte is None:
                    break
            ergebnis = Wertemenge(url, erstes_system, tuple(konzepte) if konzepte is not None else None)
        self._wertemengen[url] = ergebnis
        return ergebnis

    def codesystem_anzeige(self, system: str, code: str) -> str | None:
        cs = self._codesystem(system)
        if not cs:
            return None
        return next((k.display for k in self._codesystem_konzepte(cs) if k.code == code), None)


_standard: DemisPakete | None = None


def standard_pakete() -> DemisPakete:
    """Gemeinsame Instanz (Laden dauert etwa eine Sekunde)."""
    global _standard
    if _standard is None:
        _standard = DemisPakete()
    return _standard
