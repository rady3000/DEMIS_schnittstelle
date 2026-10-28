"""Gesamtprüfung einer Meldung: Fragebogen-Prüfer + offizieller Validator, Ergebnis auf Deutsch."""

from __future__ import annotations

from dataclasses import dataclass, field

from .fehlertexte import Problem, uebersetze
from .fragebogen import pruefe_antworten
from .pakete import DemisPakete, standard_pakete
from .validator import FhirValidator


@dataclass(frozen=True)
class Pruefergebnis:
    probleme: list[Problem] = field(default_factory=list)

    @property
    def fehler(self) -> list[Problem]:
        return [p for p in self.probleme if p.schwere == "fehler"]

    @property
    def offen(self) -> list[Problem]:
        """Noch nicht beantwortete Fragen (nur im strengen Modus)."""
        return [p for p in self.probleme if p.schwere == "offen"]

    @property
    def hinweise(self) -> list[Problem]:
        return [p for p in self.probleme if p.schwere == "hinweis"]

    @property
    def ok(self) -> bool:
        """True, wenn DEMIS die Meldung formal annehmen würde (keine Fehler)."""
        return not self.fehler

    @property
    def vollstaendig(self) -> bool:
        """True, wenn zusätzlich alle Fragen aktiv beantwortet wurden. Das verlangt der Meldeassistent vor dem Senden."""
        return not self.fehler and not self.offen


def _fragebogen_probleme(bundle: dict, pakete: DemisPakete, streng: bool) -> list[Problem]:
    probleme = []
    for eintrag in bundle.get("entry", []):
        r = eintrag["resource"]
        if r["resourceType"] != "QuestionnaireResponse":
            continue
        name = r["questionnaire"].rsplit("/", 1)[-1].removeprefix("DiseaseQuestions")
        wo = "Allgemeine klinische Angaben" if name == "Common" else "Krankheitsspezifische Angaben"
        for befund in pruefe_antworten(pakete.fragebogen(name), r["item"], pakete, streng):
            probleme.append(Problem(befund.schwere, wo, befund.text, quelle="fragebogen"))
    return probleme


def pruefe_meldung(bundle: dict, validator: FhirValidator, pakete: DemisPakete | None = None, streng: bool = False) -> Pruefergebnis:
    """Prüft eine fertige Meldung. Wirft ValidatorFehler, wenn der Validator nicht erreichbar ist.

    ``streng``: unbeantwortete Fragen ("nicht erhoben") werden als "offen" gemeldet (siehe ``Pruefergebnis.vollstaendig``).
    """
    pakete = pakete or standard_pakete()
    probleme = _fragebogen_probleme(bundle, pakete, streng)
    ergebnis = validator.pruefe(bundle)
    vom_validator = [p for issue in ergebnis["issue"] if (p := uebersetze(issue, bundle)) is not None]
    probleme.extend(vom_validator)
    # Folgefehler ("entspricht nicht dem Profil") nur zeigen, wenn es keine eigentliche Ursache gibt
    gibt_ursache = any(p.schwere == "fehler" and not p.folgefehler for p in probleme)
    probleme = [p for p in probleme if not (p.folgefehler and gibt_ursache)]
    # Fehler zuerst; gleiche Aussage nur einmal (auch wenn sie zusätzlich als Hinweis auftaucht)
    probleme.sort(key=lambda p: ({"fehler": 0, "offen": 1}.get(p.schwere, 2), p.quelle != "fragebogen"))
    gesehen: set[tuple[str, str]] = set()
    eindeutig = []
    for p in probleme:
        if (p.wo, p.text) in gesehen:
            continue
        gesehen.add((p.wo, p.text))
        eindeutig.append(p)
    probleme = eindeutig
    return Pruefergebnis(probleme)
