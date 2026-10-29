"""Vorläufiges Regelwerk: Welcher Meldeweg gilt für einen Fall?

ACHTUNG: Das ist nur das Nötigste für Phase 4 (Arbeitsliste) und deckt die sieben Testfälle ab.
In Phase 6 wird es durch das vollständige, von der Hygiene ohne Programmierung pflegbare
YAML-Regelwerk ersetzt (Krankheiten mit Spalten Verdacht/Erkrankung/Tod laut Landesformular).

Rechtsgrundlagen (im Original gelesen, siehe PLAN.md): § 6 IfSG und SächsIfSMeldeVO vom 19.07.2024.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from meldeassistent.modell import Diagnose, Diagnosesicherheit, FallUebersicht, Verstorben


class Meldeweg(str, Enum):
    DEMIS = "demis"  # ärztliche Meldung über DEMIS
    SACHSEN = "sachsen"  # Landesmeldung nach SächsIfSMeldeVO
    KLAERUNG = "klaerung"  # weder DEMIS-Profil noch Landesverordnung: manuelle Klärung
    KEINER = "keiner"  # nach diesem Regelwerk nicht meldepflichtig


# ICD-10-GM-Präfixe der in DEMIS umgesetzten Krankheiten (Kürzel laut DEMIS)
ICD_PRAEFIXE = {
    "CDFD": ("A04.7",),
    "MYTD": ("A15", "A16", "A17", "A18", "A19"),
    "MSVD": ("B05",),
}
INFLUENZA = ("J09", "J10", "J11")
GASTROENTERITIS = ("A08",)
INFEKTIONSKRANKHEITEN = tuple(f"{b}{n:02d}" for b in "AB" for n in range(0, 100))
AIDS_HIV = ("B20", "B21", "B22", "B23", "B24")  # § 1 Abs. 2 SächsIfSMeldeVO: Tod bei AIDS ist ausgenommen

BEGRUENDUNG = {
    Meldeweg.DEMIS: "Ärztliche Meldung nach § 6 Abs. 1 IfSG über DEMIS.",
    Meldeweg.SACHSEN: "Landesmeldung nach SächsIfSMeldeVO (nicht über DEMIS).",
    Meldeweg.KLAERUNG: "Kein automatischer Meldeweg: bitte mit der Krankenhaushygiene klären.",
    Meldeweg.KEINER: "Nach dem Regelwerk nicht meldepflichtig.",
}


@dataclass(frozen=True)
class Bewertung:
    weg: Meldeweg
    kuerzel: str | None  # DEMIS-Kürzel, nur bei Meldeweg.DEMIS
    grund: str  # verständlich, auf Deutsch
    diagnose: Diagnose | None = None  # die auslösende Diagnose

    @property
    def meldepflichtig(self) -> bool:
        return self.weg is not Meldeweg.KEINER


def _passt(diagnose: Diagnose, praefixe: tuple[str, ...]) -> bool:
    return bool(diagnose.icd_code and diagnose.icd_code.startswith(praefixe)) and diagnose.sicherheit is not Diagnosesicherheit.AUSGESCHLOSSEN


def bewerte(fall: FallUebersicht, alle: list[FallUebersicht]) -> Bewertung:
    """Meldeweg eines Falls. ``alle``: die ganze Arbeitsliste (für die Erkennung von Häufungen)."""
    for kuerzel, praefixe in ICD_PRAEFIXE.items():
        for d in fall.diagnosen:
            if _passt(d, praefixe):
                return Bewertung(Meldeweg.DEMIS, kuerzel, f"{BEGRUENDUNG[Meldeweg.DEMIS]} Meldetatbestand: {kuerzel}.", d)
    for d in fall.diagnosen:
        if _passt(d, INFLUENZA):
            return Bewertung(Meldeweg.SACHSEN, None, "Influenza: Landesmeldung nach § 1 Abs. 1 Nr. 9 SächsIfSMeldeVO (in DEMIS nur zoonotische Influenza).", d)
    for d in fall.diagnosen:
        if _passt(d, GASTROENTERITIS) and fall.station:
            gleiche = [
                f for f in alle
                if f.laufend and f.station == fall.station and any(_passt(x, GASTROENTERITIS) for x in f.diagnosen)
            ]
            if len(gleiche) >= 2 and fall.laufend:
                return Bewertung(
                    Meldeweg.KLAERUNG, None,
                    f"Mögliche Häufung nosokomialer Infektionen ({len(gleiche)} Fälle auf derselben Station, § 6 Abs. 3 IfSG). "
                    "DEMIS bietet dafür kein Profil; bitte mit der Krankenhaushygiene klären.",
                    d,
                )
    if fall.verstorben is Verstorben.JA:
        for d in fall.diagnosen:
            if d.icd_code and d.icd_code.startswith(INFEKTIONSKRANKHEITEN) and not d.icd_code.startswith(AIDS_HIV) and d.sicherheit is not Diagnosesicherheit.AUSGESCHLOSSEN:
                return Bewertung(Meldeweg.SACHSEN, None, "Tod bei Infektionskrankheit: Landesmeldung nach § 1 Abs. 2 SächsIfSMeldeVO.", d)
    return Bewertung(Meldeweg.KEINER, None, BEGRUENDUNG[Meldeweg.KEINER])
